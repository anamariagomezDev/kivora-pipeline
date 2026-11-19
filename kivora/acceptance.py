"""Oráculo de KIV-101 (python tasks.py acceptance).

Comprueba los escenarios de docs/specs/KIV-101/spec.md §5 y §6:

0. Copia a una carpeta temporal solo los días 2026-09-01 .. 2026-09-07 de data/inbox/.
1. Ejecuta `python -m kivora` dos veces sobre esa copia (run1 y run2).
2. Columnas de los tres ficheros nuevos.
3. Filas literales de E1–E17, ausencias de E2 y E11, totales y rechazos de E18.
4. Diferencial completo contra docs/specs/KIV-101/reference_calc.py sobre la misma copia.
5. Escenarios sintéticos S1–S8, en carpetas temporales.
6. E19: determinismo (SHA-256) y entrada sin cambios.

Imprime PASS/FAIL por escenario y sale con 0 solo si pasan todos. Es el único módulo
de kivora/ que contiene ids de la muestra.
"""

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "data" / "inbox"
REFERENCE = ROOT / "data" / "reference"
REFERENCE_CALC = ROOT / "docs" / "specs" / "KIV-101" / "reference_calc.py"
DAYS = [f"2026-09-0{d}" for d in range(1, 8)]
NEW_OUTPUTS = ["daily_customer_metrics.csv", "rejected.csv", "quality_report.json"]
OLD_OUTPUTS = ["daily_sales.csv", "top_customers.csv", "warehouse.db"]

METRIC_COLUMNS = ["metric_date", "customer_id", "country", "orders_count", "gross_amount",
                  "refunded_amount", "net_amount", "refunds_count", "last_purchase_date"]
REJECTED_COLUMNS = ["source", "record_id", "reason", "inbox_day", "detail"]
CHECK_NAMES = ["net_equals_gross_minus_refunded", "refunds_within_order_total",
               "unique_keys_and_orders"]

# Filas esperadas (spec §5). Las que acaban en "," se comparan como prefijo.
ROWS = {
    "E1": ["2026-09-01,C009,ES,1,45.90,0.00,45.90,0,2026-09-01"],
    "E2": ["2026-09-02,C021,GB,1,78.68,0.00,78.68,0,2026-09-02",
           "2026-09-04,C021,GB,1,203.83,39.34,164.49,1,2026-09-04"],
    "E3": ["2026-09-04,C014,ES,2,244.19,0.00,244.19,0,2026-09-04"],
    "E4": ["2026-09-04,C010,ES,2,258.32,0.00,258.32,0,2026-09-04"],
    "E5": ["2026-09-01,C007,UNKNOWN,2,246.66,0.00,246.66,0,2026-09-01",
           "2026-09-04,C032,UNKNOWN,1,139.44,0.00,139.44,0,2026-09-04"],
    "E6": ["2026-09-04,C011,ES,1,49.04,20.00,29.04,1,2026-09-04"],
    "E7": ["2026-09-04,C011,ES,1,49.04,20.00,29.04,1,2026-09-04",
           "2026-09-06,C011,ES,2,164.64,15.50,149.14,1,2026-09-06"],
    "E9": ["2026-09-05,C022,US,2,85.59,55.20,30.39,1,2026-09-05",
           "2026-09-07,C022,US,1,56.19,0.00,56.19,0,2026-09-07"],
    "E10": ["2026-09-05,C028,ES,1,39.21,12.00,27.21,1,2026-09-05"],
    "E12": ["2026-09-04,C002,ES,2,405.40,",
            "2026-09-05,C002,ES,2,263.75,0.00,263.75,0,2026-09-05",
            "2026-09-07,C027,ES,3,409.09,0.00,409.09,0,2026-09-07"],
    "E13": ["2026-09-07,C020,ES,0,0.00,20.00,-20.00,1,2026-09-06"],
    "E14": ["2026-09-04,C020,ES,0,0.00,21.83,-21.83,1,2026-09-01"],
    "E15": ["2026-09-04,C018,GB,1,245.70,0.00,245.70,0,2026-09-04",
            "2026-09-06,C006,ES,1,134.50,0.00,134.50,0,2026-09-06"],
    "E16": ["2026-09-02,C024,ES,1,197.51,0.00,197.51,0,2026-09-02"],
    "E17": ["2026-09-04,C022,US,3,325.17,0.00,325.17,0,2026-09-04"],
}
ABSENT = {"E2": ["2026-09-03,C021"], "E11": ["2026-09-05,C014"]}
# (source, record_id, inbox_day, reason)
REJECTED_IN = {
    "E3": [("orders", "K-10149", "2026-09-05", "not_sale_cancelled")],
    "E8": [("refunds", "R-1003", "2026-09-05", "order_not_found")],
    "E9": [("refunds", "R-1009", "2026-09-07", "refund_exceeds_order")],
    "E10": [("refunds", "R-1006", "2026-09-06", "duplicate_refund")],
    "E11": [("refunds", "R-1005", "2026-09-05", "order_not_sale")],
    "E16": [("orders", "K-10062", "2026-09-02", "not_sale_unpaid")],
}
NOT_REJECTED = {"E1": "K-10059", "E4": "K-10151"}
E18_TOTALS = {"ventas": 156, "bruto": Decimal("18490.74"), "devuelto": Decimal("1264.19"),
              "neto": Decimal("17226.55"), "filas": 126, "solo_devolucion": 11,
              "neto_negativo": 12}
E18_REJECTED = sorted(t for ts in REJECTED_IN.values() for t in ts)

RESULTS = []


def record(scenario, ok, message=""):
    RESULTS.append((scenario, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {scenario}" + (f": {message}" if message else ""))


def scenario(name):
    """Decorador: un escenario que lanza AssertionError (u otra excepción) es FAIL."""
    def wrap(function):
        def inner(*args):
            try:
                function(*args)
            except AssertionError as exc:
                record(name, False, str(exc) or "aserción fallida")
            except Exception as exc:  # el oráculo no debe abortar por un escenario
                record(name, False, f"{type(exc).__name__}: {exc}")
            else:
                record(name, True)
        return inner
    return wrap


# --- utilidades ------------------------------------------------------------

def env():
    return {**os.environ, "PYTHONUTF8": "1"}


def run_kivora(inbox, out):
    return subprocess.run(
        [sys.executable, "-m", "kivora", "--inbox", str(inbox), "--reference", str(REFERENCE),
         "--out", str(out)], cwd=ROOT, env=env(), capture_output=True, text=True,
        encoding="utf-8")


def run_reference(inbox, *args):
    result = subprocess.run([sys.executable, "-I", str(REFERENCE_CALC), str(inbox),
                             str(REFERENCE), *args], cwd=ROOT, env=env(),
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, f"reference_calc.py falló: {result.stderr.strip()}"
    return result.stdout.splitlines()


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def metric_lines(out):
    lines = (Path(out) / "daily_customer_metrics.csv").read_text(encoding="utf-8").split("\n")
    return [line for line in lines[1:] if line]


def rejected_tuples(out):
    return sorted((r["source"], r["record_id"], r["inbox_day"], r["reason"])
                  for r in read_csv(Path(out) / "rejected.csv"))


def quality(out):
    return json.loads((Path(out) / "quality_report.json").read_text(encoding="utf-8"))


def tree_hash(folder):
    digest = hashlib.sha256()
    for path in sorted(p for p in Path(folder).rglob("*") if p.is_file()):
        digest.update(path.relative_to(folder).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def totals(lines):
    rows = [line.split(",") for line in lines]
    return {"ventas": sum(int(r[3]) for r in rows),
            "bruto": sum((Decimal(r[4]) for r in rows), Decimal("0")),
            "devuelto": sum((Decimal(r[5]) for r in rows), Decimal("0")),
            "neto": sum((Decimal(r[6]) for r in rows), Decimal("0")),
            "filas": len(rows),
            "solo_devolucion": sum(1 for r in rows if r[3] == "0"),
            "neto_negativo": sum(1 for r in rows if Decimal(r[6]) < 0)}


def reference_rejected(summary_lines):
    # "rejected <source> <record_id> <inbox_day> <reason>"; record_id puede estar vacío
    return sorted(tuple(line.split(" ")[1:5]) for line in summary_lines
                  if line.startswith("rejected "))


# --- escenarios con los datos reales (E1–E18) ------------------------------

def check_literal_scenarios(lines, rejected, label=""):
    """E1–E18 sobre unas filas de métricas y unos rechazos (de la salida o de la referencia)."""
    keyed = {",".join(line.split(",")[:2]): line for line in lines}
    ids = sorted(set(ROWS) | set(ABSENT) | set(REJECTED_IN) | set(NOT_REJECTED),
                 key=lambda s: int(s[1:]))
    for sid in ids:
        @scenario(f"{sid}{label}")
        def check():
            for expected in ROWS.get(sid, []):
                key = ",".join(expected.split(",")[:2])
                got = keyed.get(key)
                assert got is not None, f"falta la fila {key}"
                if expected.endswith(","):
                    assert got.startswith(expected), f"{got!r} no empieza por {expected!r}"
                else:
                    assert got == expected, f"{got!r} != {expected!r}"
            for key in ABSENT.get(sid, []):
                assert key not in keyed, f"no debería existir la fila {key}: {keyed[key]!r}"
            for item in REJECTED_IN.get(sid, []):
                assert item in rejected, f"falta en rejected.csv: {item}"
            if sid in NOT_REJECTED:
                bad = [r for r in rejected if r[1] == NOT_REJECTED[sid]]
                assert not bad, f"{NOT_REJECTED[sid]} no debería estar en rejected.csv: {bad}"
        check()

    @scenario(f"E18{label}")
    def e18():
        got = totals(lines)
        assert got == E18_TOTALS, f"totales {got} != {E18_TOTALS}"
        assert rejected == E18_REJECTED, f"rechazos {rejected} != {E18_REJECTED}"
    e18()


def check_outputs(run1, run2, result1, result2, inbox_copy_hash_before, inbox_copy,
                  repo_inbox_hash_before):
    @scenario("ejecución")
    def execution():
        for name, result in (("run1", result1), ("run2", result2)):
            assert result.returncode == 0, (
                f"{name}: código {result.returncode}: {result.stderr.strip()[-500:]}")
    execution()

    @scenario("columnas")
    def columns():
        for name in NEW_OUTPUTS:
            assert (run1 / name).exists(), f"falta {name}"
        header = (run1 / "daily_customer_metrics.csv").read_text(encoding="utf-8").split("\n")[0]
        assert header == ",".join(METRIC_COLUMNS), f"cabecera de métricas: {header!r}"
        header = (run1 / "rejected.csv").read_text(encoding="utf-8").split("\n")[0]
        assert header.split(",") == REJECTED_COLUMNS, (
            f"cabecera de rejected.csv: {header!r}")
        report = quality(run1)
        assert list(report) == ["checks"], f"claves de quality_report.json: {list(report)}"
        assert [c["name"] for c in report["checks"]] == CHECK_NAMES
        for check in report["checks"]:
            assert list(check) == ["name", "passed", "failed_records"], f"claves: {list(check)}"
    columns()

    if not all((run1 / name).exists() for name in NEW_OUTPUTS):
        record("E1–E19", False, "sin ficheros de salida no se pueden comprobar los escenarios")
        return

    lines, rejected = metric_lines(run1), rejected_tuples(run1)
    check_literal_scenarios(lines, rejected)

    @scenario("E18 (controles)")
    def e18_checks():
        for check in quality(run1)["checks"]:
            assert check["passed"] is True and check["failed_records"] == 0, f"{check}"
    e18_checks()

    @scenario("diferencial con reference_calc.py")
    def differential():
        expected = run_reference(inbox_copy)
        assert lines == expected, (
            f"métricas distintas: solo en la salida {sorted(set(lines) - set(expected))[:5]}, "
            f"solo en la referencia {sorted(set(expected) - set(lines))[:5]}")
        expected_rejected = reference_rejected(run_reference(inbox_copy, "--summary"))
        assert rejected == expected_rejected, f"rechazos {rejected} != {expected_rejected}"
    differential()

    @scenario("E19")
    def e19():
        for name in NEW_OUTPUTS:
            assert sha256(run1 / name) == sha256(run2 / name), f"{name} distinto entre ejecuciones"
            raw = (run1 / name).read_bytes()
            assert b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf"), f"{name}: formato"
        for name in OLD_OUTPUTS:
            assert (run1 / name).exists(), f"falta {name}"
        assert tree_hash(inbox_copy) == inbox_copy_hash_before, "la copia del inbox ha cambiado"
        assert tree_hash(INBOX) == repo_inbox_hash_before, "data/inbox/ ha cambiado"
    e19()


def self_check_reference(inbox_copy):
    """Valida el propio oráculo: E1–E18 deben pasar también sobre reference_calc.py."""
    lines = run_reference(inbox_copy)
    rejected = reference_rejected(run_reference(inbox_copy, "--summary"))
    check_literal_scenarios(lines, rejected, label=" [referencia]")


# --- escenarios sintéticos (S1–S8) -----------------------------------------

ORDER_FIELDS = ["order_id", "customer_id", "created_at", "updated_at", "status", "currency",
                "total_amount"]
PAYMENT_FIELDS = ["payment_id", "order_id", "paid_at", "method", "status", "amount"]
CUSTOMER_FIELDS = ["customer_id", "name", "country", "signup_date"]


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(fields)
        writer.writerows(rows)


def write_day(inbox, day, orders=(), customers=(), refunds=None):
    folder = Path(inbox) / day
    folder.mkdir(parents=True, exist_ok=True)
    write_csv(folder / "orders.csv", ORDER_FIELDS,
              [[o, c, at, at, "confirmed", cur, amt] for o, c, at, cur, amt in orders])
    write_csv(folder / "payments.csv", PAYMENT_FIELDS,
              [[f"P-{o}", o, at, "card", "captured", amt] for o, c, at, cur, amt in orders])
    write_csv(folder / "customers.csv", CUSTOMER_FIELDS, customers)
    if refunds is not None:
        text = refunds if isinstance(refunds, str) else json.dumps(refunds, indent=2)
        (folder / "refunds.json").write_text(text, encoding="utf-8")


def rf(rid, oid, at, amount, currency):
    return {"refund_id": rid, "order_id": oid, "refunded_at": at, "amount": amount,
            "currency": currency}


def synthetic(tmp):
    d1, d2, d3 = "2026-09-01", "2026-09-02", "2026-09-03"
    c1 = [["C1", "Cliente Uno", "ES", "2025-01-01"]]

    # Base S
    base_s = tmp / "S" / "inbox"
    write_day(base_s, d1,
              orders=[("K-1", "C1", "2026-09-01T10:00:00Z", "EUR", "10.00"),
                      ("K-2", "C1", "2026-09-01T11:00:00Z", "JPY", "1000"),
                      ("K-3", "C1", "2026-09-01T12:00:00Z", "EUR", "0.00"),
                      ("K-4", "", "2026-09-01T13:00:00Z", "EUR", "15.00"),
                      ("K-5", "C9", "2026-09-01T14:00:00Z", "EUR", "20.00")],
              customers=c1,
              refunds=[rf("R-2", "K-1", "2026-09-01T15:00:00Z", 500, "JPY"),
                       rf("R-3", "K-1", "2026-09-01T15:00:00Z", -5.0, "EUR"),
                       rf("R-4", "", "2026-09-01T15:00:00Z", 3.0, "EUR"),
                       rf("", "K-1", "2026-09-01T16:00:00Z", 1.0, "EUR"),
                       rf("  ", "K-1", "2026-09-01T16:10:00Z", 2.0, "EUR")])
    out_s = tmp / "S" / "out"
    result = run_kivora(base_s, out_s)
    ok_s = result.returncode == 0 and (out_s / "rejected.csv").exists()
    rej = rejected_tuples(out_s) if ok_s else []
    lines = metric_lines(out_s) if ok_s else []

    def need_s():
        assert ok_s, (f"código {result.returncode}, rejected.csv "
                      f"{'existe' if (out_s / 'rejected.csv').exists() else 'no existe'}: "
                      f"{result.stderr.strip()[-300:]}")

    @scenario("S1")
    def s1():
        need_s()
        for item in [("orders", "K-2", d1, "unknown_currency"),
                     ("refunds", "R-2", d1, "unknown_currency")]:
            assert item in rej, f"falta {item}"
    s1()

    @scenario("S2")
    def s2():
        need_s()
        for item in [("orders", "K-3", d1, "invalid_record"),
                     ("refunds", "R-3", d1, "invalid_record")]:
            assert item in rej, f"falta {item}"
    s2()

    @scenario("S3")
    def s3():
        need_s()
        for item in [("orders", "K-4", d1, "invalid_record"),
                     ("refunds", "R-4", d1, "invalid_record")]:
            assert item in rej, f"falta {item}"
        empty = [r for r in rej if r[0] == "refunds" and r[1] == ""]
        assert empty == [("refunds", "", d1, "invalid_record")] * 2, f"sin refund_id: {empty}"
    s3()

    @scenario("S4")
    def s4():
        need_s()
        assert "2026-09-01,C9,UNKNOWN,1,20.00,0.00,20.00,0,2026-09-01" in lines, f"{lines}"
    s4()

    @scenario("S1–S4 (conjunto)")
    def s_all():
        need_s()
        assert lines == ["2026-09-01,C1,ES,1,10.00,0.00,10.00,0,2026-09-01",
                         "2026-09-01,C9,UNKNOWN,1,20.00,0.00,20.00,0,2026-09-01"], f"{lines}"
        assert len(rej) == 8, f"{len(rej)} rechazos: {rej}"
    s_all()

    # Base T
    base_t = tmp / "T" / "inbox"
    write_day(base_t, d1, orders=[("K-1", "C1", "2026-09-01T10:00:00Z", "EUR", "10.00")],
              customers=c1,
              refunds=[rf("R-5", "K-1", "2026-09-01T15:00:00Z", 2.0, "EUR"),
                       rf("R-6", "K-1", "2026-09-01T15:00:00Z", 3.0, "GBP")])
    write_day(base_t, d2, refunds=[rf("R-5", "K-1", "2026-09-01T15:00:00Z", 4.0, "EUR")])
    out_t = tmp / "T" / "out"
    result_t = run_kivora(base_t, out_t)
    ok_t = result_t.returncode == 0 and (out_t / "rejected.csv").exists()
    rej_t = rejected_tuples(out_t) if ok_t else []

    def need_t():
        assert ok_t, (f"código {result_t.returncode}, rejected.csv "
                      f"{'existe' if (out_t / 'rejected.csv').exists() else 'no existe'}: "
                      f"{result_t.stderr.strip()[-300:]}")

    @scenario("S5")
    def s5():
        need_t()
        for item in [("refunds", "R-5", d1, "conflicting_duplicate"),
                     ("refunds", "R-5", d2, "conflicting_duplicate")]:
            assert item in rej_t, f"falta {item}"
    s5()

    @scenario("S6")
    def s6():
        need_t()
        assert ("refunds", "R-6", d1, "currency_mismatch") in rej_t, f"{rej_t}"
    s6()

    @scenario("S7")
    def s7():
        broken = tmp / "S7" / "inbox"
        write_day(broken, d1, orders=[("K-1", "C1", "2026-09-01T10:00:00Z", "EUR", "10.00")],
                  customers=c1, refunds='[{"refund_id": "R-1", ')
        result7 = run_kivora(broken, tmp / "S7" / "out")
        assert result7.returncode != 0, "debería terminar con código ≠ 0"
        message = result7.stderr + result7.stdout
        assert "refunds.json" in message, f"el mensaje no nombra el fichero: {message[-300:]!r}"
        assert "Traceback" not in message, "error sin controlar (traceback)"
    s7()

    @scenario("S8")
    def s8():
        sale = [("K-1", "C1", "2026-09-01T10:00:00Z", "EUR", "10.00")]
        plain, mixed = tmp / "S8a" / "inbox", tmp / "S8b" / "inbox"
        write_day(plain, d1, orders=sale, customers=c1)
        write_day(plain, d2)
        write_day(plain, d3)
        write_day(mixed, d1, orders=sale, customers=c1)
        write_day(mixed, d2, refunds="[]")
        write_day(mixed, d3)
        ra, rb = run_kivora(plain, tmp / "S8a" / "out"), run_kivora(mixed, tmp / "S8b" / "out")
        assert ra.returncode == 0 and rb.returncode == 0, f"códigos {ra.returncode}, {rb.returncode}"
        for name in ("daily_customer_metrics.csv", "rejected.csv"):
            a, b = tmp / "S8a" / "out" / name, tmp / "S8b" / "out" / name
            assert a.exists() and b.exists(), f"falta {name}"
            assert a.read_bytes() == b.read_bytes(), f"{name} distinto con [] / sin fichero"
    s8()


# --- principal --------------------------------------------------------------

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    missing = [d for d in DAYS if not (INBOX / d).is_dir()]
    if missing:
        print(f"FAIL  copia del inbox: faltan en data/inbox/ los días {', '.join(missing)}")
        return 1
    repo_inbox_hash = tree_hash(INBOX)
    tmp = Path(tempfile.mkdtemp(prefix="kivora-acceptance-"))
    try:
        inbox_copy = tmp / "inbox"
        for day in DAYS:
            shutil.copytree(INBOX / day, inbox_copy / day)
        copy_hash = tree_hash(inbox_copy)

        self_check_reference(inbox_copy)
        run1, run2 = tmp / "run1", tmp / "run2"
        result1, result2 = run_kivora(inbox_copy, run1), run_kivora(inbox_copy, run2)
        check_outputs(run1, run2, result1, result2, copy_hash, inbox_copy, repo_inbox_hash)
        synthetic(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [name for name, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)} PASS, {len(failed)} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
