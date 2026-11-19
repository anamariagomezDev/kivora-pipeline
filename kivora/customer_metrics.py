"""KIV-101: sales, refunds, rejections and daily customer metrics.

Pure functions, no I/O. Rows are dicts with the raw TEXT columns of the raw_* tables
plus `_day` (inbox folder) and `_pos` (position in its file). Requirement ids (R*) are
those of docs/specs/KIV-101/spec.md.
"""

from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")
CENT = Decimal("0.01")
ZERO = Decimal("0.00")

ORDER_REQUIRED = ["order_id", "customer_id", "created_at", "updated_at", "status",
                  "currency", "total_amount"]
ORDER_STATUSES = ("confirmed", "cancelled")
REFUND_REQUIRED = ["order_id", "refunded_at", "currency"]


# --- values ----------------------------------------------------------------

def text(value):
    return "" if value is None else str(value).strip()


def parse_ts(value):
    """ISO 8601 timestamp with zone ('Z' = UTC). Without zone it is not valid (T5)."""
    ts = datetime.fromisoformat(text(value).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError(f"sin zona horaria: {value!r}")
    return ts


def madrid_date(value):
    """R6: natural day in Europe/Madrid, with the time zone database (DST included)."""
    return parse_ts(value).astimezone(MADRID).date().isoformat()


def to_decimal(value):
    try:
        number = Decimal(text(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def to_eur(amount, rate):
    """R5: decimal arithmetic, half up, rounded record by record."""
    return (amount * rate).quantize(CENT, rounding=ROUND_HALF_UP)


def fx_table(rows):
    return {text(r["currency"]).upper(): Decimal(text(r["rate_to_eur"])) for r in rows}


def rejection(source, record_id, reason, row, explanation):
    file = "orders.csv" if source == "orders" else "refunds.json"
    return {"source": source, "record_id": record_id, "reason": reason,
            "inbox_day": row["_day"], "detail": f"{file}#{row['_pos']}: {explanation}",
            "_pos": int(row["_pos"])}


def _in_file_order(rows):
    return sorted(rows, key=lambda r: (r["_day"], int(r["_pos"])))


# --- customers and payments (R4, R7) -----------------------------------------

def current_countries(customer_rows):
    """R7: last row received per customer (later folder, later row); country normalised."""
    countries = {}
    for row in _in_file_order(customer_rows):
        countries[text(row["customer_id"])] = text(row["country"]).upper() or "UNKNOWN"
    return countries


def captured_orders(payment_rows):
    return {text(p["order_id"]) for p in payment_rows if text(p["status"]) == "captured"}


# --- orders (R2, R3, R4) -----------------------------------------------------

def latest_orders(order_rows):
    """R2: per order_id, the greatest updated_at; ties -> later folder, then later row."""
    best = {}
    for row in order_rows:
        key = (text(row["updated_at"]), row["_day"], int(row["_pos"]))
        oid = text(row["order_id"])
        if oid not in best or key > best[oid][0]:
            best[oid] = (key, row)
    return {oid: row for oid, (_, row) in best.items()}


def _order_problem(row):
    empty = [f for f in ORDER_REQUIRED if not text(row[f])]
    if empty:
        return f"campos vacíos: {', '.join(empty)}"
    for field in ("created_at", "updated_at"):
        try:
            parse_ts(row[field])
        except ValueError:
            return f"{field} no es ISO 8601 con zona: {row[field]!r}"
    amount = to_decimal(row["total_amount"])
    if amount is None or amount <= 0:
        return f"total_amount no numérico o <= 0: {row['total_amount']!r}"
    if text(row["status"]) not in ORDER_STATUSES:
        return f"status no válido: {row['status']!r}"
    return None


def classify_orders(latest, fx, captured):
    """R3, R4: (sales by order_id, rejections), with the reasons in priority order."""
    sales, rejected = {}, []
    for oid in sorted(latest):
        row = latest[oid]
        problem = _order_problem(row)
        if problem:
            rejected.append(rejection("orders", oid, "invalid_record", row, problem))
            continue
        currency = text(row["currency"]).upper()
        if currency not in fx:
            rejected.append(rejection("orders", oid, "unknown_currency", row,
                                      f"moneda {currency} no está en fx_rates.csv"))
            continue
        if text(row["status"]) == "cancelled":
            rejected.append(rejection("orders", oid, "not_sale_cancelled", row,
                                      "la última versión está cancelada"))
            continue
        if oid not in captured:
            rejected.append(rejection("orders", oid, "not_sale_unpaid", row,
                                      "ningún pago captured"))
            continue
        total = to_decimal(row["total_amount"])
        sales[oid] = {"order_id": oid, "customer_id": text(row["customer_id"]),
                      "date": madrid_date(row["created_at"]), "currency": currency,
                      "total": total, "eur": to_eur(total, fx[currency])}
    return sales, rejected


# --- refunds (R8, R9, R10, R11) ----------------------------------------------

def deduplicate_refunds(refund_rows):
    """R8 (empty refund_id) and R9 (same refund_id): (candidates, rejections)."""
    rejected, groups = [], defaultdict(list)
    for row in _in_file_order(refund_rows):
        rid = text(row["refund_id"])
        if not rid:
            rejected.append(rejection("refunds", "", "invalid_record", row, "refund_id vacío"))
            continue
        groups[rid].append(row)
    candidates = []
    for rid in sorted(groups):
        rows = groups[rid]
        if len({r["_raw"] for r in rows}) > 1:
            rejected += [rejection("refunds", rid, "conflicting_duplicate", r,
                                   f"{len(rows)} apariciones con contenido distinto")
                         for r in rows]
            continue
        first = rows[0]
        rejected += [rejection("refunds", rid, "duplicate_refund", r,
                               f"copia de {first['_day']}/refunds.json#{first['_pos']}")
                     for r in rows[1:]]
        candidates.append(first)
    return candidates, rejected


def _refund_problem(row):
    empty = [f for f in REFUND_REQUIRED if not text(row[f])]
    if empty:
        return f"campos vacíos: {', '.join(empty)}"
    try:
        parse_ts(row["refunded_at"])
    except ValueError:
        return f"refunded_at no es ISO 8601 con zona: {row['refunded_at']!r}"
    amount = to_decimal(row["amount"])
    if amount is None or amount <= 0:
        return f"amount no numérico o <= 0: {row['amount']!r}"
    return None


def classify_refunds(refund_rows, fx, latest, sales):
    """R8–R10, then R11. Returns (accepted refunds, rejections)."""
    candidates, rejected = deduplicate_refunds(refund_rows)
    valid = []
    for row in candidates:
        rid = text(row["refund_id"])
        problem = _refund_problem(row)
        if problem:
            rejected.append(rejection("refunds", rid, "invalid_record", row, problem))
            continue
        currency = text(row["currency"]).upper()
        if currency not in fx:
            rejected.append(rejection("refunds", rid, "unknown_currency", row,
                                      f"moneda {currency} no está en fx_rates.csv"))
            continue
        oid = text(row["order_id"])
        if oid not in latest:
            rejected.append(rejection("refunds", rid, "order_not_found", row,
                                      f"el pedido {oid} no está en ningún orders.csv"))
            continue
        if oid not in sales:
            rejected.append(rejection("refunds", rid, "order_not_sale", row,
                                      f"el pedido {oid} no es venta"))
            continue
        if currency != sales[oid]["currency"]:
            rejected.append(rejection("refunds", rid, "currency_mismatch", row,
                                      f"{currency} frente a {sales[oid]['currency']} del pedido"))
            continue
        valid.append(row)
    accepted, over = apply_refund_limit(valid, fx, sales)
    return accepted, rejected + over


def apply_refund_limit(valid_rows, fx, sales):
    """R11: per order, in (refunded_at, refund_id) order, accept while the sum in the
    order currency does not exceed total_amount; otherwise reject the whole refund."""
    used = defaultdict(Decimal)
    accepted, rejected = [], []
    for row in sorted(valid_rows, key=lambda r: (parse_ts(r["refunded_at"]), text(r["refund_id"]))):
        rid, oid = text(row["refund_id"]), text(row["order_id"])
        amount, sale = to_decimal(row["amount"]), sales[oid]
        if used[oid] + amount > sale["total"]:
            rejected.append(rejection(
                "refunds", rid, "refund_exceeds_order", row,
                f"{used[oid]} + {amount} supera {sale['total']} {sale['currency']} de {oid}"))
            continue
        used[oid] += amount
        accepted.append({"refund_id": rid, "order_id": oid, "customer_id": sale["customer_id"],
                         "date": madrid_date(row["refunded_at"]), "currency": sale["currency"],
                         "amount": amount, "eur": to_eur(amount, fx[sale["currency"]])})
    return accepted, rejected


# --- metrics (R13, R14) and quality checks (R15) -------------------------------

METRIC_COLUMNS = ["metric_date", "customer_id", "country", "orders_count", "gross_amount",
                  "refunded_amount", "net_amount", "refunds_count", "last_purchase_date"]
CHECK_NAMES = ["net_equals_gross_minus_refunded", "refunds_within_order_total",
               "unique_keys_and_orders"]


def build_metrics(sales, accepted, countries):
    """R13, R14: one row per (metric_date, customer_id) with a sale or an accepted refund.
    Returns (rows sorted by metric_date, customer_id; order_ids aggregated, one per use)."""
    totals = defaultdict(lambda: {"orders_count": 0, "gross_amount": ZERO,
                                  "refunded_amount": ZERO, "refunds_count": 0})
    aggregated, purchase_dates = [], defaultdict(list)
    for sale in sales.values():
        cell = totals[(sale["date"], sale["customer_id"])]
        cell["orders_count"] += 1
        cell["gross_amount"] += sale["eur"]
        aggregated.append(sale["order_id"])
        purchase_dates[sale["customer_id"]].append(sale["date"])
    for refund in accepted:
        cell = totals[(refund["date"], refund["customer_id"])]
        cell["refunds_count"] += 1
        cell["refunded_amount"] += refund["eur"]
    for dates in purchase_dates.values():
        dates.sort()
    rows = []
    for (day, cid), cell in sorted(totals.items()):
        dates = purchase_dates.get(cid, [])
        index = bisect_right(dates, day)  # last purchase <= metric_date, never in the future
        rows.append({"metric_date": day, "customer_id": cid,
                     "country": countries.get(cid, "UNKNOWN"), **cell,
                     "net_amount": cell["gross_amount"] - cell["refunded_amount"],
                     "last_purchase_date": dates[index - 1] if index else ""})
    return rows, aggregated


def quality_checks(rows, aggregated, accepted, sales):
    """R15 / spec §3.3: the three checks, in order, computed on the output."""
    bad_net = sum(1 for r in rows if r["net_amount"] != r["gross_amount"] - r["refunded_amount"])
    refunded = defaultdict(Decimal)
    for refund in accepted:
        refunded[refund["order_id"]] += refund["amount"]
    over = sum(1 for oid, amount in refunded.items() if amount > sales[oid]["total"])
    keys = Counter((r["metric_date"], r["customer_id"]) for r in rows)
    repeated = (sum(n - 1 for n in keys.values() if n > 1)
                + sum(1 for n in Counter(aggregated).values() if n > 1))
    return [{"name": name, "passed": failed == 0, "failed_records": failed}
            for name, failed in zip(CHECK_NAMES, (bad_net, over, repeated))]


def compute(order_rows, customer_rows, payment_rows, refund_rows, fx_rows):
    """Whole KIV-101 computation: (metric rows, rejections, checks)."""
    fx = fx_table(fx_rows)
    latest = latest_orders(order_rows)
    sales, rejected = classify_orders(latest, fx, captured_orders(payment_rows))
    accepted, rejected_refunds = classify_refunds(refund_rows, fx, latest, sales)
    rows, aggregated = build_metrics(sales, accepted, current_countries(customer_rows))
    rejected = sorted(rejected + rejected_refunds,
                      key=lambda r: (r["source"], r["record_id"], r["inbox_day"], r["reason"],
                                     r["_pos"]))
    return rows, rejected, quality_checks(rows, aggregated, accepted, sales)
