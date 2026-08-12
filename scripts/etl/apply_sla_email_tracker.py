"""Import controlled SLA Email Tracker snapshot files into SQLite."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

LIST_FOLDER_SUMMARY_FAST = "SLA_Folder_Summary_FAST"
LIST_DAILY_HISTORY = "SLA_Folder_Summary_Daily_History"
LIST_WEEKLY_OWNER_SUMMARY = "SLA_Weekly_Owner_Summary"
LIST_EMAIL_TRACKER = "SLA_Email_Tracker"
LIST_ACTION_LOG = "SLA_Action_Log"
LIST_FOLDER_AUDIT_STATE = "SLA_Folder_Audit_State"

_SUPPORTED_LISTS = (
    LIST_FOLDER_SUMMARY_FAST,
    LIST_DAILY_HISTORY,
    LIST_WEEKLY_OWNER_SUMMARY,
    LIST_EMAIL_TRACKER,
    LIST_ACTION_LOG,
    LIST_FOLDER_AUDIT_STATE,
)
_SUPPORTED_SUFFIXES = {".json", ".csv", ".xlsx"}


@dataclass(frozen=True)
class SnapshotSpec:
    table: str
    normalise: Callable[[dict[str, Any], str], dict[str, Any]]
    columns: tuple[str, ...]
    placeholders: str


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create SLA tracker tables if they are missing."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sla_folder_summary_fast (
            folder_path       TEXT PRIMARY KEY,
            owner             TEXT NOT NULL DEFAULT '',
            open_count        INTEGER NOT NULL DEFAULT 0,
            unread_count      INTEGER NOT NULL DEFAULT 0,
            oldest_received_at TEXT NOT NULL DEFAULT '',
            source_updated_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS sla_folder_daily_history (
            snapshot_date     TEXT NOT NULL,
            folder_path       TEXT NOT NULL,
            owner             TEXT NOT NULL DEFAULT '',
            open_count        INTEGER NOT NULL DEFAULT 0,
            unread_count      INTEGER NOT NULL DEFAULT 0,
            net_change        INTEGER NOT NULL DEFAULT 0,
            source_updated_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (snapshot_date, folder_path)
        );

        CREATE TABLE IF NOT EXISTS sla_weekly_owner_summary (
            week_start        TEXT NOT NULL,
            week_end          TEXT NOT NULL,
            owner             TEXT NOT NULL,
            open_count        INTEGER NOT NULL DEFAULT 0,
            folder_count      INTEGER NOT NULL DEFAULT 0,
            start_count       INTEGER NOT NULL DEFAULT 0,
            net_change        INTEGER NOT NULL DEFAULT 0,
            start_unread_count INTEGER NOT NULL DEFAULT 0,
            unread_count      INTEGER NOT NULL DEFAULT 0,
            net_unread_change INTEGER NOT NULL DEFAULT 0,
            last_snapshot_at  TEXT NOT NULL DEFAULT '',
            weekly_status     TEXT NOT NULL DEFAULT '',
            source_updated_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (week_start, owner)
        );

        CREATE TABLE IF NOT EXISTS sla_email_tracker_open (
            email_key         TEXT PRIMARY KEY,
            received_at       TEXT NOT NULL,
            sender_email      TEXT NOT NULL DEFAULT '',
            sender_name       TEXT NOT NULL DEFAULT '',
            subject           TEXT NOT NULL DEFAULT '',
            owner             TEXT NOT NULL DEFAULT '',
            folder_path       TEXT NOT NULL DEFAULT '',
            sla_status        TEXT NOT NULL DEFAULT '',
            supplier_key      TEXT NOT NULL DEFAULT '',
            source_updated_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS sla_action_log (
            action_key        TEXT PRIMARY KEY,
            email_key         TEXT NOT NULL,
            received_at       TEXT NOT NULL,
            actioned_at       TEXT NOT NULL,
            sender_email      TEXT NOT NULL DEFAULT '',
            sender_name       TEXT NOT NULL DEFAULT '',
            subject           TEXT NOT NULL DEFAULT '',
            owner             TEXT NOT NULL DEFAULT '',
            action            TEXT NOT NULL DEFAULT '',
            folder_path       TEXT NOT NULL DEFAULT '',
            supplier_key      TEXT NOT NULL DEFAULT '',
            source_updated_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS sla_folder_audit_state (
            folder_path       TEXT PRIMARY KEY,
            last_seen_at      TEXT NOT NULL DEFAULT '',
            oldest_received_at TEXT NOT NULL DEFAULT '',
            open_count        INTEGER NOT NULL DEFAULT 0,
            source_updated_at TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_sla_open_received
            ON sla_email_tracker_open(received_at);
        CREATE INDEX IF NOT EXISTS idx_sla_open_owner
            ON sla_email_tracker_open(owner);
        CREATE INDEX IF NOT EXISTS idx_sla_action_received
            ON sla_action_log(received_at);
        CREATE INDEX IF NOT EXISTS idx_sla_action_actioned
            ON sla_action_log(actioned_at);
        CREATE INDEX IF NOT EXISTS idx_sla_action_owner
            ON sla_action_log(owner);
        CREATE INDEX IF NOT EXISTS idx_sla_weekly_owner_week
            ON sla_weekly_owner_summary(week_start, owner);
        CREATE INDEX IF NOT EXISTS idx_sla_daily_history_date
            ON sla_folder_daily_history(snapshot_date);
        """
    )
    _ensure_column(conn, "sla_folder_daily_history", "owner", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "sla_folder_daily_history", "unread_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "sla_folder_daily_history", "net_change", "INTEGER NOT NULL DEFAULT 0")
    for column_name in (
        "folder_count",
        "start_count",
        "net_change",
        "start_unread_count",
        "unread_count",
        "net_unread_change",
    ):
        _ensure_column(conn, "sla_weekly_owner_summary", column_name, "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "sla_weekly_owner_summary", "last_snapshot_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "sla_weekly_owner_summary", "weekly_status", "TEXT NOT NULL DEFAULT ''")
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def derive_supplier_key(sender_email: str, sender_name: str, subject: str) -> str:
    """Return a deterministic supplier key from domain first, then fallback text."""
    email = _clean_text(sender_email).lower()
    if "@" in email:
        domain = email.rsplit("@", 1)[1].strip(" .")
        if domain:
            return domain

    name_subject = " ".join(part for part in (_clean_text(sender_name), _clean_text(subject)) if part)
    slug = re.sub(r"[^a-z0-9]+", "-", name_subject.lower()).strip("-")
    if slug:
        return f"name-subject:{slug[:60]}"

    digest = hashlib.sha256("|".join([email, sender_name, subject]).encode("utf-8")).hexdigest()[:16]
    return f"unknown:{digest}"


def _normalise_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "nat", "none"}:
        return ""
    return text


def _row_get(row: dict[str, Any], *candidates: str) -> Any:
    keyed = {_normalise_key(str(key)): value for key, value in row.items()}
    for candidate in candidates:
        key = _normalise_key(candidate)
        if key in keyed:
            return keyed[key]
    return ""


def _int_value(value: Any) -> int:
    text = _clean_text(value)
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError as exc:
        raise ValueError(f"expected integer value, got {value!r}") from exc


def _parse_datetime_value(value: Any, field: str, *, required: bool = False) -> str:
    text = _clean_text(value)
    if not text:
        if required:
            raise ValueError(f"{field} is required")
        return ""

    parsers = (
        lambda raw: datetime.fromisoformat(raw.replace("Z", "+00:00")),
        lambda raw: datetime.strptime(raw, "%Y-%m-%d %H:%M:%S"),
        lambda raw: datetime.strptime(raw, "%Y-%m-%d"),
        lambda raw: datetime.strptime(raw, "%d/%m/%Y %H:%M:%S"),
        lambda raw: datetime.strptime(raw, "%d/%m/%Y %H:%M"),
        lambda raw: datetime.strptime(raw, "%d/%m/%Y"),
    )
    for parser in parsers:
        try:
            parsed = parser(text)
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            return parsed.isoformat(timespec="seconds")
        except ValueError:
            continue
    raise ValueError(f"{field} must be a supported date/datetime, got {value!r}")


def _parse_date_value(value: Any, field: str, *, required: bool = False) -> str:
    parsed = _parse_datetime_value(value, field, required=required)
    return parsed[:10] if parsed else ""


def _source_updated_at(row: dict[str, Any], fallback: str) -> str:
    return _parse_datetime_value(
        _row_get(row, "source_updated_at", "Modified", "Updated", "Snapshot_At", "Snapshot At", "Last_Audit_At"),
        "source_updated_at",
    ) or fallback


def _stable_email_key(row: dict[str, Any], received_at: str, sender_email: str, subject: str) -> str:
    supplied = _clean_text(_row_get(row, "Email_Key", "Email Key", "Item/Email_Key", "Item Email Key"))
    if supplied:
        return supplied
    raw = json.dumps(
        {"received_at": received_at, "sender_email": sender_email, "subject": subject},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "email_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _normalise_email_tracker(row: dict[str, Any], fallback_updated_at: str) -> dict[str, Any]:
    received_at = _parse_datetime_value(_row_get(row, "Received_At", "Received At"), "Received_At", required=True)
    sender_email = _clean_text(_row_get(row, "Sender_Email", "Sender Email", "From", "From Email"))
    sender_name = _clean_text(_row_get(row, "Sender_Name", "Sender Name", "From Name"))
    subject = _clean_text(_row_get(row, "Subject", "Email_Subject", "Email Subject"))
    return {
        "email_key": _stable_email_key(row, received_at, sender_email, subject),
        "received_at": received_at,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "subject": subject,
        "owner": _clean_text(_row_get(row, "Owner", "Owner_Display", "Assigned_To", "Assigned To")),
        "folder_path": _clean_text(_row_get(row, "Folder_Path", "Folder Path")),
        "sla_status": _clean_text(_row_get(row, "SLA_Status", "SLA Status", "Status")),
        "supplier_key": derive_supplier_key(sender_email, sender_name, subject),
        "source_updated_at": _source_updated_at(row, fallback_updated_at),
    }


def _normalise_action_log(row: dict[str, Any], fallback_updated_at: str) -> dict[str, Any]:
    received_at = _parse_datetime_value(_row_get(row, "Received_At", "Received At"), "Received_At", required=True)
    actioned_at = _parse_datetime_value(_row_get(row, "Actioned_At", "Actioned At"), "Actioned_At", required=True)
    sender_email = _clean_text(_row_get(row, "Sender_Email", "Sender Email", "From", "From Email"))
    sender_name = _clean_text(_row_get(row, "Sender_Name", "Sender Name", "From Name"))
    subject = _clean_text(_row_get(row, "Subject", "Email_Subject", "Email Subject"))
    email_key = _stable_email_key(row, received_at, sender_email, subject)
    action = _clean_text(_row_get(row, "Action", "Action_Detection_Method", "Action_Type", "Action Type"))
    supplied_action_key = _clean_text(_row_get(row, "Action_Key", "Action Key"))
    action_key = supplied_action_key or "action_" + hashlib.sha256(
        "|".join([email_key, actioned_at, action]).encode("utf-8")
    ).hexdigest()[:24]
    return {
        "action_key": action_key,
        "email_key": email_key,
        "received_at": received_at,
        "actioned_at": actioned_at,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "subject": subject,
        "owner": _clean_text(_row_get(row, "Owner", "Owner_Display", "Actioned_By", "Actioned By")),
        "action": action,
        "folder_path": _clean_text(_row_get(row, "Folder_Path", "Folder Path")),
        "supplier_key": derive_supplier_key(sender_email, sender_name, subject),
        "source_updated_at": _source_updated_at(row, fallback_updated_at),
    }


def _normalise_folder_summary(row: dict[str, Any], fallback_updated_at: str) -> dict[str, Any]:
    folder_path = _clean_text(_row_get(row, "Folder_Path", "Folder Path", "Folder"))
    if not folder_path:
        raise ValueError("Folder_Path is required")
    return {
        "folder_path": folder_path,
        "owner": _clean_text(_row_get(row, "Owner", "Owner_Display")),
        "open_count": _int_value(_row_get(row, "Open_Count", "Open Count", "Email_Count", "TotalItemCount", "totalItemCount")),
        "unread_count": _int_value(_row_get(row, "Unread_Count", "Unread Count", "Unread_Email_Count", "UnreadItemCount", "unreadItemCount")),
        "oldest_received_at": _parse_datetime_value(
            _row_get(row, "Oldest_Received_At", "Oldest Received At", "Oldest_Email_Received"),
            "Oldest_Received_At",
        ),
        "source_updated_at": _source_updated_at(row, fallback_updated_at),
    }


def _normalise_daily_history(row: dict[str, Any], fallback_updated_at: str) -> dict[str, Any]:
    folder_path = _clean_text(_row_get(row, "Folder_Path", "Folder Path", "Folder"))
    if not folder_path:
        raise ValueError("Folder_Path is required")
    return {
        "snapshot_date": _parse_date_value(_row_get(row, "Snapshot_Date", "Snapshot Date", "Date"), "Snapshot_Date", required=True),
        "folder_path": folder_path,
        "owner": _clean_text(_row_get(row, "Owner", "Owner_Display")),
        "open_count": _int_value(_row_get(row, "Open_Count", "Open Count", "Email_Count")),
        "unread_count": _int_value(_row_get(row, "Unread_Count", "Unread Count", "Unread_Email_Count")),
        "net_change": _int_value(_row_get(row, "Net_Change", "Net Change", "Net_Change_Since_Last_Run")),
        "source_updated_at": _source_updated_at(row, fallback_updated_at),
    }


def _normalise_weekly_owner(row: dict[str, Any], fallback_updated_at: str) -> dict[str, Any]:
    owner = _clean_text(_row_get(row, "Owner", "Owner_Display"))
    if not owner:
        raise ValueError("Owner is required")
    return {
        "week_start": _parse_date_value(_row_get(row, "Week_Start", "Week Start", "Week_Start_Date"), "Week_Start", required=True),
        "week_end": _parse_date_value(_row_get(row, "Week_End", "Week End", "Week_End_Date"), "Week_End", required=True),
        "owner": owner,
        "open_count": _int_value(_row_get(row, "Open_Count", "Open Count", "Latest_Email_Count")),
        "folder_count": _int_value(_row_get(row, "Folder_Count", "Folder Count")),
        "start_count": _int_value(_row_get(row, "Start_Of_Week_Email_Count", "Start Count")),
        "net_change": _int_value(_row_get(row, "Net_Change_This_Week", "Net Change")),
        "start_unread_count": _int_value(_row_get(row, "Start_Of_Week_Unread_Count", "Start Unread Count")),
        "unread_count": _int_value(_row_get(row, "Latest_Unread_Count", "Unread Count")),
        "net_unread_change": _int_value(_row_get(row, "Net_Unread_Change_This_Week", "Net Unread Change")),
        "last_snapshot_at": _parse_datetime_value(_row_get(row, "Last_Snapshot_At", "Snapshot_At"), "Last_Snapshot_At"),
        "weekly_status": _clean_text(_row_get(row, "Weekly_Status", "Status")),
        "source_updated_at": _source_updated_at(row, fallback_updated_at),
    }


def _normalise_audit_state(row: dict[str, Any], fallback_updated_at: str) -> dict[str, Any]:
    folder_path = _clean_text(_row_get(row, "Folder_Path", "Folder Path", "Folder"))
    if not folder_path:
        raise ValueError("Folder_Path is required")
    return {
        "folder_path": folder_path,
        "last_seen_at": _parse_datetime_value(_row_get(row, "Last_Seen_At", "Last Seen At", "Last_Audit_At", "Last_Success_At"), "Last_Seen_At"),
        "oldest_received_at": _parse_datetime_value(
            _row_get(row, "Oldest_Received_At", "Oldest Received At", "Oldest_Email_Received"),
            "Oldest_Received_At",
        ),
        "open_count": _int_value(_row_get(row, "Open_Count", "Open Count", "Open_Email_Count_Last_Run")),
        "source_updated_at": _source_updated_at(row, fallback_updated_at),
    }


_SPECS: dict[str, SnapshotSpec] = {
    LIST_FOLDER_SUMMARY_FAST: SnapshotSpec(
        "sla_folder_summary_fast",
        _normalise_folder_summary,
        ("folder_path", "owner", "open_count", "unread_count", "oldest_received_at", "source_updated_at"),
        "?, ?, ?, ?, ?, ?",
    ),
    LIST_DAILY_HISTORY: SnapshotSpec(
        "sla_folder_daily_history",
        _normalise_daily_history,
        ("snapshot_date", "folder_path", "owner", "open_count", "unread_count", "net_change", "source_updated_at"),
        "?, ?, ?, ?, ?, ?, ?",
    ),
    LIST_WEEKLY_OWNER_SUMMARY: SnapshotSpec(
        "sla_weekly_owner_summary",
        _normalise_weekly_owner,
        (
            "week_start", "week_end", "owner", "open_count", "folder_count",
            "start_count", "net_change", "start_unread_count", "unread_count",
            "net_unread_change", "last_snapshot_at", "weekly_status", "source_updated_at",
        ),
        "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
    ),
    LIST_EMAIL_TRACKER: SnapshotSpec(
        "sla_email_tracker_open",
        _normalise_email_tracker,
        ("email_key", "received_at", "sender_email", "sender_name", "subject", "owner", "folder_path", "sla_status", "supplier_key", "source_updated_at"),
        "?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
    ),
    LIST_ACTION_LOG: SnapshotSpec(
        "sla_action_log",
        _normalise_action_log,
        ("action_key", "email_key", "received_at", "actioned_at", "sender_email", "sender_name", "subject", "owner", "action", "folder_path", "supplier_key", "source_updated_at"),
        "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
    ),
    LIST_FOLDER_AUDIT_STATE: SnapshotSpec(
        "sla_folder_audit_state",
        _normalise_audit_state,
        ("folder_path", "last_seen_at", "oldest_received_at", "open_count", "source_updated_at"),
        "?, ?, ?, ?, ?",
    ),
}


def _detect_list_name(path: Path) -> str | None:
    normalized_name = _normalise_key(path.stem)
    for list_name in _SUPPORTED_LISTS:
        if _normalise_key(list_name) in normalized_name:
            return list_name
    return None


def _read_snapshot_rows(path: Path, list_name: str) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("value") or payload.get("rows") or payload.get(list_name) or []
        else:
            raise ValueError("JSON snapshot must be an array or object")
        if not isinstance(rows, list):
            raise ValueError("JSON snapshot rows must be a list")
        return [row for row in rows if isinstance(row, dict)]

    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    if path.suffix.lower() == ".xlsx":
        import pandas as pd  # noqa: PLC0415

        frame = pd.read_excel(path)
        return frame.to_dict(orient="records")

    raise ValueError(f"unsupported snapshot suffix: {path.suffix}")


def _file_updated_at(path: Path) -> str:
    modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return modified.isoformat(timespec="seconds").replace("+00:00", "Z")


def _replace_table(conn: sqlite3.Connection, spec: SnapshotSpec, rows: list[dict[str, Any]]) -> None:
    columns = ", ".join(spec.columns)
    values = [tuple(row[column] for column in spec.columns) for row in rows]
    conn.execute(f"DELETE FROM {spec.table}")
    if values:
        conn.executemany(
            f"INSERT OR REPLACE INTO {spec.table} ({columns}) VALUES ({spec.placeholders})",
            values,
        )


def _default_snapshot_dir() -> Path:
    from scripts.paths import DATA_DIR  # noqa: PLC0415

    try:
        from scripts.paths import SLA_TRACKER_SNAPSHOT_DIR  # type: ignore[attr-defined]  # noqa: PLC0415
    except ImportError:
        return DATA_DIR / "sla_tracker_snapshots"
    return SLA_TRACKER_SNAPSHOT_DIR


def apply_sla_email_tracker(
    db_path: Path | None = None,
    snapshot_dir: Path | None = None,
    dry_run: bool = False,
    _conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Load controlled SLA tracker snapshot files into SQLite."""
    from scripts.paths import DB_PATH  # noqa: PLC0415

    db_path = db_path or DB_PATH
    snapshot_dir = snapshot_dir or _default_snapshot_dir()
    result: dict[str, Any] = {
        "files_loaded": 0,
        "files_failed": 0,
        "files_skipped": 0,
        "rows_loaded": {list_name: 0 for list_name in _SUPPORTED_LISTS},
        "snapshot_dir_missing": False,
        "errors": [],
    }

    if not snapshot_dir.exists():
        result["snapshot_dir_missing"] = True
        return result

    try:
        snapshot_files = sorted(
            path for path in snapshot_dir.iterdir()
            if path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES
        )
    except OSError as exc:
        result["errors"].append(f"snapshot directory unavailable: {exc}")
        result["files_failed"] += 1
        return result

    own_conn = _conn is None
    conn: sqlite3.Connection = _conn or sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_schema(conn)
        for path in snapshot_files:
            list_name = _detect_list_name(path)
            if list_name is None:
                result["files_skipped"] += 1
                continue
            spec = _SPECS[list_name]
            try:
                fallback_updated_at = _file_updated_at(path)
                raw_rows = _read_snapshot_rows(path, list_name)
                normalised_rows = [spec.normalise(row, fallback_updated_at) for row in raw_rows]
                if not dry_run:
                    with conn:
                        _replace_table(conn, spec, normalised_rows)
                result["files_loaded"] += 1
                result["rows_loaded"][list_name] = len(normalised_rows)
            except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
                msg = f"{path.name}: {exc}"
                logger.warning("SLA tracker snapshot rejected: %s", msg)
                result["files_failed"] += 1
                result["errors"].append(msg)
        return result
    finally:
        if own_conn:
            conn.close()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply controlled SLA Email Tracker snapshots.")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--db", metavar="PATH", default=None)
    parser.add_argument("--snapshot-dir", metavar="PATH", default=None)
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    summary = apply_sla_email_tracker(
        db_path=Path(args.db) if args.db else None,
        snapshot_dir=Path(args.snapshot_dir) if args.snapshot_dir else None,
        dry_run=args.dry_run,
    )
    print(
        "[OK] SLA tracker snapshots: "
        f"files_loaded={summary['files_loaded']} "
        f"files_failed={summary['files_failed']} "
        f"files_skipped={summary['files_skipped']} "
        f"errors={len(summary['errors'])}"
    )


if __name__ == "__main__":
    main()
