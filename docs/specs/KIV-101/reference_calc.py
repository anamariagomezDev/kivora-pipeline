"""Cálculo de referencia de KIV-101 (solo lectura; ver spec.md §5 y Anexo A).

Adaptado en KIV-102 (docs/specs/KIV-102/spec.md, K7): el importe de cada devolución sale de la
única clave que traiga, `amount` (formato antiguo) o `refund_amount` (nuevo); con las dos o con
ninguna es invalid_record. R9 compara refund_id, order_id, refunded_at, importe y currency
(no `reason`).

Uso: uv run python -I docs/specs/KIV-101/reference_calc.py <inbox> <reference> [--summary | claves "AAAA-MM-DD,cliente"...]
"""
import csv, json, sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

MAD = ZoneInfo("Europe/Madrid")
inbox, ref = Path(sys.argv[1]), Path(sys.argv[2])
fx = {r["currency"].strip().upper(): Decimal(r["rate_to_eur"]) for r in csv.DictReader(open(ref / "fx_rates.csv", encoding="utf-8-sig"))}
q = lambda x: x.quantize(Decimal("0.01"), ROUND_HALF_UP)
def ts(s): return datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
def mdate(s): return ts(s).astimezone(MAD).date().isoformat()
def dec(v):
    try: d = Decimal(str(v).strip())
    except (InvalidOperation, ValueError): return None
    return d if d.is_finite() else None
def ramt(r):  # KIV-102: importe de la devolución si trae exactamente una de las dos claves
    keys = [k for k in ("amount", "refund_amount") if k in r]
    return r[keys[0]] if len(keys) == 1 else None

orders, customers, captured, refunds = {}, {}, set(), []
for day in sorted(p for p in inbox.iterdir() if p.is_dir()):
    for i, r in enumerate(csv.DictReader(open(day / "orders.csv", encoding="utf-8-sig")) if (day / "orders.csv").exists() else []):
        key = ((r.get("updated_at") or "").strip(), day.name, i)
        if r["order_id"] not in orders or key > orders[r["order_id"]][0]: orders[r["order_id"]] = (key, r, day.name)
    for r in csv.DictReader(open(day / "customers.csv", encoding="utf-8-sig")) if (day / "customers.csv").exists() else []:
        customers[r["customer_id"]] = r
    for r in csv.DictReader(open(day / "payments.csv", encoding="utf-8-sig")) if (day / "payments.csv").exists() else []:
        if (r.get("status") or "").strip() == "captured": captured.add(r["order_id"])
    if (day / "refunds.json").exists():
        for i, r in enumerate(json.load(open(day / "refunds.json", encoding="utf-8"))): refunds.append((day.name, i, r))

rejected, sales = [], {}
for oid, (_, o, day) in orders.items():
    try:
        assert all((o.get(f) or "").strip() for f in ["order_id", "customer_id", "created_at", "updated_at", "status", "currency", "total_amount"])
        ts(o["created_at"]); amt = dec(o["total_amount"]); assert amt is not None and amt > 0
        assert o["status"].strip() in ("confirmed", "cancelled")
    except (AssertionError, ValueError):
        rejected.append(("orders", oid, day, "invalid_record")); continue
    cur = o["currency"].strip().upper()
    if cur not in fx: rejected.append(("orders", oid, day, "unknown_currency")); continue
    if o["status"].strip() == "cancelled": rejected.append(("orders", oid, day, "not_sale_cancelled")); continue
    if oid not in captured: rejected.append(("orders", oid, day, "not_sale_unpaid")); continue
    sales[oid] = dict(customer_id=o["customer_id"].strip(), date=mdate(o["created_at"]), cur=cur, amt=amt, eur=q(amt * fx[cur]))

byid = defaultdict(list)
for day, i, r in refunds:
    rid = str(r.get("refund_id") or "").strip()
    if not rid: rejected.append(("refunds", "", day, "invalid_record")); continue  # sin refund_id: no se agrupa (R9)
    byid[rid].append((day, i, r))
cand = []
for rid, occ in byid.items():
    sig = lambda r: json.dumps([r.get("refund_id"), r.get("order_id"), r.get("refunded_at"), ramt(r), r.get("currency")])
    if len({sig(r) for _, _, r in occ}) > 1:
        rejected += [("refunds", rid, d, "conflicting_duplicate") for d, _, _ in occ]; continue
    for d, _, _ in occ[1:]: rejected.append(("refunds", rid, d, "duplicate_refund"))
    cand.append(occ[0])
accepted, used = [], defaultdict(Decimal)
def rkey(c): return (ts(c[2]["refunded_at"]), str(c[2]["refund_id"]))
valid = []
for day, i, r in cand:
    rid = str(r.get("refund_id", "")).strip()
    try:
        assert rid and all(str(r.get(f, "") or "").strip() for f in ["order_id", "refunded_at", "currency"])
        ts(r["refunded_at"]); a = dec(ramt(r)); assert a is not None and a > 0
    except (AssertionError, ValueError, KeyError):
        rejected.append(("refunds", rid, day, "invalid_record")); continue
    cur = str(r["currency"]).strip().upper()
    if cur not in fx: rejected.append(("refunds", rid, day, "unknown_currency")); continue
    oid = str(r["order_id"]).strip()
    if oid not in orders: rejected.append(("refunds", rid, day, "order_not_found")); continue
    if oid not in sales: rejected.append(("refunds", rid, day, "order_not_sale")); continue
    if cur != sales[oid]["cur"]: rejected.append(("refunds", rid, day, "currency_mismatch")); continue
    valid.append((day, i, r))
for day, i, r in sorted(valid, key=rkey):
    oid, a = str(r["order_id"]).strip(), dec(ramt(r))
    if used[oid] + a > sales[oid]["amt"]: rejected.append(("refunds", str(r["refund_id"]).strip(), day, "refund_exceeds_order")); continue
    used[oid] += a
    accepted.append(dict(refund_id=str(r["refund_id"]).strip(), order_id=oid, customer_id=sales[oid]["customer_id"],
                         date=mdate(r["refunded_at"]), eur=q(a * fx[str(r["currency"]).strip().upper()])))

rows = defaultdict(lambda: dict(orders_count=0, gross=Decimal("0.00"), refunded=Decimal("0.00"), refunds_count=0))
for s in sales.values(): k = (s["date"], s["customer_id"]); rows[k]["orders_count"] += 1; rows[k]["gross"] += s["eur"]
for a in accepted: k = (a["date"], a["customer_id"]); rows[k]["refunds_count"] += 1; rows[k]["refunded"] += a["eur"]
def country(c): return ((customers.get(c) or {}).get("country") or "").strip().upper() or "UNKNOWN"
def lpd(c, d): return max((s["date"] for s in sales.values() if s["customer_id"] == c and s["date"] <= d), default="")
out = [(d, c, country(c), v["orders_count"], v["gross"], v["refunded"], v["gross"] - v["refunded"], v["refunds_count"], lpd(c, d))
       for (d, c), v in sorted(rows.items())]

if len(sys.argv) > 3 and sys.argv[3] == "--summary":
    print("ventas", len(sales), "bruto", sum(s["eur"] for s in sales.values()), "devuelto", sum(a["eur"] for a in accepted),
          "neto", sum(r[6] for r in out), "filas", len(out), "solo_devolucion", sum(1 for r in out if r[3] == 0),
          "neto_negativo", sum(1 for r in out if r[6] < 0))
    for r in sorted(rejected): print("rejected", *r)
    sys.exit()
want = set(sys.argv[3:])
for r in out:
    if not want or r[1] in want or f"{r[0]},{r[1]}" in want:
        print(",".join([r[0], r[1], r[2], str(r[3]), f"{r[4]:.2f}", f"{r[5]:.2f}", f"{r[6]:.2f}", str(r[7]), r[8]]))
