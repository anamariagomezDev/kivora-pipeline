"""Basic checks on output/ (python tasks.py check)."""

import csv
import json
import sys
from pathlib import Path

OUTPUT = Path("output")
EXPECTED = {
    "daily_sales.csv": ["sales_date", "country", "orders_count", "gross_amount"],
    "top_customers.csv": ["customer_id", "orders_count", "gross_amount"],
    # KIV-101 (docs/specs/KIV-101/spec.md §3). net_amount may be negative (D1).
    "daily_customer_metrics.csv": ["metric_date", "customer_id", "country", "orders_count",
                                   "gross_amount", "refunded_amount", "net_amount",
                                   "refunds_count", "last_purchase_date"],
    "rejected.csv": ["source", "record_id", "reason", "inbox_day", "detail"],
}
QUALITY_REPORT = "quality_report.json"
CHECK_NAMES = ["net_equals_gross_minus_refunded", "refunds_within_order_total",
               "unique_keys_and_orders"]


def check_quality_report(path):
    """Structure only: the three checks, in order, with their three keys."""
    if not path.exists():
        return [f"falta {path}: ejecuta antes python tasks.py run"]
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        checks = report["checks"]
        names = [c["name"] for c in checks]
    except (ValueError, KeyError, TypeError) as exc:
        return [f"{path.name}: estructura no válida ({exc})"]
    problems = []
    if names != CHECK_NAMES:
        problems.append(f"{path.name}: controles {names}, se esperaban {CHECK_NAMES}")
    for c in checks:
        if not isinstance(c.get("passed"), bool) or not isinstance(c.get("failed_records"), int):
            problems.append(f"{path.name}: {c.get('name')}: passed/failed_records no válidos")
    return problems


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    problems = []
    for name, columns in EXPECTED.items():
        path = OUTPUT / name
        if not path.exists():
            problems.append(f"falta {path}: ejecuta antes python tasks.py run")
            continue
        with open(path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in columns if c not in (reader.fieldnames or [])]
            if missing:
                problems.append(f"{name}: faltan columnas {missing}")
                continue
            if "gross_amount" not in columns:
                continue
            for line, row in enumerate(reader, start=2):
                if float(row["gross_amount"]) < 0:
                    problems.append(f"{name}:{line}: gross_amount negativo")
    problems += check_quality_report(OUTPUT / QUALITY_REPORT)
    for problem in problems:
        print(f"FAIL  {problem}")
    if problems:
        return 1
    print("OK: output/ tiene los ficheros y columnas esperados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
