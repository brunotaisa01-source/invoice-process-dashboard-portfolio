"""Clear pack-local SLA tracker data while the SLA feature is disabled."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


SLA_TABLES = (
    "sla_folder_summary_fast",
    "sla_folder_daily_history",
    "sla_weekly_owner_summary",
    "sla_email_tracker_open",
    "sla_action_log",
    "sla_folder_audit_state",
)


def clear_sla_tracker_data(db_path: Path) -> tuple[str, ...]:
    """Delete SLA rows without changing invoice or other dashboard tables."""
    if not db_path.is_file():
        raise FileNotFoundError(f"Dashboard DB missing: {db_path}")

    with sqlite3.connect(db_path) as conn:
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        cleared = tuple(table for table in SLA_TABLES if table in existing)
        for table in cleared:
            conn.execute(f'DELETE FROM "{table}"')
        conn.commit()

    return cleared


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Clear pack-local SLA tracker tables."
    )
    parser.add_argument("--db", required=True, type=Path, metavar="PATH")
    return parser


def main() -> None:
    """Run the pack-local SLA clear operation."""
    args = build_parser().parse_args()
    cleared = clear_sla_tracker_data(args.db)
    print(
        "[OK] SLA tracker disabled; "
        f"cleared {len(cleared)} SLA table(s)."
    )


if __name__ == "__main__":
    main()
