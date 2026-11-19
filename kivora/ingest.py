"""Load the raw sources into SQLite, as text, without cleaning anything."""

import csv
import json
from decimal import Decimal
from pathlib import Path

SOURCES = {
    "orders": ["order_id", "customer_id", "created_at", "updated_at", "status",
               "currency", "total_amount"],
    "customers": ["customer_id", "name", "country", "signup_date"],
    "payments": ["payment_id", "order_id", "paid_at", "method", "status", "amount"],
}
# Normalised refund (KIV-102 R20): `amount` is the refund amount whatever key it came in
# (`amount` in the old format, `refund_amount` in the new one); `reason` only exists in the
# new format and is NULL when absent or null.
REFUND_FIELDS = ["refund_id", "order_id", "refunded_at", "amount", "currency", "reason"]
AMOUNT_KEYS = ("amount", "refund_amount")
# `_format` (KIV-102 R19): the amount key the object brings: amount, refund_amount, both, none.
# `_raw`: the whole JSON object, canonical, kept only as a trace (R9 compares REFUND_CONTENT).
REFUND_COLUMNS = REFUND_FIELDS + ["_format", "_raw"]


class InputError(Exception):
    """An input file that cannot be read (spec R1, A19). The message names the file."""


def _create(conn, table, columns):
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(f"CREATE TABLE {table} ({', '.join(c + ' TEXT' for c in columns)})")


def _as_text(value):
    """JSON value -> TEXT, keeping decimals exactly as written (no float)."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, (int, Decimal)):
        return str(value)
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


def normalize_refund(item):
    """KIV-102 R19, R20: one JSON refund, in either format -> row of REFUND_COLUMNS.
    The format is decided by the keys of this object, never by its day or file."""
    present = [key for key in AMOUNT_KEYS if key in item]
    if len(present) == 1:
        fmt, amount = present[0], item[present[0]]
    else:
        fmt, amount = ("both" if present else "none"), None
    values = {**item, "amount": amount, "reason": item.get("reason")}
    raw = json.dumps(item, sort_keys=True, default=str, ensure_ascii=False)
    return [_as_text(values.get(f)) for f in REFUND_FIELDS] + [fmt, raw]


def read_refunds(path):
    """Rows of refunds.json: missing file or [] -> no rows; invalid JSON -> InputError."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"), parse_float=Decimal)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InputError(f"{path}: no es JSON válido ({exc})") from exc
    if not isinstance(data, list):
        raise InputError(f"{path}: se esperaba una lista de devoluciones")
    rows = []
    for pos, item in enumerate(data):
        if not isinstance(item, dict):
            raise InputError(f"{path}: el elemento {pos} no es un objeto")
        rows.append(normalize_refund(item))
    return rows


def load_inbox(conn, inbox):
    """One raw_<source> table per source, with the day folder in `_day` and the
    position of the row (or JSON element) in its file in `_pos`."""
    for name, columns in SOURCES.items():
        _create(conn, f"raw_{name}", columns + ["_day", "_pos"])
    _create(conn, "raw_refunds", REFUND_COLUMNS + ["_day", "_pos"])
    days = sorted(p for p in Path(inbox).iterdir() if p.is_dir())
    for day in days:
        for name, columns in SOURCES.items():
            path = day / f"{name}.csv"
            if not path.exists():
                continue
            with open(path, encoding="utf-8-sig", newline="") as fh:
                rows = [[row[c] for c in columns] + [day.name, pos]
                        for pos, row in enumerate(csv.DictReader(fh))]
            placeholders = ", ".join("?" for _ in range(len(columns) + 2))
            conn.executemany(f"INSERT INTO raw_{name} VALUES ({placeholders})", rows)
        refunds = [row + [day.name, pos] for pos, row in enumerate(read_refunds(day / "refunds.json"))]
        placeholders = ", ".join("?" for _ in range(len(REFUND_COLUMNS) + 2))
        conn.executemany(f"INSERT INTO raw_refunds VALUES ({placeholders})", refunds)
    conn.commit()
    return [d.name for d in days]


def load_reference(conn, reference):
    _create(conn, "ref_fx_rates", ["currency", "rate_to_eur"])
    with open(Path(reference) / "fx_rates.csv", encoding="utf-8-sig", newline="") as fh:
        rows = [[row["currency"], row["rate_to_eur"]] for row in csv.DictReader(fh)]
    conn.executemany("INSERT INTO ref_fx_rates VALUES (?, ?)", rows)
    conn.commit()
