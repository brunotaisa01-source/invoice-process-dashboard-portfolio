"""
export_dashboard.py - Generates dashboard/data.js AND dashboard/index.html.

Both files are created by Python. The HTML is fully self-contained with
inlined libraries for offline local use.

Usage:
    python -m scripts.dashboard.export_dashboard                  (generate locally)
    python -m scripts.dashboard.export_dashboard --force-html     (regenerate index.html)
    python -m scripts.dashboard.export_dashboard --deploy         (stage, validate, deploy)
"""
from __future__ import annotations

import argparse
import json
import logging
import filecmp
import math
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import zlib
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path

# The documented direct entrypoint must not leave a cache directory that the
# pack preflight correctly rejects.
sys.dont_write_bytecode = True

# File-path execution sets sys.path to scripts/dashboard rather than the
# project root. Keep the documented direct command equivalent to module mode.
if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from scripts.config import (
    TEAM_MEMBERS, ALL_MEMBERS, FORMER_MEMBERS, DOC_TYPE_LABELS, DAILY_TARGET,
    INDIVIDUAL_TARGETS, WORKING_DAYS_PER_WEEK, CREDIT_NOTE_TYPES,
)
from scripts.paths import DB_PATH, DATA_JS_PATH, DASHBOARD_DIR, DEPLOY_DIR, LIBS_DIR, DATA_CHUNKS_DIR

logger = logging.getLogger(__name__)

HTML_PATH = DASHBOARD_DIR / "index.html"

DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
REQUIRED_DEPLOY_FILES = (
    Path("index.html"),
    Path("data.js"),
    Path("dist") / "dashboard.js",
)
REQUIRED_CALENDAR_DIRS = ("pending", "processed", "rejected")
DEPLOY_MANIFEST_NAME = "deploy_manifest.json"


def validate_extraction_date(date: str) -> None:
    """Validate extraction_date is YYYY-MM-DD format.

    Prevents path traversal and malformed filenames by ensuring dates
    conform strictly to ISO 8601 date format with zero-padded fields.

    Raises:
        ValueError: If date format is invalid.
    """
    if not DATE_PATTERN.match(date):
        raise ValueError(
            f"Invalid extraction_date format: '{date}'. "
            f"Expected YYYY-MM-DD (e.g., 2026-03-10)"
        )


def _query_absences(conn: sqlite3.Connection) -> dict[str, dict[str, list[dict]]]:
    """
    Query all absences grouped by week_start  member  list of {date, type}.
    Returns empty dict if the team_absences table doesn't exist yet (old DB).
    """
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(team_absences)").fetchall()}
        source_expr = "source" if "source" in columns else "'weekly_overrides' AS source"
        rows = conn.execute(
            f"SELECT week_start, member, date, type, {source_expr} "
            "FROM team_absences ORDER BY week_start, member, date"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}

    result: dict[str, dict[str, list[dict]]] = {}
    for row in rows:
        ws = row["week_start"]
        m = row["member"]
        if ws not in result:
            result[ws] = {}
        if m not in result[ws]:
            result[ws][m] = []
        result[ws][m].append({"date": row["date"], "type": row["type"], "source": row["source"]})
    return result


def _flatten_absences(absences_by_week: dict[str, dict[str, list[dict]]]) -> list[dict]:
    """Flatten grouped absence data for the Calendar page."""
    rows: list[dict] = []
    for week_start, by_member in absences_by_week.items():
        for member, absences in by_member.items():
            for absence in absences:
                rows.append({
                    "week_start": week_start,
                    "member": member,
                    "date": absence["date"],
                    "type": absence["type"],
                    "source": absence.get("source", "weekly_overrides"),
                })
    return sorted(rows, key=lambda item: (item["date"], item["member"]))


def _empty_member_total() -> dict:
    """Return an empty aggregate bucket for one member."""
    return {
        "total": 0, "by_country": {}, "by_doc_type": {},
        "reversal_count": 0, "credit_note_count": 0,
    }


def _adjust_bucket(bucket: dict, amount: int, country: str, doc_type: str) -> None:
    """Move aggregate production credit in or out of one member bucket."""
    bucket["total"] += amount
    if country:
        bucket["by_country"][country] = bucket["by_country"].get(country, 0) + amount
    if doc_type:
        bucket["by_doc_type"][doc_type] = bucket["by_doc_type"].get(doc_type, 0) + amount


def _available_credit(bucket: dict, country: str, doc_type: str) -> int:
    """Return credit available for an override, respecting optional dimensions."""
    available = [int(bucket.get("total") or 0)]
    if country:
        available.append(int(bucket.get("by_country", {}).get(country, 0) or 0))
    if doc_type:
        available.append(int(bucket.get("by_doc_type", {}).get(doc_type, 0) or 0))
    return min(available)


def _override_doc_type(override: dict) -> str:
    """Treat a blank Envoy override document as the Envoy document type."""
    document_type = str(override.get("document_type") or "")
    if document_type:
        return document_type
    return "1H" if str(override.get("work_type") or "").lower() == "envoy" else ""


def _candidate_override_dates(daily: dict, requested_date: str) -> list[str]:
    """Prefer the requested/following dates, then fall back to prior dates."""
    dates = sorted(daily)
    return [date for date in dates if date >= requested_date] + [
        date for date in reversed(dates) if date < requested_date
    ]


def _apply_production_overrides(
    daily: dict,
    weekly_totals: dict,
    production_overrides: list[dict] | None,
    included_members: set[str],
) -> None:
    """Apply dashboard production overrides to aggregates only."""
    for override in production_overrides or []:
        date = str(override.get("date") or "")
        from_member = str(override.get("from_member") or "")
        to_member = str(override.get("to_member") or "")
        if from_member not in included_members or to_member not in included_members:
            continue

        requested = int(override.get("count") or 0)
        if requested <= 0:
            continue

        country = str(override.get("country") or "")
        doc_type = _override_doc_type(override)
        from_weekly = weekly_totals.get(from_member)
        if not from_weekly:
            continue

        weekly_available = _available_credit(from_weekly, country, doc_type)
        if weekly_available <= 0:
            continue

        remaining = min(requested, weekly_available)
        moved_total = 0
        for source_date in _candidate_override_dates(daily, date):
            if remaining <= 0:
                break
            day_members = daily[source_date]
            from_daily = day_members.get(from_member)
            if not from_daily:
                continue
            daily_available = _available_credit(from_daily, country, doc_type)
            if daily_available <= 0:
                continue

            moved = min(remaining, daily_available)
            to_daily = day_members.setdefault(to_member, _empty_member_total())
            _adjust_bucket(from_daily, -moved, country, doc_type)
            _adjust_bucket(to_daily, moved, country, doc_type)
            moved_total += moved
            remaining -= moved

        # If no daily source exists anywhere in the week, keep the correction in
        # the weekly aggregate rather than silently dropping a valid override.
        if moved_total <= 0:
            moved_total = min(requested, weekly_available)

        to_weekly = weekly_totals.setdefault(to_member, _empty_member_total())
        _adjust_bucket(from_weekly, -moved_total, country, doc_type)
        _adjust_bucket(to_weekly, moved_total, country, doc_type)


def _query_production_overrides(conn: sqlite3.Connection) -> list[dict]:
    """Query active production overrides for aggregate dashboard export."""
    try:
        rows = conn.execute(
            """
            SELECT override_id, week_start, date, from_member, to_member, count,
                   work_type, country, company_code, document_type, reference,
                   reason, created_at, created_by
            FROM production_overrides
            ORDER BY week_start, date, work_type, from_member, to_member, override_id
            """
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table: production_overrides" in str(exc).lower():
            return []
        logger.exception("production_overrides query failed")
        raise

    return [
        {
            "override_id": row["override_id"],
            "week_start": row["week_start"],
            "date": row["date"],
            "from_member": row["from_member"],
            "to_member": row["to_member"],
            "count": int(row["count"]),
            "work_type": row["work_type"],
            "country": row["country"] or "",
            "company_code": row["company_code"] or "",
            "document_type": row["document_type"] or "",
            "reference": row["reference"] or "",
            "reason": row["reason"] or "",
            "created_at": row["created_at"],
            "created_by": row["created_by"] or "",
        }
        for row in rows
    ]


def _group_production_overrides(overrides: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Group production overrides by week_start and work_type."""
    grouped: dict[tuple[str, str], list[dict]] = {}
    for override in overrides:
        key = (override["week_start"], override["work_type"])
        grouped.setdefault(key, []).append(override)
    return grouped


SLA_DRILLDOWN_LIMIT = 500
SLA_REQUIRED_TABLES = (
    "sla_email_tracker_open",
    "sla_action_log",
)


def _empty_sla_tracker(now_iso: str) -> dict:
    """Return the stable empty SLA tracker payload shape."""
    return {
        "generated_at": now_iso,
        "source_updated_at": "",
        "kpis": {
            "open_emails": 0,
            "weekly_received": 0,
            "weekly_actioned": 0,
            "weekly_gap": 0,
            "people_needed": 0,
            "weekly_net_change": 0,
            "aged_open_emails": 0,
            "avg_weekly_actioned_per_owner": 0,
            "avg_resolution_days": 0,
            "current_week_start": "",
            "current_week_end": "",
        },
        "owner_summary": [],
        "weekly_owner_summary": [],
        "daily_history": [],
        "open_emails": [],
        "action_log": [],
        "supplier_summary": [],
    }


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Return True when a SQLite table exists."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """Return existing column names for a SQLite table."""
    if not _table_exists(conn, table_name):
        return set()
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _has_sla_tracker_tables(conn: sqlite3.Connection) -> bool:
    """Return True when the DB can produce the SLA tracker payload."""
    return all(_table_exists(conn, table) for table in SLA_REQUIRED_TABLES)


def _parse_sla_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sla_date(value: str) -> str:
    parsed = _parse_sla_datetime(value)
    return parsed.date().isoformat() if parsed else ""


def _sla_friday_week_start(value: datetime) -> datetime:
    days_since_friday = (value.weekday() - 4) % 7
    start = value - timedelta(days=days_since_friday)
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def _sla_monday_week_start(value: datetime) -> datetime:
    start = value - timedelta(days=value.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_sla_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(str(value or ""), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _sla_current_week_window(conn: sqlite3.Connection, fallback_activity: datetime) -> tuple[datetime, datetime, datetime]:
    if _table_exists(conn, "sla_weekly_owner_summary"):
        row = conn.execute(
            """
            SELECT week_start, week_end
            FROM sla_weekly_owner_summary
            ORDER BY week_start DESC, week_end DESC
            LIMIT 1
            """
        ).fetchone()
        if row:
            week_start = _parse_sla_date(row["week_start"])
            week_end = _parse_sla_date(row["week_end"])
            if week_start is not None and week_end is not None:
                return week_start, week_end + timedelta(days=1), week_end

    week_start = _sla_monday_week_start(fallback_activity)
    week_end = week_start + timedelta(days=4)
    return week_start, week_end + timedelta(days=1), week_end


def _latest_sla_activity(open_rows: list[sqlite3.Row], action_rows: list[sqlite3.Row], now: datetime) -> datetime:
    dates: list[datetime] = []
    for row in open_rows:
        parsed = _parse_sla_datetime(row["received_at"])
        if parsed is not None:
            dates.append(parsed)
    for row in action_rows:
        for field in ("received_at", "actioned_at"):
            parsed = _parse_sla_datetime(row[field])
            if parsed is not None:
                dates.append(parsed)
    return max(dates) if dates else now


def _within_week(value: str, week_start: datetime, week_end: datetime) -> bool:
    parsed = _parse_sla_datetime(value)
    return parsed is not None and week_start <= parsed < week_end


def _age_days(received_at: str, now: datetime) -> int:
    parsed = _parse_sla_datetime(received_at)
    if parsed is None:
        return 0
    return max(0, (now.date() - parsed.date()).days)


def _duration_days(start_value: str, end_value: str) -> float:
    start = _parse_sla_datetime(start_value)
    end = _parse_sla_datetime(end_value)
    if start is None or end is None or end < start:
        return 0
    return round((end - start).total_seconds() / 86400, 2)


def _query_sla_weekly_owner_summary(conn: sqlite3.Connection) -> list[dict]:
    if not _table_exists(conn, "sla_weekly_owner_summary"):
        return []
    rows = conn.execute(
        """
        SELECT week_start, week_end, owner, open_count, folder_count, start_count,
               net_change, start_unread_count, unread_count, net_unread_change,
               last_snapshot_at, weekly_status
        FROM sla_weekly_owner_summary
        ORDER BY week_start DESC, owner
        LIMIT 120
        """
    ).fetchall()
    return [
        {
            "week_start": row["week_start"],
            "week_end": row["week_end"],
            "owner_display": row["owner"],
            "open_count": int(row["open_count"] or 0),
            "folder_count": int(row["folder_count"] or 0),
            "start_count": int(row["start_count"] or 0),
            "net_change": int(row["net_change"] or 0),
            "start_unread_count": int(row["start_unread_count"] or 0),
            "unread_count": int(row["unread_count"] or 0),
            "net_unread_change": int(row["net_unread_change"] or 0),
            "last_snapshot_at": row["last_snapshot_at"] or "",
            "weekly_status": row["weekly_status"] or "",
        }
        for row in rows
    ]


def _query_sla_daily_history(conn: sqlite3.Connection) -> list[dict]:
    if not _table_exists(conn, "sla_folder_daily_history"):
        return []
    columns = _table_columns(conn, "sla_folder_daily_history")
    owner_select = "owner" if "owner" in columns else "'' AS owner"
    rows = conn.execute(
        f"""
        SELECT snapshot_date, folder_path, {owner_select}, open_count, unread_count, net_change
        FROM sla_folder_daily_history
        ORDER BY snapshot_date DESC, folder_path
        LIMIT 500
        """
    ).fetchall()
    return [
        {
            "snapshot_date": row["snapshot_date"],
            "folder_path": row["folder_path"],
            "owner_display": row["owner"] or "",
            "open_count": int(row["open_count"] or 0),
            "unread_count": int(row["unread_count"] or 0),
            "net_change": int(row["net_change"] or 0),
        }
        for row in rows
    ]


def _sla_source_updated_at(conn: sqlite3.Connection) -> str:
    candidates: list[str] = []
    for table in (
        "sla_email_tracker_open",
        "sla_action_log",
        "sla_weekly_owner_summary",
        "sla_folder_daily_history",
        "sla_folder_summary_fast",
        "sla_folder_audit_state",
    ):
        if not _table_exists(conn, table):
            continue
        row = conn.execute(f"SELECT MAX(source_updated_at) AS source_updated_at FROM {table}").fetchone()
        if row and row["source_updated_at"]:
            candidates.append(row["source_updated_at"])
    return max(candidates) if candidates else ""


def _query_sla_tracker(conn: sqlite3.Connection, now_iso: str | None = None) -> dict:
    """Query a compact SLA Email Tracker payload for DASHBOARD_DATA."""
    now = _parse_sla_datetime(now_iso or "") or datetime.now(timezone.utc)
    generated_at = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    if not _has_sla_tracker_tables(conn):
        return _empty_sla_tracker(generated_at)

    all_open_rows = conn.execute(
        """
        SELECT email_key, received_at, sender_email, sender_name, subject, owner,
               folder_path, sla_status, supplier_key
        FROM sla_email_tracker_open
        ORDER BY received_at ASC
        """
    ).fetchall()
    all_action_rows = conn.execute(
        """
        SELECT email_key, received_at, actioned_at, sender_email, sender_name,
               subject, owner, action, folder_path, supplier_key
        FROM sla_action_log
        ORDER BY actioned_at DESC
        """
    ).fetchall()
    open_rows = all_open_rows[:SLA_DRILLDOWN_LIMIT]
    action_rows = all_action_rows[:SLA_DRILLDOWN_LIMIT]

    latest_activity = _latest_sla_activity(all_open_rows, all_action_rows, now)
    week_start, week_end_exclusive, week_end = _sla_current_week_window(conn, latest_activity)
    weekly_owner_summary = _query_sla_weekly_owner_summary(conn)
    current_week_key = week_start.date().isoformat()
    current_week_summary = [
        row for row in weekly_owner_summary
        if row["week_start"] == current_week_key
    ]

    received_keys: set[str] = set()
    for row in all_open_rows:
        if _within_week(row["received_at"], week_start, week_end_exclusive):
            received_keys.add(str(row["email_key"]))
    for row in all_action_rows:
        if _within_week(row["received_at"], week_start, week_end_exclusive):
            received_keys.add(str(row["email_key"]))

    actioned_keys = {
        str(row["email_key"])
        for row in all_action_rows
        if _within_week(row["actioned_at"], week_start, week_end_exclusive)
    }
    weekly_received = len(received_keys)
    weekly_actioned = len(actioned_keys)
    weekly_gap = weekly_received - weekly_actioned
    weekly_net_change = (
        sum(int(row["net_change"] or 0) for row in current_week_summary)
        if current_week_summary
        else weekly_received - weekly_actioned
    )
    aged_open_emails = sum(
        1 for row in all_open_rows
        if _age_days(row["received_at"], now) >= 5
    )

    owner_map: dict[str, dict] = {}
    owner_received_keys: dict[str, set[str]] = {}
    owner_actioned_keys: dict[str, set[str]] = {}
    for row in all_open_rows:
        owner = row["owner"] or "Unassigned"
        bucket = owner_map.setdefault(
            owner,
            {
                "owner_display": owner,
                "open_count": 0,
                "received_this_week": 0,
                "actioned_this_week": 0,
                "weekly_gap": 0,
                "avg_weekly_actioned": 0,
                "avg_resolution_days": 0,
                "people_needed": 0,
            },
        )
        bucket["open_count"] += 1
        if _within_week(row["received_at"], week_start, week_end_exclusive):
            owner_received_keys.setdefault(owner, set()).add(str(row["email_key"]))
    for row in all_action_rows:
        owner = row["owner"] or "Unassigned"
        bucket = owner_map.setdefault(
            owner,
            {
                "owner_display": owner,
                "open_count": 0,
                "received_this_week": 0,
                "actioned_this_week": 0,
                "weekly_gap": 0,
                "avg_weekly_actioned": 0,
                "avg_resolution_days": 0,
                "people_needed": 0,
            },
        )
        if _within_week(row["received_at"], week_start, week_end_exclusive):
            owner_received_keys.setdefault(owner, set()).add(str(row["email_key"]))
        if _within_week(row["actioned_at"], week_start, week_end_exclusive):
            owner_actioned_keys.setdefault(owner, set()).add(str(row["email_key"]))
    for owner, bucket in owner_map.items():
        bucket["received_this_week"] = len(owner_received_keys.get(owner, set()))
        bucket["actioned_this_week"] = len(owner_actioned_keys.get(owner, set()))
    for bucket in owner_map.values():
        bucket["weekly_gap"] = bucket["received_this_week"] - bucket["actioned_this_week"]

    owner_week_counts: dict[tuple[str, str], set[str]] = {}
    owner_resolution_totals: dict[str, dict[str, float]] = {}
    resolution_keys: set[str] = set()
    total_resolution_days = 0.0
    total_resolution_count = 0
    for row in all_action_rows:
        actioned_at = _parse_sla_datetime(row["actioned_at"])
        if actioned_at is None:
            continue
        owner = str(row["owner"] or "Unassigned")
        owner_week = _sla_monday_week_start(actioned_at).date().isoformat()
        owner_week_counts.setdefault((owner, owner_week), set()).add(str(row["email_key"]))
        email_key = str(row["email_key"])
        if _within_week(row["actioned_at"], week_start, week_end_exclusive) and email_key not in resolution_keys:
            resolution_keys.add(email_key)
            duration = _duration_days(row["received_at"], row["actioned_at"])
            owner_total = owner_resolution_totals.setdefault(owner, {"days": 0.0, "count": 0})
            owner_total["days"] += duration
            owner_total["count"] += 1
            total_resolution_days += duration
            total_resolution_count += 1

    owner_weekly_actioned: dict[str, list[int]] = {}
    for (owner, _owner_week), keys in owner_week_counts.items():
        if keys:
            owner_weekly_actioned.setdefault(owner, []).append(len(keys))
    current_owner_count = sum(
        1 for bucket in owner_map.values()
        if bucket["open_count"] > 0 or bucket["actioned_this_week"] > 0
    )
    avg_weekly_actioned = (
        weekly_actioned / current_owner_count
        if current_owner_count
        else 0
    )
    avg_resolution_days = (
        total_resolution_days / total_resolution_count
        if total_resolution_count
        else 0
    )
    people_needed = (
        math.ceil(max(0, weekly_gap) / avg_weekly_actioned)
        if weekly_gap > 0 and avg_weekly_actioned > 0
        else 0
    )
    for owner, bucket in owner_map.items():
        owner_actioned_counts = owner_weekly_actioned.get(owner, [])
        owner_avg_actioned = bucket["actioned_this_week"] or (
            sum(owner_actioned_counts) / len(owner_actioned_counts)
            if owner_actioned_counts
            else avg_weekly_actioned
        )
        owner_resolution = owner_resolution_totals.get(owner, {"days": 0.0, "count": 0})
        bucket["avg_weekly_actioned"] = round(owner_avg_actioned, 2)
        bucket["avg_resolution_days"] = round(
            owner_resolution["days"] / owner_resolution["count"],
            2,
        ) if owner_resolution["count"] else 0
        bucket["people_needed"] = (
            math.ceil(max(0, bucket["weekly_gap"]) / owner_avg_actioned)
            if bucket["weekly_gap"] > 0 and owner_avg_actioned > 0
            else 0
        )

    open_emails = [
        {
            "received_at": row["received_at"],
            "age_days": _age_days(row["received_at"], now),
            "sender_email": row["sender_email"] or "",
            "sender_name": row["sender_name"] or "",
            "subject": row["subject"] or "",
            "owner_display": row["owner"] or "",
            "folder_path": row["folder_path"] or "",
            "sla_status": row["sla_status"] or "",
            "supplier_key": row["supplier_key"] or "",
        }
        for row in open_rows
    ]
    action_log = [
        {
            "received_at": row["received_at"],
            "actioned_at": row["actioned_at"],
            "sender_email": row["sender_email"] or "",
            "sender_name": row["sender_name"] or "",
            "subject": row["subject"] or "",
            "owner_display": row["owner"] or "",
            "action": row["action"] or "",
            "folder_path": row["folder_path"] or "",
            "time_to_action_days": _duration_days(row["received_at"], row["actioned_at"]),
            "supplier_key": row["supplier_key"] or "",
        }
        for row in action_rows
    ]

    supplier_map: dict[tuple[str, str], dict] = {}
    supplier_received_keys: dict[tuple[str, str], set[str]] = {}
    supplier_actioned_keys: dict[tuple[str, str], set[str]] = {}
    for row in all_open_rows:
        supplier = row["supplier_key"] or "unknown"
        owner = row["owner"] or "Unassigned"
        supplier_key = (supplier, owner)
        bucket = supplier_map.setdefault(
            supplier_key,
            {
                "supplier_key": supplier,
                "owner_display": owner,
                "open_count": 0,
                "received_this_week": 0,
                "actioned_this_week": 0,
            },
        )
        bucket["open_count"] += 1
        if _within_week(row["received_at"], week_start, week_end_exclusive):
            supplier_received_keys.setdefault(supplier_key, set()).add(str(row["email_key"]))
    for row in all_action_rows:
        supplier = row["supplier_key"] or "unknown"
        owner = row["owner"] or "Unassigned"
        supplier_key = (supplier, owner)
        bucket = supplier_map.setdefault(
            supplier_key,
            {
                "supplier_key": supplier,
                "owner_display": owner,
                "open_count": 0,
                "received_this_week": 0,
                "actioned_this_week": 0,
            },
        )
        if _within_week(row["received_at"], week_start, week_end_exclusive):
            supplier_received_keys.setdefault(supplier_key, set()).add(str(row["email_key"]))
        if _within_week(row["actioned_at"], week_start, week_end_exclusive):
            supplier_actioned_keys.setdefault(supplier_key, set()).add(str(row["email_key"]))
    for supplier_key, bucket in supplier_map.items():
        bucket["received_this_week"] = len(supplier_received_keys.get(supplier_key, set()))
        bucket["actioned_this_week"] = len(supplier_actioned_keys.get(supplier_key, set()))

    payload = _empty_sla_tracker(generated_at)
    payload.update({
        "source_updated_at": _sla_source_updated_at(conn),
        "kpis": {
            "open_emails": len(all_open_rows),
            "weekly_received": weekly_received,
            "weekly_actioned": weekly_actioned,
            "weekly_gap": weekly_gap,
            "people_needed": people_needed,
            "weekly_net_change": weekly_net_change,
            "aged_open_emails": aged_open_emails,
            "avg_weekly_actioned_per_owner": round(avg_weekly_actioned, 2),
            "avg_resolution_days": round(avg_resolution_days, 2),
            "current_week_start": week_start.date().isoformat(),
            "current_week_end": week_end.date().isoformat(),
        },
        "owner_summary": sorted(
            owner_map.values(),
            key=lambda item: (-item["open_count"], -item["weekly_gap"], item["owner_display"]),
        ),
        "weekly_owner_summary": weekly_owner_summary,
        "daily_history": _query_sla_daily_history(conn),
        "open_emails": open_emails,
        "action_log": action_log,
        "supplier_summary": sorted(
            supplier_map.values(),
            key=lambda item: (
                -item["actioned_this_week"],
                -item["open_count"],
                item["supplier_key"],
                item["owner_display"],
            ),
        ),
    })
    return payload


def _sla_payload_has_rows(payload: dict) -> bool:
    """Return True when an SLA payload would render non-empty UI content."""
    kpis = payload.get("kpis") or {}
    return bool(
        kpis.get("open_emails")
        or payload.get("owner_summary")
        or payload.get("weekly_owner_summary")
        or payload.get("daily_history")
        or payload.get("open_emails")
        or payload.get("action_log")
        or payload.get("supplier_summary")
    )


def _query_sla_tracker_with_fallback(
    conn: sqlite3.Connection,
    *,
    fallback_db_path: Path | None = None,
    now_iso: str | None = None,
) -> dict:
    """Query SLA tracker data, falling back to the dashboard DB mirror when needed.

    The operator pack can have an already-published dashboard/data/invoices.db
    mirror with SLA tables while the primary runtime DB lacks those tables. In
    that case, keeping SLA in data.js matches the existing static dashboard
    artifact pattern without changing browser-side chunk/resource loading.
    """
    payload = _query_sla_tracker(conn, now_iso=now_iso)
    if _has_sla_tracker_tables(conn) or fallback_db_path is None or not fallback_db_path.exists():
        return payload

    try:
        fallback_path = fallback_db_path.resolve()
        primary_path = Path(conn.execute("PRAGMA database_list").fetchone()["file"]).resolve()
    except (OSError, TypeError, sqlite3.Error):
        fallback_path = fallback_db_path
        primary_path = Path("")

    if fallback_path == primary_path:
        return payload

    try:
        with sqlite3.connect(str(fallback_db_path)) as fallback_conn:
            fallback_conn.row_factory = sqlite3.Row
            fallback_payload = _query_sla_tracker(fallback_conn, now_iso=now_iso)
    except sqlite3.Error as err:
        logger.warning("[WARN] Could not read SLA dashboard DB mirror %s: %s", fallback_db_path, err)
        return payload

    if _sla_payload_has_rows(fallback_payload):
        logger.warning(
            "[WARN] Primary DB has no SLA tables; using SLA payload from dashboard DB mirror: %s",
            fallback_db_path,
        )
        return fallback_payload
    return payload

def build_week_data(
    rows: list,
    week_start: str,
    week_end: str,
    extraction_date: str,
    absences: dict[str, list[dict]] | None = None,
    production_overrides: list[dict] | None = None,
) -> dict:
    """Build daily breakdown and weekly totals from a set of invoice rows."""
    included_members = set(ALL_MEMBERS)  # active + former: aggregate former members' history too
    daily: dict = {}
    for row in rows:
        date = row["entry_date"]
        member = row["team_member"]
        if member not in included_members:
            continue
        country = row["country"] or "Other"
        doc_type = row["document_type"]

        if date not in daily:
            daily[date] = {}
        if member not in daily[date]:
            daily[date][member] = {
                "total": 0, "by_country": {}, "by_doc_type": {},
                "reversal_count": 0, "credit_note_count": 0,
            }

        daily[date][member]["total"] += 1

        if country not in daily[date][member]["by_country"]:
            daily[date][member]["by_country"][country] = 0
        daily[date][member]["by_country"][country] += 1

        if doc_type and doc_type not in daily[date][member]["by_doc_type"]:
            daily[date][member]["by_doc_type"][doc_type] = 0
        if doc_type:
            daily[date][member]["by_doc_type"][doc_type] += 1

        if row["is_reversal"]:
            daily[date][member]["reversal_count"] += 1
        if doc_type in CREDIT_NOTE_TYPES:
            daily[date][member]["credit_note_count"] += 1

    # Fill in missing members for each day
    for date in daily:
        for member in ALL_MEMBERS:
            if member not in daily[date]:
                daily[date][member] = {
                    "total": 0, "by_country": {}, "by_doc_type": {},
                    "reversal_count": 0, "credit_note_count": 0,
                }

    # Build weekly totals
    weekly_totals: dict = {}
    for member in ALL_MEMBERS:
        weekly_totals[member] = {
            "total": 0, "by_country": {}, "by_doc_type": {},
            "reversal_count": 0, "credit_note_count": 0,
        }

    for row in rows:
        member = row["team_member"]
        if member not in included_members:
            continue
        country = row["country"] or "Other"
        doc_type = row["document_type"]

        weekly_totals[member]["total"] += 1
        if country not in weekly_totals[member]["by_country"]:
            weekly_totals[member]["by_country"][country] = 0
        weekly_totals[member]["by_country"][country] += 1
        if doc_type and doc_type not in weekly_totals[member]["by_doc_type"]:
            weekly_totals[member]["by_doc_type"][doc_type] = 0
        if doc_type:
            weekly_totals[member]["by_doc_type"][doc_type] += 1
        if row["is_reversal"]:
            weekly_totals[member]["reversal_count"] += 1
        if doc_type in CREDIT_NOTE_TYPES:
            weekly_totals[member]["credit_note_count"] += 1

    _apply_production_overrides(daily, weekly_totals, production_overrides, included_members)

    # Format label
    try:
        ws = datetime.strptime(week_start, "%Y-%m-%d")
        we = datetime.strptime(week_end, "%Y-%m-%d")
        label = f"{ws.strftime('%d %b')} - {we.strftime('%d %b %Y')}"
    except (ValueError, TypeError):
        label = f"{week_start} to {week_end}"

    working_days = len([d for d in daily.keys() if d])
    absences_map = {
        member: entries
        for member, entries in (absences or {}).items()
        if member in included_members
    }
    working_days_per_member = {
        m: max(1, WORKING_DAYS_PER_WEEK - sum(
            0.5 if a.get("type") == "Half Day" else 1
            for a in absences_map.get(m, [])
        ))
        for m in ALL_MEMBERS
    }

    return {
        "week_start": week_start,
        "week_end": week_end,
        "extraction_date": extraction_date,
        "label": label,
        "working_days": max(working_days, 1),
        "working_days_per_member": working_days_per_member,
        "absences": absences_map,
        "daily": dict(sorted(daily.items())),
        "weekly_totals": weekly_totals,
    }


def compress_blob(data: dict | list) -> tuple[str, int, int]:
    """Compress a Python object to base64-encoded zlib string."""
    json_str = json.dumps(data, separators=(",", ":"), default=str)
    compressed = zlib.compress(json_str.encode("utf-8"), level=9)
    return base64.b64encode(compressed).decode("ascii"), len(json_str), len(compressed)


def build_trend_entry(week_data: dict) -> dict:
    """Extract per-member weekly_totals for trend pre-computation."""
    empty = {"total": 0, "by_country": {}, "by_doc_type": {}, "reversal_count": 0, "credit_note_count": 0}
    return {m: week_data["weekly_totals"].get(m, empty) for m in ALL_MEMBERS}


def _query_all_weeks(
    conn: sqlite3.Connection,
    absences_by_week: dict[str, dict[str, list[dict]]] | None = None,
    production_overrides_by_week_type: dict[tuple[str, str], list[dict]] | None = None,
) -> tuple[list, list, list]:
    """Query all weeks from SQLite and build week data lists (manual, csv, envoy)."""
    weeks_rows = conn.execute(
        "SELECT DISTINCT extraction_date, week_start, week_end "
        "FROM weekly_imports ORDER BY week_start ASC"
    ).fetchall()

    manual_weeks: list[dict] = []
    csv_weeks: list[dict] = []
    envoy_weeks: list[dict] = []

    for week_row in weeks_rows:
        extraction_date = week_row["extraction_date"]
        week_start = week_row["week_start"]
        week_end = week_row["week_end"]

        # Validate all dates before use in SQL queries and filenames
        validate_extraction_date(extraction_date)
        validate_extraction_date(week_start)
        validate_extraction_date(week_end)

        manual_rows = conn.execute(
            "SELECT * FROM invoices WHERE extraction_date = ? AND is_csv = 0",
            (extraction_date,),
        ).fetchall()
        csv_rows = conn.execute(
            "SELECT * FROM invoices WHERE extraction_date = ? AND is_csv = 1",
            (extraction_date,),
        ).fetchall()
        envoy_rows = conn.execute(
            "SELECT * FROM invoices WHERE extraction_date = ? AND is_csv = 2",
            (extraction_date,),
        ).fetchall()

        abs_week = (absences_by_week or {}).get(week_start, {})
        overrides_by_type = production_overrides_by_week_type or {}
        if manual_rows:
            manual_weeks.append(build_week_data(
                manual_rows, week_start, week_end, extraction_date, abs_week,
                overrides_by_type.get((week_start, "manual"), []),
            ))
        if csv_rows:
            csv_weeks.append(build_week_data(
                csv_rows, week_start, week_end, extraction_date, abs_week,
                overrides_by_type.get((week_start, "csv"), []),
            ))
        if envoy_rows:
            envoy_weeks.append(build_week_data(
                envoy_rows, week_start, week_end, extraction_date, abs_week,
                overrides_by_type.get((week_start, "envoy"), []),
            ))

    return manual_weeks, csv_weeks, envoy_weeks


def _query_invoices(conn: sqlite3.Connection) -> list[dict]:
    """Query all invoice rows for the detail table."""
    all_invoices = conn.execute(
        """SELECT reference, entry_date, posting_date, document_date, team_member, vendor_name,
                  supplier_number, company_code, country, payment_block,
                  document_type, is_csv, extraction_date, system, amount, document_number, is_reversal
           FROM invoices ORDER BY entry_date DESC, team_member"""
    ).fetchall()

    return [
        {
            "reference": row["reference"],
            "entry_date": row["entry_date"],
            "posting_date": row["posting_date"],
            "document_date": row["document_date"],
            "team_member": row["team_member"],
            "vendor_name": row["vendor_name"],
            "supplier_number": row["supplier_number"],
            "company_code": row["company_code"],
            "country": row["country"],
            "payment_block": row["payment_block"] or "",
            "document_type": row["document_type"],
            "is_csv": row["is_csv"],
            "extraction_date": row["extraction_date"],
            "system": row["system"],
            "amount": row["amount"],
            "document_number": row["document_number"],
            "is_reversal": row["is_reversal"],
        }
        for row in all_invoices
    ]


def _build_trend_data(
    manual_weeks: list[dict],
    csv_weeks: list[dict],
    envoy_weeks: list[dict],
) -> list[dict]:
    """Build the trend_data list from all week types."""
    all_extraction_dates: dict = {}
    for w in manual_weeks + csv_weeks + envoy_weeks:
        ed = w["extraction_date"]
        if ed not in all_extraction_dates:
            all_extraction_dates[ed] = {
                "week_start": w["week_start"], "week_end": w["week_end"],
                "label": w["label"], "working_days": w["working_days"],
            }

    manual_by_ed = {w["extraction_date"]: w for w in manual_weeks}
    csv_by_ed = {w["extraction_date"]: w for w in csv_weeks}
    envoy_by_ed = {w["extraction_date"]: w for w in envoy_weeks}

    trend_data = []
    for ed in sorted(all_extraction_dates.keys(), reverse=True):
        meta = all_extraction_dates[ed]
        entry = {
            "extraction_date": ed,
            "week_start": meta["week_start"],
            "week_end": meta["week_end"],
            "label": meta["label"],
            "working_days": meta["working_days"],
        }
        if ed in manual_by_ed:
            entry["manual"] = build_trend_entry(manual_by_ed[ed])
        if ed in csv_by_ed:
            entry["csv"] = build_trend_entry(csv_by_ed[ed])
        if ed in envoy_by_ed:
            entry["envoy"] = build_trend_entry(envoy_by_ed[ed])
        trend_data.append(entry)

    return trend_data


def _collect_metadata(
    manual_weeks: list[dict],
    csv_weeks: list[dict],
    envoy_weeks: list[dict],
) -> tuple[list[str], list[str]]:
    """Collect all countries and doc types across all weeks."""
    all_countries: set[str] = set()
    all_doc_types: set[str] = set()
    for w in manual_weeks + csv_weeks + envoy_weeks:
        for m in ALL_MEMBERS:
            wt = w["weekly_totals"].get(m, {})
            all_countries.update(wt.get("by_country", {}).keys())
            all_doc_types.update(wt.get("by_doc_type", {}).keys())
    return sorted(all_countries), sorted(all_doc_types)


def _week_index(w: dict) -> dict:
    """Extract metadata-only index entry from a week dict."""
    return {
        "week_start": w["week_start"], "week_end": w["week_end"],
        "extraction_date": w["extraction_date"], "label": w["label"],
        "working_days": w["working_days"],
    }


def _split_core_and_historical(
    weeks: list[dict], core_count: int = 2,
) -> tuple[list[dict], list[dict]]:
    """Split weeks into core (last N) and historical (older).

    Weeks must be sorted by week_start ASC (oldest first).
    Returns (core_weeks, historical_weeks).
    """
    if len(weeks) <= core_count:
        return weeks, []
    return weeks[-core_count:], weeks[:-core_count]


def _compress_weeks_dict(
    weeks_list: list[dict], type_name: str,
) -> tuple[dict[str, str], int, int]:
    """Compress a list of week dicts into a key->base64 dict."""
    compressed: dict[str, str] = {}
    total_orig = 0
    total_comp = 0
    for w in weeks_list:
        key = f"{type_name}_{w['extraction_date']}"
        blob_data = {
            "daily": w["daily"],
            "weekly_totals": w["weekly_totals"],
            "working_days_per_member": w.get("working_days_per_member", {}),
            "absences": w.get("absences", {}),
        }
        b64, orig_sz, comp_sz = compress_blob(blob_data)
        compressed[key] = b64
        total_orig += orig_sz
        total_comp += comp_sz
    return compressed, total_orig, total_comp


def _write_tier3_chunks(
    manual_hist: list[dict],
    csv_hist: list[dict],
    envoy_hist: list[dict],
) -> int:
    """Write Tier 3 per-week chunk files to data_chunks/.

    Each historical week_start gets its own .js file containing
    compressed data for all types (manual/csv/envoy) present for that week.

    Returns number of chunk files written.
    """
    DATA_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    # Group all historical weeks by week_start
    by_week_start: dict[str, dict[str, dict]] = {}
    for type_name, hist_list in [("manual", manual_hist), ("csv", csv_hist), ("envoy", envoy_hist)]:
        for w in hist_list:
            ws = w["week_start"]
            if ws not in by_week_start:
                by_week_start[ws] = {}
            by_week_start[ws][type_name] = w

    expected_chunk_names = {f"week_{week_start}.js" for week_start in by_week_start}
    for stale in DATA_CHUNKS_DIR.glob("week_*.js"):
        if stale.name not in expected_chunk_names:
            stale.unlink()
            logger.info("  Removed stale Tier 3 chunk: %s", stale.name)

    chunks_written = 0
    for week_start, type_weeks in sorted(by_week_start.items()):
        # Validate week_start before using in filename construction
        validate_extraction_date(week_start)

        chunk_data: dict[str, str] = {}
        meta: dict = {}
        for type_name, w in type_weeks.items():
            blob_data = {
                "daily": w["daily"],
                "weekly_totals": w["weekly_totals"],
                "working_days_per_member": w.get("working_days_per_member", {}),
                "absences": w.get("absences", {}),
            }
            b64, _, _ = compress_blob(blob_data)
            chunk_data[type_name] = b64
            if not meta:
                meta = {
                    "week_start": w["week_start"],
                    "week_end": w["week_end"],
                    "extraction_date": w["extraction_date"],
                    "label": w["label"],
                    "working_days": w["working_days"],
                }

        chunk_obj = {"meta": meta, "compressed_weeks": chunk_data}
        var_name = f"WEEK_{week_start.replace('-', '_')}"
        chunk_js = f"// Auto-generated chunk for week {week_start}\n"
        chunk_js += f"window.{var_name} = {json.dumps(chunk_obj, separators=(',', ':'))};\n"

        chunk_path = DATA_CHUNKS_DIR / f"week_{week_start}.js"
        with open(chunk_path, "w", encoding="utf-8") as f:
            f.write(chunk_js)

        chunks_written += 1
        logger.info("  Tier 3 chunk: %s (%.1f KB)", chunk_path.name, len(chunk_js) / 1024)

    return chunks_written


def _write_tier2_trend_cube(trend_data: list[dict]) -> None:
    """Write Tier 2 trend cube to data_chunks/trend_cube.js."""
    DATA_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    b64, orig_sz, comp_sz = compress_blob(trend_data)
    trend_js = "// Auto-generated trend cube\n"
    trend_js += f"window.TREND_CUBE = {json.dumps(b64)};\n"

    trend_path = DATA_CHUNKS_DIR / "trend_cube.js"
    with open(trend_path, "w", encoding="utf-8") as f:
        f.write(trend_js)

    logger.info("  Tier 2 trend cube: %s (%.1f KB, compressed from %.1f KB)",
                trend_path.name, len(trend_js) / 1024, orig_sz / 1024)


def export_data_js() -> None:
    """Query SQLite and generate 3-tier data files.

    Tier 1: data.js - Core data (last 2 weeks) + metadata + compressed invoices
    Tier 2: data_chunks/trend_cube.js - Trend data for all weeks (async load)
    Tier 3: data_chunks/week_YYYY-MM-DD.js - Historical week data (on-demand)
    """
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    DATA_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    if not DB_PATH.exists():
        raise FileNotFoundError("Database not found. Run bootstrap_local or process_invoices first.")

    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row

        weeks_rows = conn.execute(
            "SELECT DISTINCT extraction_date FROM weekly_imports"
        ).fetchall()

        if not weeks_rows:
            raise RuntimeError("Required weekly_imports query returned zero rows.")

        # Query all weeks (sorted ASC by week_start)
        absences_by_week = _query_absences(conn)
        production_overrides = _query_production_overrides(conn)
        production_overrides_by_week_type = _group_production_overrides(production_overrides)
        sla_tracker = _query_sla_tracker_with_fallback(
            conn,
            fallback_db_path=DASHBOARD_DIR / "data" / "invoices.db",
        )
        manual_weeks, csv_weeks, envoy_weeks = _query_all_weeks(
            conn,
            absences_by_week,
            production_overrides_by_week_type,
        )
        invoices_list = _query_invoices(conn)
        if not invoices_list:
            raise RuntimeError("Required invoices query returned zero rows.")
        calendar_absences = _flatten_absences(absences_by_week)

    # --- Split into tiers ---
    manual_core, manual_hist = _split_core_and_historical(manual_weeks)
    csv_core, csv_hist = _split_core_and_historical(csv_weeks)
    envoy_core, envoy_hist = _split_core_and_historical(envoy_weeks)

    logger.info("Week split: manual=%d core + %d hist, csv=%d core + %d hist, envoy=%d core + %d hist",
                len(manual_core), len(manual_hist),
                len(csv_core), len(csv_hist),
                len(envoy_core), len(envoy_hist))

    # --- Tier 1: Core data.js (last 2 weeks + metadata) ---
    # Compress core weeks
    core_compressed: dict[str, str] = {}
    total_orig = 0
    total_comp = 0
    for type_name, core_list in [("manual", manual_core), ("csv", csv_core), ("envoy", envoy_core)]:
        cw, orig, comp = _compress_weeks_dict(core_list, type_name)
        core_compressed.update(cw)
        total_orig += orig
        total_comp += comp

    if total_orig > 0:
        logger.info("Core weeks compression: %.1f KB -> %.1f KB (%.1f%%)",
                     total_orig / 1024, total_comp / 1024, total_comp / total_orig * 100)

    # Compress invoices
    inv_b64, inv_orig, inv_comp = compress_blob(invoices_list)
    logger.info("Invoices compression: %.1f KB -> %.1f KB (%.1f%%)",
                inv_orig / 1024, inv_comp / 1024, inv_comp / max(inv_orig, 1) * 100)

    # Build indexes for ALL weeks (core + historical) so the dashboard knows what exists
    all_manual = manual_weeks  # already sorted ASC
    all_csv = csv_weeks
    all_envoy = envoy_weeks

    manual_week_index = [_week_index(w) for w in all_manual]
    csv_week_index = [_week_index(w) for w in all_csv]
    envoy_week_index = [_week_index(w) for w in all_envoy]

    # Build trend_data (for all weeks)
    trend_data = _build_trend_data(all_manual, all_csv, all_envoy)

    # Collect metadata
    all_countries, all_doc_types = _collect_metadata(all_manual, all_csv, all_envoy)

    # List of historical week_starts so the dashboard knows which chunks exist
    hist_week_starts: set[str] = set()
    for w in manual_hist + csv_hist + envoy_hist:
        hist_week_starts.add(w["week_start"])

    # Build Tier 1 data object
    dashboard_data = {
        "team_members": TEAM_MEMBERS,
        "former_members": sorted(FORMER_MEMBERS),
        "doc_type_labels": DOC_TYPE_LABELS,
        "daily_target": DAILY_TARGET,
        "individual_targets": INDIVIDUAL_TARGETS,
        "working_days": WORKING_DAYS_PER_WEEK,
        "all_countries": all_countries,
        "all_doc_types": all_doc_types,
        "manual_week_index": manual_week_index,
        "csv_week_index": csv_week_index,
        "envoy_week_index": envoy_week_index,
        "compressed_weeks": core_compressed,
        "compressed_invoices": inv_b64,
        "trend_data": trend_data,
        "calendar_absences": calendar_absences,
        "production_overrides": production_overrides,
        "sla_tracker": sla_tracker,
        "chunked": True,
        "chunk_week_starts": sorted(hist_week_starts),
    }

    # Write data.js (Tier 1)
    js_content = "// Auto-generated by export_dashboard.py - DO NOT EDIT\n"
    js_content += f"const DASHBOARD_DATA = {json.dumps(dashboard_data, separators=(',', ':'))};\n"

    with open(DATA_JS_PATH, "w", encoding="utf-8") as f:
        f.write(js_content)

    data_kb = len(js_content) / 1024
    logger.info("Tier 1 (core data.js): %s (%.1f KB)", DATA_JS_PATH, data_kb)

    # --- Tier 2: Trend cube ---
    logger.info("Generating Tier 2 (trend cube)...")
    _write_tier2_trend_cube(trend_data)

    # --- Tier 3: Historical week chunks ---
    if manual_hist or csv_hist or envoy_hist:
        logger.info("Generating Tier 3 (historical week chunks)...")
        n_chunks = _write_tier3_chunks(manual_hist, csv_hist, envoy_hist)
        logger.info("Tier 3: %d chunk file(s) written.", n_chunks)
    else:
        logger.info("Tier 3: No historical weeks to chunk (all weeks are core).")
        for stale in DATA_CHUNKS_DIR.glob("week_*.js"):
            stale.unlink()
            logger.info("  Removed stale Tier 3 chunk: %s", stale.name)

    # Summary
    m_total = sum(sum(m["total"] for m in w["weekly_totals"].values()) for w in all_manual)
    c_total = sum(sum(m["total"] for m in w["weekly_totals"].values()) for w in all_csv)
    e_total = sum(sum(m["total"] for m in w["weekly_totals"].values()) for w in all_envoy)
    logger.info("Manual weeks: %d (%d invoices)", len(all_manual), m_total)
    logger.info("CSV weeks: %d (%d invoices)", len(all_csv), c_total)
    logger.info("Envoy weeks: %d (%d invoices)", len(all_envoy), e_total)
    logger.info("Detail table: %d rows", len(invoices_list))
    logger.info("Trend entries: %d", len(trend_data))


def _read_lib(filename: str) -> str:
    """Read a library file from the libs/ directory."""
    path = LIBS_DIR / filename
    if not path.exists():
        logger.warning("%s not found", path)
        return f"// {filename} not found"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def generate_dashboard_html() -> str:
    """Generate the complete index.html with inlined libraries."""
    # Import here to avoid circular imports at module level
    from scripts.dashboard.html_template import HTML_TEMPLATE

    chart_js = _read_lib("chart.umd.min.js")
    pako_js = _read_lib("pako.min.js")

    html = HTML_TEMPLATE
    html = html.replace("__CHARTJS_INLINE__", chart_js)
    html = html.replace("__PAKO_INLINE__", pako_js)
    html = html.replace(
        "__BUILD_VERSION__",
        datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
    )

    logger.info("Inlined: Chart.js (%dKB), Pako (%dKB)", len(chart_js) // 1024, len(pako_js) // 1024)
    return html


def export_html(force: bool = False) -> None:
    """Generate index.html if it doesn't exist or force is True."""
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    if HTML_PATH.exists() and not force:
        logger.info("HTML exists: %s (use --force-html to regenerate)", HTML_PATH)
        return

    html = generate_dashboard_html()
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = len(html) / 1024
    logger.info("Generated: %s (%.1f KB)", HTML_PATH, size_kb)


def _ensure_calendar_tree(calendar_dir: Path) -> None:
    """Ensure Calendar folders exist without deleting user-saved JSON files."""
    for child in REQUIRED_CALENDAR_DIRS:
        target = calendar_dir / child
        try:
            if target.is_dir():
                continue
        except PermissionError:
            continue
        target.mkdir(parents=True, exist_ok=True)


def _missing_required_files(root: Path) -> list[Path]:
    """Return required deployment files missing under a root directory."""
    return [root / rel_path for rel_path in REQUIRED_DEPLOY_FILES if not (root / rel_path).exists()]


def _verify_deploy_tree(root: Path, label: str, *, require_calendar: bool = True) -> None:
    """Verify a local/temp/final dashboard tree has the required runtime files."""
    missing = _missing_required_files(root)
    if missing:
        raise OSError(f"{label} deployment verification failed. Missing: {[str(f) for f in missing]}")

    if not require_calendar:
        return

    calendar_dir = root / "Calendar"
    missing_calendar = [calendar_dir / child for child in REQUIRED_CALENDAR_DIRS if not (calendar_dir / child).exists()]
    if missing_calendar:
        raise OSError(
            f"{label} Calendar verification failed. Missing: {[str(f) for f in missing_calendar]}"
        )


def _write_deploy_manifest(root: Path) -> None:
    """Write a small deployment manifest so the published folder is auditable."""
    chunks_dir = root / "data_chunks"
    chunk_files = (
        sorted(p.name for p in chunks_dir.iterdir() if p.is_file() and p.suffix == ".js")
        if chunks_dir.is_dir()
        else []
    )
    file_sizes: dict[str, int | None] = {}
    for path in REQUIRED_DEPLOY_FILES:
        key = str(path).replace("\\", "/")
        try:
            file_sizes[key] = (root / path).stat().st_size
        except OSError:
            file_sizes[key] = None

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "required_files": [str(path).replace("\\", "/") for path in REQUIRED_DEPLOY_FILES],
        "chunk_count": len(chunk_files),
        "chunk_files": chunk_files,
        "calendar_dirs": list(REQUIRED_CALENDAR_DIRS),
        "files": file_sizes,
    }
    manifest_path = root / DEPLOY_MANIFEST_NAME
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def _tmp_copy_path(path: Path) -> Path:
    """Return a same-directory temp path for atomic file replacement."""
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def _files_equal(src: Path, dst: Path) -> bool:
    """Return True when both files exist and have identical bytes."""
    if not dst.exists():
        return False
    if src.stat().st_size != dst.stat().st_size:
        return False
    return filecmp.cmp(src, dst, shallow=False)


def _copy_if_changed(src: Path, dst: Path) -> bool:
    """Copy src to dst atomically only when bytes differ."""
    if _files_equal(src, dst):
        return False

    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_copy_path(dst)
    try:
        shutil.copy2(str(src), str(tmp))
        os.replace(tmp, dst)
        return True
    finally:
        if tmp.exists():
            tmp.unlink()


def _sync_tree_if_changed(src_dir: Path, dst_dir: Path) -> tuple[int, int]:
    """Sync a generated directory tree file-by-file, preserving unrelated files."""
    changed = 0
    total = 0
    if not src_dir.exists():
        return changed, total

    for src in sorted(path for path in src_dir.rglob("*") if path.is_file()):
        rel = src.relative_to(src_dir)
        if _copy_if_changed(src, dst_dir / rel):
            changed += 1
        total += 1
    return changed, total


def _sync_generated_chunks(src_dir: Path, dst_dir: Path) -> tuple[int, int]:
    """Sync generated JS chunk files and prune stale week chunks only."""
    changed = 0
    pruned = 0
    if not src_dir.exists():
        return changed, pruned

    expected = {path.name for path in src_dir.glob("*.js")}
    dst_dir.mkdir(parents=True, exist_ok=True)

    for name in sorted(expected):
        if _copy_if_changed(src_dir / name, dst_dir / name):
            changed += 1

    for stale in dst_dir.glob("week_*.js"):
        if stale.name not in expected:
            stale.unlink()
            pruned += 1

    return changed, pruned


def _deploy_dashboard_legacy() -> None:
    """Atomically deploy dashboard files to shared network drive with rollback capability.

    Uses atomic deployment pattern:
    1. Create backup of existing deployment (if exists)
    2. Deploy to temporary directory (.temp_*)
    3. Verify critical files exist
    4. Atomic rename temporary  final
    5. Cleanup backup on success, or rollback on failure

    Fails fast with actionable error if the deploy directory parent
    (typically S: drive) is not accessible, preventing silent failures
    where stale data remains on the shared drive.
    """
    deploy_dir = str(DEPLOY_DIR)
    deploy_parent = DEPLOY_DIR.parent
    deploy_name = DEPLOY_DIR.name
    temp_dir = deploy_parent / f".temp_{deploy_name}"
    backup_dir = deploy_parent / f".backup_{deploy_name}"
    calendar_name = "Calendar"
    backup_created = False

    try:
        # Health check: verify deploy directory parent is accessible
        # This catches unmapped network drives (e.g., S: not mapped)
        if not deploy_parent.exists():
            logger.error(
                "Deploy directory parent not accessible: %s",
                deploy_parent,
            )
            logger.error(
                "  S: drive may not be mapped. Run 'net use S: "
                "\\\\<server>\\<share>' or set env var:"
            )
            logger.error(
                "  set INVOICE_DASHBOARD_DEPLOY_DIR=<path>"
            )
            sys.exit(1)

        # Validate local generated files before touching the shared drive.
        _verify_deploy_tree(DASHBOARD_DIR, "Local dashboard", require_calendar=False)

        # Step 1: Create backup of existing deployment (if possible - Local Fixture Store may prevent)
        if DEPLOY_DIR.exists():
            # Try to remove old backup if it exists
            if backup_dir.exists():
                try:
                    shutil.rmtree(str(backup_dir))
                except (PermissionError, OSError):
                    pass  # Ignore, will be overwritten or left

            # Try to move current deployment to backup
            try:
                shutil.move(str(DEPLOY_DIR), str(backup_dir))
                logger.info("Created backup: %s", backup_dir)
                backup_created = True
            except (PermissionError, OSError) as move_err:
                logger.warning("Could not create backup (Local Fixture Store lock?): %s", move_err)
                logger.info("Deployment will overwrite existing files directly")

        # Step 2: Deploy to temporary directory
        if temp_dir.exists():
            try:
                shutil.rmtree(str(temp_dir))
            except (PermissionError, OSError) as e:
                logger.warning("Could not remove old temp dir (Local Fixture Store lock?), will overwrite: %s", e)
        temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Deploying to temp: %s", temp_dir)

        # Copy files to temp directory
        files_to_copy = ["index.html", "data.js"]
        for fname in files_to_copy:
            src = DASHBOARD_DIR / fname
            dst = temp_dir / fname
            if src.exists():
                shutil.copy2(str(src), str(dst))
                logger.info("[OK] %s -> %s", fname, temp_dir)
            else:
                logger.warning("[WARN] %s not found, skipping.", src)

        # Deploy css/ folder
        css_src = DASHBOARD_DIR / "css"
        css_dst = temp_dir / "css"
        if css_src.exists():
            shutil.copytree(str(css_src), str(css_dst), dirs_exist_ok=True)
            logger.info("[OK] css/ -> %s", temp_dir)

        # Deploy dist/ folder (webpack bundle)
        dist_src = DASHBOARD_DIR / "dist"
        dist_dst = temp_dir / "dist"
        if dist_src.exists():
            shutil.copytree(str(dist_src), str(dist_dst), dirs_exist_ok=True)
            logger.info("[OK] dist/ -> %s", temp_dir)

        # Deploy data_chunks/ (Tier 2 + Tier 3)
        if DATA_CHUNKS_DIR.exists() and any(DATA_CHUNKS_DIR.iterdir()):
            deploy_chunks = temp_dir / "data_chunks"
            deploy_chunks.mkdir(parents=True, exist_ok=True)
            chunk_count = 0
            for chunk_file in DATA_CHUNKS_DIR.iterdir():
                if chunk_file.suffix == ".js":
                    shutil.copy2(str(chunk_file), str(deploy_chunks / chunk_file.name))
                    chunk_count += 1
            logger.info("[OK] data_chunks/ -> %s (%d files)", deploy_chunks, chunk_count)

        # Deploy SQLite database
        data_dir = temp_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        if DB_PATH.exists():
            dst_db = data_dir / "invoices.db"
            shutil.copy2(str(DB_PATH), str(dst_db))
            sz = dst_db.stat().st_size / (1024 * 1024)
            logger.info("[OK] invoices.db -> %s (%.1f MB)", data_dir, sz)

        # Preserve Calendar folder inside the published dashboard.
        # The dashboard writes TL-created absence JSON files here; deploy must
        # never delete or replace that operational state.
        preserved_calendar = None
        if backup_created and (backup_dir / calendar_name).exists():
            preserved_calendar = backup_dir / calendar_name
        elif (DEPLOY_DIR / calendar_name).exists():
            preserved_calendar = DEPLOY_DIR / calendar_name

        temp_calendar = temp_dir / calendar_name
        if preserved_calendar is not None:
            shutil.copytree(str(preserved_calendar), str(temp_calendar), dirs_exist_ok=True)
            logger.info("[OK] Preserved Calendar/ -> %s", temp_calendar)
        _ensure_calendar_tree(temp_calendar)

        # Step 3: Verify critical files and Calendar tree in temp directory
        _verify_deploy_tree(temp_dir, "Temp dashboard")
        _write_deploy_manifest(temp_dir)
        logger.info("Temp deployment verified")

        # Step 4: Atomic rename temp  final (with Local Fixture Store fallback)
        try:
            shutil.move(str(temp_dir), str(DEPLOY_DIR))
            logger.info("Atomic rename: %s  %s", temp_dir.name, deploy_name)
        except (PermissionError, OSError) as move_err:
            # Fallback for Local Fixture Store locks: copy + verify + delete old
            logger.warning("Atomic rename failed (Local Fixture Store lock?): %s", move_err)
            logger.info("Using fallback: copy + verify + delete")

            # Copy temp  final
            shutil.copytree(str(temp_dir), str(DEPLOY_DIR), dirs_exist_ok=True)
            logger.info("Copied: %s  %s", temp_dir.name, deploy_name)

            _ensure_calendar_tree(DEPLOY_DIR / calendar_name)
            _verify_deploy_tree(DEPLOY_DIR, "Fallback dashboard")
            _write_deploy_manifest(DEPLOY_DIR)
            logger.info("Fallback deployment verified")

        _ensure_calendar_tree(DEPLOY_DIR / calendar_name)
        _verify_deploy_tree(DEPLOY_DIR, "Final dashboard")
        _write_deploy_manifest(DEPLOY_DIR)
        logger.info("Final deployment verified")

        # Step 5: Cleanup backup on success (only if backup was created)
        if backup_created and backup_dir.exists():
            try:
                shutil.rmtree(str(backup_dir))
                logger.info("Backup cleanup complete")
            except (PermissionError, OSError) as e:
                logger.warning("Could not clean up backup (Local Fixture Store lock?): %s", e)
                logger.warning("Backup will remain: %s", backup_dir)

        logger.info("Deploy complete (atomic): %s", deploy_dir)

    except Exception as exc:
        # Rollback: restore from backup if it was created and deployment is gone
        logger.error("Deployment failed: %s", exc)
        if backup_created and backup_dir.exists() and not DEPLOY_DIR.exists():
            try:
                logger.info("Rolling back from backup...")
                shutil.move(str(backup_dir), str(DEPLOY_DIR))
                logger.info("Rollback complete: restored from backup")
            except (PermissionError, OSError) as rollback_err:
                logger.error("Rollback failed (Local Fixture Store lock?): %s", rollback_err)
        # Clean up temp directory if it exists (best effort - ignore Local Fixture Store locks)
        if temp_dir.exists():
            try:
                shutil.rmtree(str(temp_dir))
                logger.info("Cleaned up temp directory")
            except (PermissionError, OSError) as cleanup_err:
                logger.warning("Could not clean up temp directory (Local Fixture Store lock?): %s", cleanup_err)
                logger.warning("Temp directory will be cleaned on next deployment: %s", temp_dir)
        if isinstance(exc, PermissionError):
            logger.error("No permission to write to %s", deploy_parent)
        else:
            logger.error("Dashboard was generated locally. Copy manually if needed.")
        raise  # Re-raise to fail the script


def deploy_dashboard(source_dir: Path = DASHBOARD_DIR) -> None:
    """Deploy a validated dashboard staging tree using per-file atomic sync."""
    deploy_parent = DEPLOY_DIR.parent
    try:
        parent_exists = deploy_parent.exists()
    except PermissionError:
        parent_exists = True
    if not parent_exists:
        logger.error("Deploy directory parent not accessible: %s", deploy_parent)
        logger.error("  set INVOICE_DASHBOARD_DEPLOY_DIR=<path>")
        sys.exit(1)

    _verify_deploy_tree(source_dir, "Staged dashboard", require_calendar=False)
    try:
        DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        pass
    _ensure_calendar_tree(DEPLOY_DIR / "Calendar")

    changed = 0
    unchanged = 0
    for filename in ("index.html", "data.js"):
        src = source_dir / filename
        if not src.exists():
            logger.warning("[WARN] %s not found, skipping.", src)
            continue
        if _copy_if_changed(src, DEPLOY_DIR / filename):
            changed += 1
            logger.info("[OK] %s -> %s", filename, DEPLOY_DIR)
        else:
            unchanged += 1
            logger.info("[OK] %s unchanged, skipped", filename)

    for folder in ("css", "dist"):
        folder_changed, folder_total = _sync_tree_if_changed(
            source_dir / folder,
            DEPLOY_DIR / folder,
        )
        logger.info("[OK] %s/: %d changed / %d checked", folder, folder_changed, folder_total)

    chunk_changed, chunk_pruned = _sync_generated_chunks(source_dir / "data_chunks", DEPLOY_DIR / "data_chunks")
    logger.info("[OK] data_chunks/: %d changed, %d stale week chunks pruned", chunk_changed, chunk_pruned)

    staged_db = source_dir / "data" / "invoices.db"
    if staged_db.exists():
        dst_db = DEPLOY_DIR / "data" / "invoices.db"
        if _copy_if_changed(staged_db, dst_db):
            changed += 1
            logger.info("[OK] invoices.db -> %s", dst_db.parent)
        else:
            unchanged += 1
            logger.info("[OK] invoices.db unchanged, skipped")

    _verify_deploy_tree(DEPLOY_DIR, "Final dashboard")
    _write_deploy_manifest(DEPLOY_DIR)
    logger.info("Final deployment verified")
    logger.info("Deploy complete: %s (%d changed, %d unchanged)", DEPLOY_DIR, changed, unchanged)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-html", action="store_true", help="regenerate index.html")
    deployment = parser.add_mutually_exclusive_group()
    deployment.add_argument(
        "--deploy",
        action="store_true",
        help="stage, validate, and promote to the configured deployment directory",
    )
    deployment.add_argument("--no-deploy", action="store_false", dest="deploy", help=argparse.SUPPRESS)
    parser.set_defaults(deploy=False)
    return parser


def main() -> int:
    """Main entry point for dashboard export."""
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("=" * 60)
    logger.info("  Export Dashboard")
    logger.info("=" * 60)

    logger.info("Step 1: Generating data.js...")
    export_data_js()

    logger.info("Step 2: Generating index.html...")
    export_html(force=args.force_html)

    if args.deploy:
        logger.info("Step 3: Staging and validating deployment...")
        with tempfile.TemporaryDirectory(prefix="invoice-dashboard-stage-") as temp_dir:
            staged_dashboard = Path(temp_dir) / "dashboard"
            shutil.copytree(DASHBOARD_DIR, staged_dashboard)
            _verify_deploy_tree(staged_dashboard, "Staged dashboard", require_calendar=False)
            logger.info("Step 4: Promoting validated dashboard...")
            deploy_dashboard(staged_dashboard)

    logger.info("=" * 60)
    logger.info("  DONE!")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
