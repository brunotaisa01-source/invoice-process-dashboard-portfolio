"""Build the pack-local SQLite database from the committed synthetic fixture."""
from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
from pathlib import Path

from scripts.paths import DB_PATH, ROOT, SQL_DIR

FIXTURE_PATH = ROOT / "data" / "fixtures" / "synthetic_invoices.csv"
DASHBOARD_DB_PATH = ROOT / "dashboard" / "data" / "invoices.db"
SQL_FILES = ("01_schema.sql", "02_indexes.sql", "03_views.sql")


def _assert_pack_local(path: Path) -> None:
    resolved = path.resolve()
    expected_parent = (ROOT / "db").resolve()
    if resolved.parent != expected_parent:
        raise RuntimeError(f"Refusing to bootstrap non-pack database: {resolved}")


def bootstrap() -> dict[str, int | str]:
    _assert_pack_local(DB_PATH)
    if not FIXTURE_PATH.is_file():
        raise FileNotFoundError(f"Synthetic fixture missing: {FIXTURE_PATH.relative_to(ROOT)}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        objects = conn.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' "
            "ORDER BY CASE type WHEN 'view' THEN 0 ELSE 1 END"
        ).fetchall()
        for object_type, name in objects:
            safe_name = name.replace('"', '""')
            conn.execute(f'DROP {object_type.upper()} IF EXISTS "{safe_name}"')
        for filename in SQL_FILES:
            conn.executescript((SQL_DIR / filename).read_text(encoding="utf-8"))

        with FIXTURE_PATH.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            raise RuntimeError("Synthetic invoice fixture is empty.")

        columns = list(rows[0])
        placeholders = ",".join("?" for _ in columns)
        quoted_columns = ",".join(f'"{column}"' for column in columns)
        conn.executemany(
            f"INSERT INTO invoices ({quoted_columns}) VALUES ({placeholders})",
            [[row[column] if row[column] != "" else None for column in columns] for row in rows],
        )
        first = rows[0]
        conn.execute(
            "INSERT INTO weekly_imports "
            "(extraction_date, week_start, week_end, imported_at, files_processed, total_rows) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                first["extraction_date"], first["week_start"], first["week_end"],
                "2026-08-14T12:00:00Z", '["SYS-A","SYS-B"]', len(rows),
            ),
        )
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        invoice_count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        legacy_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='invoice_items'"
        ).fetchone()[0]
        conn.commit()

    if integrity != "ok" or invoice_count < 1 or legacy_count:
        raise RuntimeError(
            f"Bootstrap verification failed: integrity={integrity}, invoices={invoice_count}, legacy={legacy_count}"
        )
    DASHBOARD_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DB_PATH, DASHBOARD_DB_PATH)
    result = {"status": "GREEN", "invoices": invoice_count, "integrity": integrity}
    print(result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the included database without rebuilding it",
    )
    return parser


def check() -> dict[str, int | str]:
    _assert_pack_local(DB_PATH)
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Pack database missing: {DB_PATH.relative_to(ROOT)}")
    uri = DB_PATH.resolve().as_uri() + "?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        invoice_count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    if integrity != "ok" or invoice_count < 1:
        raise RuntimeError(
            f"Database validation failed: integrity={integrity}, invoices={invoice_count}"
        )
    result = {"status": "GREEN", "invoices": invoice_count, "integrity": integrity}
    print(result)
    return result


def main() -> int:
    args = build_parser().parse_args()
    if args.check:
        check()
    else:
        bootstrap()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
