"""Tests de KIV-101: daily_customer_metrics, rejected.csv y quality_report.json.

Datos sintéticos en tmp_path, nunca data/inbox/. Los ids R*, E* y S* son los de
docs/specs/KIV-101/spec.md.
"""

import csv
import hashlib
import json
from pathlib import Path

import pytest

from kivora.pipeline import run

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "data" / "reference"  # EUR 1.0, GBP 1.17, USD 0.92 (solo lectura)

ORDER_FIELDS = ["order_id", "customer_id", "created_at", "updated_at", "status",
                "currency", "total_amount"]
CUSTOMER_FIELDS = ["customer_id", "name", "country", "signup_date"]
PAYMENT_FIELDS = ["payment_id", "order_id", "paid_at", "method", "status", "amount"]


# --- helpers ---------------------------------------------------------------

def order(oid, customer, created, amount, currency="EUR", status="confirmed", updated=None):
    return {"order_id": oid, "customer_id": customer, "created_at": created,
            "updated_at": updated or created, "status": status, "currency": currency,
            "total_amount": amount}


def payment(oid, amount="1.00", status="captured", pid=None):
    return {"payment_id": pid or f"P-{oid}-{status}", "order_id": oid,
            "paid_at": "2026-09-01T00:00:00Z", "method": "card", "status": status,
            "amount": amount}


def customer(cid, country="ES"):
    return {"customer_id": cid, "name": f"Cliente {cid}", "country": country,
            "signup_date": "2025-01-01"}


def refund(rid, oid, at, amount, currency="EUR"):
    return {"refund_id": rid, "order_id": oid, "refunded_at": at, "amount": amount,
            "currency": currency}


def _write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_day(inbox, day, orders=(), payments=(), customers=()):
    folder = Path(inbox) / day
    folder.mkdir(parents=True, exist_ok=True)
    _write_csv(folder / "orders.csv", ORDER_FIELDS, orders)
    _write_csv(folder / "payments.csv", PAYMENT_FIELDS, payments)
    _write_csv(folder / "customers.csv", CUSTOMER_FIELDS, customers)
    return folder


def write_refunds(inbox, day, refunds):
    """`refunds` es una lista (se serializa) o un texto (se escribe tal cual)."""
    folder = Path(inbox) / day
    folder.mkdir(parents=True, exist_ok=True)
    text = refunds if isinstance(refunds, str) else json.dumps(refunds, indent=2)
    (folder / "refunds.json").write_text(text, encoding="utf-8")


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def run_pipeline(tmp_path):
    out = tmp_path / "out"
    run(tmp_path / "inbox", REFERENCE, out)
    return out


def metrics(out):
    return read_csv(out / "daily_customer_metrics.csv")


def metrics_by_key(out):
    rows = metrics(out)
    keyed = {(r["metric_date"], r["customer_id"]): r for r in rows}
    assert len(keyed) == len(rows), "claves (metric_date, customer_id) repetidas"
    return keyed


def rejected(out):
    return [(r["source"], r["record_id"], r["inbox_day"], r["reason"])
            for r in read_csv(out / "rejected.csv")]


def quality(out):
    report = json.loads((out / "quality_report.json").read_text(encoding="utf-8"))
    return {c["name"]: c for c in report["checks"]}


def values(row):
    keys = ["country", "orders_count", "gross_amount", "refunded_amount", "net_amount",
            "refunds_count", "last_purchase_date"]
    return tuple(row[k] for k in keys)


D1, D2, D3 = "2026-09-01", "2026-09-02", "2026-09-03"


# --- los siete tests mínimos (assignment.md §4) ------------------------------

def test_dedup_exact_copies_and_versions(tmp_path):
    """1. Duplicados: copia exacta, versión con otro importe y versión cancelada (R2, R4)."""
    inbox = tmp_path / "inbox"
    k1 = order("K-1", "C1", "2026-09-01T10:00:00Z", "10.00")
    write_day(inbox, D1,
              orders=[k1, k1,
                      order("K-2", "C2", "2026-09-01T11:00:00Z", "10.00"),
                      order("K-3", "C3", "2026-09-01T12:00:00Z", "30.00")],
              payments=[payment("K-1"), payment("K-2"), payment("K-3")],
              customers=[customer("C1"), customer("C2"), customer("C3")])
    write_day(inbox, D2,
              orders=[order("K-2", "C2", "2026-09-01T11:00:00Z", "12.00",
                            updated="2026-09-02T09:00:00Z"),
                      order("K-3", "C3", "2026-09-01T12:00:00Z", "30.00", status="cancelled",
                            updated="2026-09-02T09:00:00Z")])
    out = run_pipeline(tmp_path)
    rows = metrics_by_key(out)
    assert values(rows[(D1, "C1")]) == ("ES", "1", "10.00", "0.00", "10.00", "0", D1)
    assert values(rows[(D1, "C2")]) == ("ES", "1", "12.00", "0.00", "12.00", "0", D1)
    assert (D1, "C3") not in rows
    assert rejected(out) == [("orders", "K-3", D2, "not_sale_cancelled")]


def test_null_and_missing_values(tmp_path):
    """2. Nulos: país vacío, cliente inexistente, pedido sin cliente y devoluciones sin refund_id (R3, R7, R8)."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1,
              orders=[order("K-1", "C1", "2026-09-01T10:00:00Z", "10.00"),
                      order("K-2", "C9", "2026-09-01T11:00:00Z", "20.00"),
                      order("K-3", "", "2026-09-01T12:00:00Z", "15.00")],
              payments=[payment("K-1"), payment("K-2"), payment("K-3")],
              customers=[customer("C1", country="")])
    write_refunds(inbox, D1, [refund("", "K-1", "2026-09-01T16:00:00Z", 1.0),
                              refund("  ", "K-1", "2026-09-01T16:10:00Z", 2.0)])
    out = run_pipeline(tmp_path)
    rows = metrics_by_key(out)
    assert values(rows[(D1, "C1")]) == ("UNKNOWN", "1", "10.00", "0.00", "10.00", "0", D1)
    assert values(rows[(D1, "C9")]) == ("UNKNOWN", "1", "20.00", "0.00", "20.00", "0", D1)
    assert sorted(rejected(out)) == [("orders", "K-3", D1, "invalid_record"),
                                     ("refunds", "", D1, "invalid_record"),
                                     ("refunds", "", D1, "invalid_record")]


def test_partial_refund(tmp_path):
    """3. Devolución parcial (R11, R14)."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1, orders=[order("K-1", "C1", "2026-09-01T10:00:00Z", "10.00")],
              payments=[payment("K-1")], customers=[customer("C1")])
    write_refunds(inbox, D1, [refund("R-1", "K-1", "2026-09-01T15:00:00Z", 3.0)])
    out = run_pipeline(tmp_path)
    assert values(metrics_by_key(out)[(D1, "C1")]) == ("ES", "1", "10.00", "3.00", "7.00", "1", D1)
    assert rejected(out) == []


def test_multiple_refunds_same_order(tmp_path):
    """4. Varias devoluciones del mismo pedido, cada una en su día (R6, R11, R13)."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1, orders=[order("K-1", "C1", "2026-09-01T10:00:00Z", "10.00")],
              payments=[payment("K-1")], customers=[customer("C1")])
    write_refunds(inbox, D2, [refund("R-1", "K-1", "2026-09-02T10:00:00Z", 2.0)])
    write_refunds(inbox, D3, [refund("R-2", "K-1", "2026-09-03T10:00:00Z", 3.0)])
    out = run_pipeline(tmp_path)
    rows = metrics_by_key(out)
    assert len(rows) == 3
    assert values(rows[(D1, "C1")]) == ("ES", "1", "10.00", "0.00", "10.00", "0", D1)
    assert values(rows[(D2, "C1")]) == ("ES", "0", "0.00", "2.00", "-2.00", "1", D1)
    assert values(rows[(D3, "C1")]) == ("ES", "0", "0.00", "3.00", "-3.00", "1", D1)
    assert rejected(out) == []


def test_refund_without_order(tmp_path):
    """5. Devolución sin pedido: order_not_found y ninguna fila (R10, R12)."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1, customers=[customer("C1")])
    write_refunds(inbox, D1, [refund("R-1", "K-404", "2026-09-01T10:00:00Z", 5.0)])
    out = run_pipeline(tmp_path)
    assert metrics(out) == []
    assert rejected(out) == [("refunds", "R-1", D1, "order_not_found")]


def test_net_amount(tmp_path):
    """6. Neto = bruto − devuelto, EUR con redondeo por registro y neto negativo (R5, R14)."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1,
              orders=[order("K-1", "C1", "2026-09-01T10:00:00Z", "100.00", currency="USD"),
                      order("K-2", "C1", "2026-09-01T11:00:00Z", "73.56", currency="USD"),
                      order("K-3", "C1", "2026-09-01T12:00:00Z", "179.88", currency="USD")],
              payments=[payment("K-1"), payment("K-2"), payment("K-3")],
              customers=[customer("C1", country="US")])
    write_refunds(inbox, D2, [refund("R-1", "K-3", "2026-09-02T10:00:00Z", 179.88, "USD")])
    out = run_pipeline(tmp_path)
    rows = metrics_by_key(out)
    # 92.00 + 67.68 + 165.49; redondear solo la suma (325.1648) daría 325.16
    assert values(rows[(D1, "C1")]) == ("US", "3", "325.17", "0.00", "325.17", "0", D1)
    assert values(rows[(D2, "C1")]) == ("US", "0", "0.00", "165.49", "-165.49", "1", D1)
    assert quality(out)["net_equals_gross_minus_refunded"] == {
        "name": "net_equals_gross_minus_refunded", "passed": True, "failed_records": 0}


def test_no_duplicates_after_joins(tmp_path):
    """7. Ni los pagos ni los clientes reenviados multiplican filas (R4, R7, control 3)."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1, orders=[order("K-1", "C1", "2026-09-01T10:00:00Z", "30.00")],
              payments=[payment("K-1", "10.00", pid="P-1"), payment("K-1", "20.00", pid="P-2"),
                        payment("K-1", "30.00", "failed", pid="P-3")],
              customers=[customer("C1", "ES")])
    write_day(inbox, D2, customers=[customer("C1", "PT")])
    write_day(inbox, D3, customers=[customer("C1", " fr ")])
    write_refunds(inbox, D3, [refund("R-1", "K-1", "2026-09-01T18:00:00Z", 5.0)])
    out = run_pipeline(tmp_path)
    rows = metrics(out)
    assert len(rows) == 1
    assert values(rows[0]) == ("FR", "1", "30.00", "5.00", "25.00", "1", D1)
    assert quality(out)["unique_keys_and_orders"]["failed_records"] == 0


# --- tests adicionales, uno por regla -----------------------------------------

def test_latest_version_tie_breaks_by_folder_then_row(tmp_path):
    """R2: con el mismo updated_at gana la carpeta posterior y, dentro, la fila posterior."""
    inbox = tmp_path / "inbox"
    same = "2026-09-01T10:00:00Z"
    write_day(inbox, D1,
              orders=[order("K-1", "C1", same, "10.00"),
                      order("K-2", "C2", same, "10.00"), order("K-2", "C2", same, "11.00")],
              payments=[payment("K-1"), payment("K-2")],
              customers=[customer("C1"), customer("C2")])
    write_day(inbox, D2, orders=[order("K-1", "C1", same, "12.00")])
    rows = metrics_by_key(run_pipeline(tmp_path))
    assert rows[(D1, "C1")]["gross_amount"] == "12.00"
    assert rows[(D1, "C2")]["gross_amount"] == "11.00"


def test_refund_exceeds_order(tmp_path):
    """R11: 6 + 5 sobre 10 rechaza la segunda entera; una tercera de 4 sí cabe."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1, orders=[order("K-1", "C1", "2026-09-01T08:00:00Z", "10.00")],
              payments=[payment("K-1")], customers=[customer("C1")])
    write_refunds(inbox, D1, [refund("R-3", "K-1", "2026-09-01T12:00:00Z", 4.0),
                              refund("R-2", "K-1", "2026-09-01T11:00:00Z", 5.0),
                              refund("R-1", "K-1", "2026-09-01T10:00:00Z", 6.0)])
    out = run_pipeline(tmp_path)
    assert values(metrics_by_key(out)[(D1, "C1")]) == ("ES", "1", "10.00", "10.00", "0.00", "2", D1)
    assert rejected(out) == [("refunds", "R-2", D1, "refund_exceeds_order")]
    assert quality(out)["refunds_within_order_total"]["failed_records"] == 0


def test_duplicate_and_conflicting_refunds(tmp_path):
    """R9: copia idéntica → duplicate_refund (se usa una vez); contenido distinto → conflicting_duplicate en todas."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1, orders=[order("K-1", "C1", "2026-09-01T08:00:00Z", "10.00")],
              payments=[payment("K-1")], customers=[customer("C1")])
    write_refunds(inbox, D1, [refund("R-1", "K-1", "2026-09-01T10:00:00Z", 2.0),
                              refund("R-2", "K-1", "2026-09-01T11:00:00Z", 1.0)])
    write_refunds(inbox, D2, [refund("R-1", "K-1", "2026-09-01T10:00:00Z", 2.0),
                              refund("R-2", "K-1", "2026-09-01T11:00:00Z", 4.0)])
    out = run_pipeline(tmp_path)
    assert values(metrics_by_key(out)[(D1, "C1")]) == ("ES", "1", "10.00", "2.00", "8.00", "1", D1)
    assert rejected(out) == [("refunds", "R-1", D2, "duplicate_refund"),
                             ("refunds", "R-2", D1, "conflicting_duplicate"),
                             ("refunds", "R-2", D2, "conflicting_duplicate")]


def test_refund_of_order_that_is_not_a_sale(tmp_path):
    """R10: devoluciones de un pedido cancelado y de uno sin pago capturado → order_not_sale."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1,
              orders=[order("K-1", "C1", "2026-09-01T08:00:00Z", "10.00", status="cancelled"),
                      order("K-2", "C1", "2026-09-01T09:00:00Z", "10.00")],
              payments=[payment("K-1"), payment("K-2", status="failed")],
              customers=[customer("C1")])
    write_refunds(inbox, D1, [refund("R-1", "K-1", "2026-09-01T10:00:00Z", 1.0),
                              refund("R-2", "K-2", "2026-09-01T10:00:00Z", 1.0)])
    out = run_pipeline(tmp_path)
    assert metrics(out) == []
    assert rejected(out) == [("orders", "K-1", D1, "not_sale_cancelled"),
                             ("orders", "K-2", D1, "not_sale_unpaid"),
                             ("refunds", "R-1", D1, "order_not_sale"),
                             ("refunds", "R-2", D1, "order_not_sale")]


def test_currency_mismatch_and_unknown_currency(tmp_path):
    """R3, R8, R10: moneda fuera de fx_rates (pedido y devolución) y moneda distinta de la del pedido."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1,
              orders=[order("K-1", "C1", "2026-09-01T08:00:00Z", "10.00"),
                      order("K-2", "C1", "2026-09-01T09:00:00Z", "1000", currency="JPY")],
              payments=[payment("K-1"), payment("K-2")], customers=[customer("C1")])
    write_refunds(inbox, D1, [refund("R-1", "K-1", "2026-09-01T10:00:00Z", 3.0, "GBP"),
                              refund("R-2", "K-1", "2026-09-01T10:00:00Z", 500, "JPY"),
                              refund("R-3", "K-1", "2026-09-01T10:00:00Z", 1.0, "eur")])
    out = run_pipeline(tmp_path)
    assert values(metrics_by_key(out)[(D1, "C1")]) == ("ES", "1", "10.00", "1.00", "9.00", "1", D1)
    assert rejected(out) == [("orders", "K-2", D1, "unknown_currency"),
                             ("refunds", "R-1", D1, "currency_mismatch"),
                             ("refunds", "R-2", D1, "unknown_currency")]


def test_non_positive_amounts(tmp_path):
    """R3, R8: importe ≤ 0 en pedido y en devolución → invalid_record."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1,
              orders=[order("K-1", "C1", "2026-09-01T08:00:00Z", "10.00"),
                      order("K-2", "C1", "2026-09-01T09:00:00Z", "0.00")],
              payments=[payment("K-1"), payment("K-2")], customers=[customer("C1")])
    write_refunds(inbox, D1, [refund("R-1", "K-1", "2026-09-01T10:00:00Z", -5.0),
                              refund("R-2", "K-1", "2026-09-01T10:00:00Z", 0)])
    out = run_pipeline(tmp_path)
    assert values(metrics_by_key(out)[(D1, "C1")]) == ("ES", "1", "10.00", "0.00", "10.00", "0", D1)
    assert rejected(out) == [("orders", "K-2", D1, "invalid_record"),
                             ("refunds", "R-1", D1, "invalid_record"),
                             ("refunds", "R-2", D1, "invalid_record")]


@pytest.mark.parametrize("created, expected_date", [
    ("2026-09-04T22:30:00Z", "2026-09-05"),  # verano: UTC+2
    ("2026-12-01T22:30:00Z", "2026-12-01"),  # invierno: UTC+1 (un +2 fijo daría el 12-02)
])
def test_madrid_date_with_daylight_saving(tmp_path, created, expected_date):
    """R6: día natural en Europe/Madrid con la base de zonas horarias, no un desfase fijo."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1, orders=[order("K-1", "C1", created, "10.00")],
              payments=[payment("K-1")], customers=[customer("C1")])
    rows = metrics(run_pipeline(tmp_path))
    assert [(r["metric_date"], r["last_purchase_date"]) for r in rows] == [
        (expected_date, expected_date)]


def test_last_purchase_date_does_not_look_ahead(tmp_path):
    """R14 / E14: en una fila solo con devoluciones, la última compra ≤ metric_date."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1, orders=[order("K-1", "C1", "2026-09-01T08:00:00Z", "10.00")],
              payments=[payment("K-1")], customers=[customer("C1")])
    write_day(inbox, D3, orders=[order("K-2", "C1", "2026-09-03T08:00:00Z", "20.00")],
              payments=[payment("K-2")])
    write_refunds(inbox, D2, [refund("R-1", "K-1", "2026-09-02T10:00:00Z", 4.0)])
    rows = metrics_by_key(run_pipeline(tmp_path))
    assert values(rows[(D2, "C1")]) == ("ES", "0", "0.00", "4.00", "-4.00", "1", D1)
    assert rows[(D3, "C1")]["last_purchase_date"] == D3


def test_malformed_refunds_json_raises_input_error(tmp_path):
    """R1 / S7: un refunds.json que no es JSON detiene el pipeline nombrando el fichero."""
    from kivora import ingest

    inbox = tmp_path / "inbox"
    write_day(inbox, D1, customers=[customer("C1")])
    write_refunds(inbox, D1, "[{ esto no es json")
    with pytest.raises(ingest.InputError, match="refunds.json"):
        run_pipeline(tmp_path)


def test_day_without_refunds_or_empty_list(tmp_path):
    """R1 / S8: un día sin refunds.json o con [] no aporta devoluciones."""
    inbox = tmp_path / "inbox"
    write_day(inbox, D1, orders=[order("K-1", "C1", "2026-09-01T08:00:00Z", "10.00")],
              payments=[payment("K-1")], customers=[customer("C1")])
    write_refunds(inbox, D2, [])
    write_day(inbox, D3)
    out = run_pipeline(tmp_path)
    assert [values(r) for r in metrics(out)] == [("ES", "1", "10.00", "0.00", "10.00", "0", D1)]
    assert rejected(out) == []


def _sample_inbox(tmp_path):
    inbox = tmp_path / "inbox"
    write_day(inbox, D1,
              orders=[order("K-2", "C2", "2026-09-01T09:00:00Z", "7.35", currency="GBP"),
                      order("K-1", "C1", "2026-09-01T08:00:00Z", "10.00")],
              payments=[payment("K-1"), payment("K-2")],
              customers=[customer("C2", "GB"), customer("C1")])
    write_refunds(inbox, D2, [refund("R-9", "K-404", "2026-09-02T10:00:00Z", 1.0),
                              refund("R-1", "K-1", "2026-09-02T10:00:00Z", 2.5)])
    return inbox


NEW_OUTPUTS = ["daily_customer_metrics.csv", "rejected.csv", "quality_report.json"]


def test_outputs_are_deterministic(tmp_path):
    """R16: dos ejecuciones dan los mismos bytes; formato de §3.4."""
    inbox = _sample_inbox(tmp_path)
    run(inbox, REFERENCE, tmp_path / "a")
    run(inbox, REFERENCE, tmp_path / "b")
    for name in NEW_OUTPUTS:
        a = (tmp_path / "a" / name).read_bytes()
        assert a == (tmp_path / "b" / name).read_bytes(), name
        assert b"\r" not in a and not a.startswith(b"\xef\xbb\xbf"), name
    report = json.loads((tmp_path / "a" / "quality_report.json").read_text(encoding="utf-8"))
    assert [c["name"] for c in report["checks"]] == [
        "net_equals_gross_minus_refunded", "refunds_within_order_total", "unique_keys_and_orders"]
    assert (tmp_path / "a" / "quality_report.json").read_text(encoding="utf-8").endswith("}\n")


def _tree_hash(folder):
    digest = hashlib.sha256()
    for path in sorted(p for p in Path(folder).rglob("*") if p.is_file()):
        digest.update(path.relative_to(folder).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_inbox_is_not_modified(tmp_path):
    """El pipeline solo escribe en --out (spec §3)."""
    inbox = _sample_inbox(tmp_path)
    before = _tree_hash(inbox)
    out = run_pipeline(tmp_path)
    assert _tree_hash(inbox) == before
    for name in NEW_OUTPUTS:
        assert (out / name).exists(), name


# --- KIV-102: dos formatos de refunds.json (docs/specs/KIV-102/spec.md) ---------

def refund_v2(rid, oid, at, amount, currency="EUR", reason=None):
    """Formato nuevo: refund_amount en lugar de amount, y reason (texto o null)."""
    return {"refund_id": rid, "order_id": oid, "refunded_at": at, "refund_amount": amount,
            "currency": currency, "reason": reason}


def rejected_details(out):
    return {(r["record_id"], r["inbox_day"]): (r["reason"], r["detail"])
            for r in read_csv(out / "rejected.csv")}


def _one_sale(inbox, amount="10.00", currency="EUR", country="ES"):
    write_day(inbox, D1, orders=[order("K-1", "C1", "2026-09-01T08:00:00Z", amount, currency)],
              payments=[payment("K-1")], customers=[customer("C1", country)])


def test_new_format_refund_is_accepted(tmp_path):
    """R19, R20: refund_amount se usa como importe y se convierte a EUR igual que amount."""
    inbox = tmp_path / "inbox"
    _one_sale(inbox, "100.00", "USD", "US")
    write_refunds(inbox, D2, [refund_v2("R-1", "K-1", "2026-09-02T10:00:00Z", 36.65, "USD",
                                        "talla incorrecta")])
    out = run_pipeline(tmp_path)
    # 36.65 USD × 0.92 = 33.718 → 33.72
    assert values(metrics_by_key(out)[(D2, "C1")]) == ("US", "0", "0.00", "33.72", "-33.72", "1", D1)
    assert rejected(out) == []


def test_new_format_reason_null_is_accepted(tmp_path):
    """R20: reason null no invalida la devolución."""
    inbox = tmp_path / "inbox"
    _one_sale(inbox)
    write_refunds(inbox, D1, [refund_v2("R-1", "K-1", "2026-09-01T10:00:00Z", 3.0, reason=None)])
    out = run_pipeline(tmp_path)
    assert values(metrics_by_key(out)[(D1, "C1")]) == ("ES", "1", "10.00", "3.00", "7.00", "1", D1)
    assert rejected(out) == []


def test_mixed_formats_in_one_file(tmp_path):
    """R19: el formato se detecta por registro; un fichero puede mezclar los dos."""
    inbox = tmp_path / "inbox"
    _one_sale(inbox)
    write_refunds(inbox, D1, [refund("R-1", "K-1", "2026-09-01T10:00:00Z", 1.0),
                              refund_v2("R-2", "K-1", "2026-09-01T11:00:00Z", 2.0, reason="x")])
    out = run_pipeline(tmp_path)
    assert values(metrics_by_key(out)[(D1, "C1")]) == ("ES", "1", "10.00", "3.00", "7.00", "2", D1)
    assert rejected(out) == []


def test_same_refund_in_both_formats_is_one_refund(tmp_path):
    """R9: la misma devolución en los dos formatos es una copia; con otro importe, un conflicto."""
    inbox = tmp_path / "inbox"
    _one_sale(inbox)
    write_refunds(inbox, D1, [refund("R-1", "K-1", "2026-09-01T10:00:00Z", 2.0),
                              refund("R-2", "K-1", "2026-09-01T11:00:00Z", 1.0)])
    write_refunds(inbox, D2, [refund_v2("R-1", "K-1", "2026-09-01T10:00:00Z", 2.0,
                                        reason="talla incorrecta"),
                              refund_v2("R-2", "K-1", "2026-09-01T11:00:00Z", 4.0)])
    out = run_pipeline(tmp_path)
    assert values(metrics_by_key(out)[(D1, "C1")]) == ("ES", "1", "10.00", "2.00", "8.00", "1", D1)
    assert rejected(out) == [("refunds", "R-1", D2, "duplicate_refund"),
                             ("refunds", "R-2", D1, "conflicting_duplicate"),
                             ("refunds", "R-2", D2, "conflicting_duplicate")]


def test_reason_does_not_count_for_duplicates(tmp_path):
    """R9: dos copias que solo difieren en reason son la misma devolución."""
    inbox = tmp_path / "inbox"
    _one_sale(inbox)
    write_refunds(inbox, D1, [refund_v2("R-1", "K-1", "2026-09-01T10:00:00Z", 2.0, reason=None)])
    write_refunds(inbox, D2, [refund_v2("R-1", "K-1", "2026-09-01T10:00:00Z", 2.0,
                                        reason="producto defectuoso")])
    out = run_pipeline(tmp_path)
    assert values(metrics_by_key(out)[(D1, "C1")]) == ("ES", "1", "10.00", "2.00", "8.00", "1", D1)
    assert rejected(out) == [("refunds", "R-1", D2, "duplicate_refund")]


def test_both_amount_fields_is_invalid_record(tmp_path):
    """R8, R19: amount y refund_amount a la vez → invalid_record, aunque coincidan."""
    inbox = tmp_path / "inbox"
    _one_sale(inbox)
    both = {**refund("R-1", "K-1", "2026-09-01T10:00:00Z", 1.0), "refund_amount": 1.0}
    write_refunds(inbox, D1, [both])
    out = run_pipeline(tmp_path)
    assert values(metrics_by_key(out)[(D1, "C1")]) == ("ES", "1", "10.00", "0.00", "10.00", "0", D1)
    reason, detail = rejected_details(out)[("R-1", D1)]
    assert reason == "invalid_record"
    assert "amount y refund_amount" in detail, detail


def test_missing_or_bad_amount_names_the_field(tmp_path):
    """R8: sin importe, o refund_amount ≤ 0 → invalid_record; el detail nombra el campo."""
    inbox = tmp_path / "inbox"
    _one_sale(inbox)
    missing = {"refund_id": "R-1", "order_id": "K-1", "refunded_at": "2026-09-01T10:00:00Z",
               "currency": "EUR", "reason": None}
    write_refunds(inbox, D1, [missing,
                              refund_v2("R-2", "K-1", "2026-09-01T10:00:00Z", -5.0),
                              refund("R-3", "K-1", "2026-09-01T10:00:00Z", 0)])
    out = run_pipeline(tmp_path)
    details = rejected_details(out)
    assert {k: v[0] for k, v in details.items()} == {
        ("R-1", D1): "invalid_record", ("R-2", D1): "invalid_record",
        ("R-3", D1): "invalid_record"}
    assert "falta el importe" in details[("R-1", D1)][1], details
    assert details[("R-2", D1)][1].split(": ", 1)[1].startswith("refund_amount "), details
    assert details[("R-3", D1)][1].split(": ", 1)[1].startswith("amount "), details


def test_reason_only_in_warehouse(tmp_path):
    """R21: reason se guarda en raw_refunds de warehouse.db y no aparece en ningún CSV."""
    import sqlite3

    inbox = tmp_path / "inbox"
    _one_sale(inbox)
    write_refunds(inbox, D1, [refund("R-1", "K-1", "2026-09-01T10:00:00Z", 1.0),
                              refund_v2("R-2", "K-1", "2026-09-01T11:00:00Z", 2.0, reason=None),
                              refund_v2("R-3", "K-1", "2026-09-01T12:00:00Z", 3.0,
                                        reason="cambio de opinión")])
    out = run_pipeline(tmp_path)
    conn = sqlite3.connect(out / "warehouse.db")
    try:
        stored = conn.execute(
            "SELECT refund_id, amount, reason FROM raw_refunds ORDER BY refund_id").fetchall()
    finally:
        conn.close()
    assert stored == [("R-1", "1.0", None), ("R-2", "2.0", None),
                      ("R-3", "3.0", "cambio de opinión")]
    for csv_file in out.glob("*.csv"):
        assert "cambio de opinión" not in csv_file.read_text(encoding="utf-8"), csv_file.name
    assert values(metrics_by_key(out)[(D1, "C1")]) == ("ES", "1", "10.00", "6.00", "4.00", "3", D1)


# --- revisión independiente (docs/review.md: H1, H2, H3) -------------------------

REFUND_TEXT = ('[{{"refund_id": "R-1", "order_id": "K-1", "refunded_at": "2026-09-01T10:00:00Z", '
               '"{key}": {amount}, "currency": "EUR"}}]')


@pytest.mark.parametrize("second_key, second_amount", [
    ("amount", "2.00"),          # mismo formato, otro número de decimales
    ("refund_amount", "2.00"),   # los dos formatos (S13)
    ("refund_amount", "2"),
])
def test_same_amount_with_different_decimals_is_a_copy(tmp_path, second_key, second_amount):
    """H1 / KIV-102 R9: el importe se compara como decimal; 2.0, 2.00 y 2 son el mismo importe."""
    inbox = tmp_path / "inbox"
    _one_sale(inbox)
    write_refunds(inbox, D1, REFUND_TEXT.format(key="amount", amount="2.0"))
    write_refunds(inbox, D2, REFUND_TEXT.format(key=second_key, amount=second_amount))
    out = run_pipeline(tmp_path)
    assert values(metrics_by_key(out)[(D1, "C1")]) == ("ES", "1", "10.00", "2.00", "8.00", "1", D1)
    assert rejected(out) == [("refunds", "R-1", D2, "duplicate_refund")]


def test_different_amount_is_still_a_conflict(tmp_path):
    """H1 / R9: comparar como decimal no iguala importes distintos (2.0 frente a 2.01)."""
    inbox = tmp_path / "inbox"
    _one_sale(inbox)
    write_refunds(inbox, D1, REFUND_TEXT.format(key="amount", amount="2.0"))
    write_refunds(inbox, D2, REFUND_TEXT.format(key="refund_amount", amount="2.01"))
    out = run_pipeline(tmp_path)
    assert rejected(out) == [("refunds", "R-1", D1, "conflicting_duplicate"),
                             ("refunds", "R-1", D2, "conflicting_duplicate")]


@pytest.mark.parametrize("newer, older", [
    ("2026-09-01T10:00:00.500Z", "2026-09-01T10:00:00Z"),       # fracciones de segundo (S14)
    ("2026-09-01T11:00:00Z", "2026-09-01T12:30:00+02:00"),      # desfase: 12:30+02 = 10:30Z
])
def test_latest_version_compares_updated_at_as_instants(tmp_path, newer, older):
    """H2 / R2: updated_at se compara como instante, no como texto. La versión más nueva
    llega en la carpeta anterior, para que el desempate por carpeta no la salve."""
    inbox = tmp_path / "inbox"
    created = "2026-09-01T08:00:00Z"
    write_day(inbox, D1, orders=[order("K-1", "C1", created, "12.00", updated=newer)],
              payments=[payment("K-1")], customers=[customer("C1")])
    write_day(inbox, D2, orders=[order("K-1", "C1", created, "99.00", updated=older)])
    rows = metrics_by_key(run_pipeline(tmp_path))
    assert rows[(D1, "C1")]["gross_amount"] == "12.00"


def test_quality_checks_detect_bad_data():
    """H3 / R15: cada control cuenta los registros que lo incumplen y sale con passed false."""
    from decimal import Decimal as Dec

    from kivora.customer_metrics import quality_checks

    def row(day, cid, gross, refunded, net):
        return {"metric_date": day, "customer_id": cid, "gross_amount": Dec(gross),
                "refunded_amount": Dec(refunded), "net_amount": Dec(net)}

    rows = [row(D1, "C1", "10.00", "2.00", "8.00"),
            row(D1, "C2", "10.00", "2.00", "9.00"),   # neto mal calculado
            row(D1, "C2", "10.00", "0.00", "10.00"),  # clave repetida
            row(D2, "C3", "5.00", "0.00", "5.00")]
    sales = {"K-1": {"total": Dec("10.00")}, "K-2": {"total": Dec("5.00")}}
    accepted = [{"order_id": "K-1", "amount": Dec("6.00")},
                {"order_id": "K-1", "amount": Dec("5.00")},   # 11.00 > 10.00
                {"order_id": "K-2", "amount": Dec("5.00")}]   # justo el total: no incumple
    aggregated = ["K-1", "K-2", "K-2"]                          # K-2 agregado dos veces
    checks = quality_checks(rows, aggregated, accepted, sales)
    assert checks == [
        {"name": "net_equals_gross_minus_refunded", "passed": False, "failed_records": 1},
        {"name": "refunds_within_order_total", "passed": False, "failed_records": 1},
        {"name": "unique_keys_and_orders", "passed": False, "failed_records": 2}]
    assert all(c["passed"] for c in quality_checks(rows[:1], ["K-1"], accepted[:1], sales))


def test_failed_check_still_exits_with_zero(tmp_path, monkeypatch, capsys):
    """H3 / R17: con entrada legible, el pipeline termina con 0 aunque falle un control,
    y el fallo queda en quality_report.json."""
    from kivora import customer_metrics
    from kivora.__main__ import main

    def failing(*_):
        return [{"name": name, "passed": name != "refunds_within_order_total",
                 "failed_records": 3 if name == "refunds_within_order_total" else 0}
                for name in customer_metrics.CHECK_NAMES]

    monkeypatch.setattr(customer_metrics, "quality_checks", failing)
    _one_sale(tmp_path / "inbox")
    out = tmp_path / "out"
    code = main(["--inbox", str(tmp_path / "inbox"), "--reference", str(REFERENCE),
                 "--out", str(out)])
    assert code == 0
    assert quality(out)["refunds_within_order_total"] == {
        "name": "refunds_within_order_total", "passed": False, "failed_records": 3}
    assert "AVISO control refunds_within_order_total: 3" in capsys.readouterr().out
