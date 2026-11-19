"""KIV-101 outputs with the format of spec §3.4 (UTF-8 without BOM, '\\n', two decimals)."""

import csv
import json
from decimal import Decimal
from pathlib import Path

from kivora.customer_metrics import METRIC_COLUMNS

REJECTED_COLUMNS = ["source", "record_id", "reason", "inbox_day", "detail"]


def _cell(value):
    return f"{value:.2f}" if isinstance(value, Decimal) else str(value)


def _table(rows, columns):
    return [[_cell(row[c]) for c in columns] for row in rows]


def _write_csv(path, columns, values):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(values)


def _save(conn, table, columns, values):
    """Same table in warehouse.db, amounts as TEXT (never REAL)."""
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(f"CREATE TABLE {table} ({', '.join(c + ' TEXT' for c in columns)})")
    conn.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' for _ in columns)})", values)
    conn.commit()


def write_all(conn, out, rows, rejected, checks):
    out = Path(out)
    metrics = _table(rows, METRIC_COLUMNS)
    rejections = _table(rejected, REJECTED_COLUMNS)
    _write_csv(out / "daily_customer_metrics.csv", METRIC_COLUMNS, metrics)
    _write_csv(out / "rejected.csv", REJECTED_COLUMNS, rejections)
    report = {"checks": [{"name": c["name"], "passed": c["passed"],
                          "failed_records": c["failed_records"]} for c in checks]}
    (out / "quality_report.json").write_bytes(
        (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    _save(conn, "daily_customer_metrics", METRIC_COLUMNS, metrics)
    _save(conn, "rejected", REJECTED_COLUMNS, rejections)
