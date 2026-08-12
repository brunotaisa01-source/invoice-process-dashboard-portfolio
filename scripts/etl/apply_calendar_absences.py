"""
apply_calendar_absences.py - Apply Calendar tab absence JSON files.

The published dashboard writes one JSON file per Save click into:
    <deploy>/Calendar/pending/

This module validates those files, applies additions/deletions to SQLite,
then archives valid files to processed/ and invalid files to rejected/.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from scripts.etl.apply_absences import (
    _VALID_TYPES,
    _parse_date,
    _read_absences_file,
    _validate_row,
    ensure_schema,
)

logger = logging.getLogger(__name__)

AbsenceType = Literal["Holiday", "Sickness", "Other", "Half Day"]


@dataclass(frozen=True)
class CalendarAbsence:
    member: str
    date: str
    type: AbsenceType
    created_by: str


@dataclass(frozen=True)
class CalendarDeletion:
    member: str
    date: str
    created_by: str


def _friday_week_start(value: str) -> str:
    """Return the Friday-start week for an ISO date."""
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    days_since_friday = (parsed.weekday() - 4) % 7
    return (parsed - timedelta(days=days_since_friday)).strftime("%Y-%m-%d")


def _require_iso_date(value: Any, field: str) -> str:
    parsed = _parse_date(value)
    try:
        datetime.strptime(parsed, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid date, got {value!r}") from exc
    return parsed


def _require_member(value: Any, team_members: list[str]) -> str:
    member = str(value or "").strip()
    if not member:
        raise ValueError("member is required")
    if member not in team_members:
        raise ValueError(f"member {member!r} is not in TEAM_MEMBERS")
    return member


def _require_type(value: Any) -> AbsenceType:
    absence_type = str(value or "").strip()
    if absence_type not in _VALID_TYPES:
        raise ValueError(f"type {absence_type!r} must be one of {sorted(_VALID_TYPES)}")
    return absence_type  # type: ignore[return-value]


def _unique_destination(directory: Path, filename: str) -> Path:
    """Return a destination path that will not overwrite an existing file."""
    target = directory / filename
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    for idx in range(1, 10_000):
        candidate = directory / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not create unique archive filename for {filename}")


def _archive_file(path: Path, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination(directory, path.name)
    shutil.move(str(path), str(destination))
    return destination


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _load_calendar_file(path: Path, team_members: list[str]) -> tuple[list[CalendarAbsence], list[CalendarDeletion]]:
    """Read and validate one Calendar JSON file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    if payload.get("app") not in {None, "invoice-process-dashboard"}:
        raise ValueError(f"unexpected app value: {payload.get('app')!r}")

    created_by = str(payload.get("created_by") or "").strip() or "unknown"
    raw_added = payload.get("added", [])
    raw_deleted = payload.get("deleted", [])
    if not isinstance(raw_added, list):
        raise ValueError("added must be a list")
    if not isinstance(raw_deleted, list):
        raise ValueError("deleted must be a list")

    added: list[CalendarAbsence] = []
    for idx, item in enumerate(raw_added, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"added[{idx}] must be an object")
        added.append(
            CalendarAbsence(
                member=_require_member(item.get("member"), team_members),
                date=_require_iso_date(item.get("date"), f"added[{idx}].date"),
                type=_require_type(item.get("type")),
                created_by=created_by,
            )
        )

    deleted: list[CalendarDeletion] = []
    for idx, item in enumerate(raw_deleted, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"deleted[{idx}] must be an object")
        deleted.append(
            CalendarDeletion(
                member=_require_member(item.get("member"), team_members),
                date=_require_iso_date(item.get("date"), f"deleted[{idx}].date"),
                created_by=created_by,
            )
        )

    if not added and not deleted:
        raise ValueError("calendar file has no added or deleted entries")
    return added, deleted


def _replay_deletions(conn: sqlite3.Connection) -> int:
    """Apply persistent Calendar deletion tombstones after weekly_overrides runs."""
    rows = conn.execute("SELECT member, date FROM team_absence_deletions").fetchall()
    for row in rows:
        conn.execute(
            "DELETE FROM team_absences WHERE member = ? AND date = ?",
            (row["member"], row["date"]),
        )
    return len(rows)


def _apply_deletion(conn: sqlite3.Connection, deletion: CalendarDeletion, deleted_at: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO team_absence_deletions
            (member, date, source, deleted_at, created_by)
        VALUES (?, ?, 'calendar', ?, ?)
        """,
        (deletion.member, deletion.date, deleted_at, deletion.created_by),
    )
    conn.execute(
        "DELETE FROM team_absences WHERE member = ? AND date = ?",
        (deletion.member, deletion.date),
    )


def _apply_addition(conn: sqlite3.Connection, absence: CalendarAbsence) -> None:
    week_start = _friday_week_start(absence.date)
    conn.execute(
        "DELETE FROM team_absence_deletions WHERE member = ? AND date = ?",
        (absence.member, absence.date),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO team_absences (week_start, member, date, type, source)
        VALUES (?, ?, ?, ?, 'calendar')
        """,
        (week_start, absence.member, absence.date, absence.type),
    )


def _calendar_file_needs_apply(
    conn: sqlite3.Connection,
    additions: list[CalendarAbsence],
    deletions: list[CalendarDeletion],
) -> bool:
    """Return True when a processed Calendar JSON has not reached the DB yet."""
    for deletion in deletions:
        tombstone = conn.execute(
            "SELECT 1 FROM team_absence_deletions WHERE member = ? AND date = ?",
            (deletion.member, deletion.date),
        ).fetchone()
        active_absence = conn.execute(
            "SELECT 1 FROM team_absences WHERE member = ? AND date = ?",
            (deletion.member, deletion.date),
        ).fetchone()
        if tombstone is None or active_absence is not None:
            return True

    for absence in additions:
        applied = conn.execute(
            """
            SELECT 1
            FROM team_absences
            WHERE member = ? AND date = ? AND type = ? AND source = 'calendar'
            """,
            (absence.member, absence.date, absence.type),
        ).fetchone()
        if applied is None:
            return True

    return False


def clear_non_calendar_absences(
    db_path: Path | None = None,
    _conn: sqlite3.Connection | None = None,
) -> int:
    """Remove legacy weekly_overrides absence rows now that Calendar JSON is source of truth."""
    from scripts.paths import DB_PATH  # noqa: PLC0415

    db_path = db_path or DB_PATH
    own_conn = _conn is None
    conn: sqlite3.Connection = _conn or sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        cursor = conn.execute(
            "DELETE FROM team_absences WHERE COALESCE(source, 'weekly_overrides') <> 'calendar'"
        )
        deleted = cursor.rowcount if cursor.rowcount is not None else 0
        if own_conn:
            conn.commit()
        return deleted
    finally:
        if own_conn:
            conn.close()


def apply_calendar_absences(
    db_path: Path | None = None,
    pending_dir: Path | None = None,
    processed_dir: Path | None = None,
    rejected_dir: Path | None = None,
    dry_run: bool = False,
    _conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Apply Calendar JSON files from pending_dir to team_absences."""
    from scripts.config import ALL_MEMBERS  # noqa: PLC0415  (incl. former members for historical rows)
    from scripts.paths import (  # noqa: PLC0415
        CALENDAR_PENDING_DIR,
        CALENDAR_PROCESSED_DIR,
        CALENDAR_REJECTED_DIR,
        DB_PATH,
    )

    db_path = db_path or DB_PATH
    pending_dir = pending_dir or CALENDAR_PENDING_DIR
    processed_dir = processed_dir or CALENDAR_PROCESSED_DIR
    rejected_dir = rejected_dir or CALENDAR_REJECTED_DIR

    result: dict[str, Any] = {
        "files_processed": 0,
        "files_rejected": 0,
        "added": 0,
        "deleted": 0,
        "tombstones_replayed": 0,
        "files_recovered": 0,
        "files_already_applied": 0,
        "errors": [],
    }

    if _conn is None:
        try:
            for directory in (pending_dir, processed_dir, rejected_dir):
                try:
                    if directory.is_dir():
                        continue
                except OSError:
                    continue
                directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            msg = f"Calendar directory unavailable: {exc}"
            logger.warning(msg)
            result["errors"].append(msg)
            return result

    try:
        pending_files = sorted(pending_dir.glob("invoice_calendar_*.json"))
        processed_files = sorted(processed_dir.glob("invoice_calendar_*.json"))
    except OSError as exc:
        msg = f"Calendar directory unavailable: {exc}"
        logger.warning(msg)
        result["errors"].append(msg)
        return result

    own_conn = _conn is None
    conn: sqlite3.Connection = _conn or sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_schema(conn)
        if dry_run:
            result["tombstones_replayed"] = conn.execute(
                "SELECT COUNT(*) FROM team_absence_deletions"
            ).fetchone()[0]
        else:
            result["tombstones_replayed"] = _replay_deletions(conn)

        for path in pending_files:
            try:
                additions, deletions = _load_calendar_file(path, ALL_MEMBERS)
                if not dry_run:
                    deleted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                    for deletion in deletions:
                        _apply_deletion(conn, deletion, deleted_at)
                    for absence in additions:
                        _apply_addition(conn, absence)
                    _archive_file(path, processed_dir)
                result["files_processed"] += 1
                result["added"] += len(additions)
                result["deleted"] += len(deletions)
            except Exception as exc:  # noqa: BLE001
                msg = f"{path.name}: {exc}"
                logger.warning("Calendar file rejected: %s", msg)
                result["files_rejected"] += 1
                result["errors"].append(msg)
                if not dry_run:
                    _archive_file(path, rejected_dir)

        for path in processed_files:
            try:
                additions, deletions = _load_calendar_file(path, ALL_MEMBERS)
                if not _calendar_file_needs_apply(conn, additions, deletions):
                    result["files_already_applied"] += 1
                    continue
                if not dry_run:
                    deleted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                    for deletion in deletions:
                        _apply_deletion(conn, deletion, deleted_at)
                    for absence in additions:
                        _apply_addition(conn, absence)
                result["files_recovered"] += 1
                result["files_processed"] += 1
                result["added"] += len(additions)
                result["deleted"] += len(deletions)
            except Exception as exc:  # noqa: BLE001
                msg = f"{path.name}: {exc}"
                logger.warning("Processed Calendar file could not be replayed: %s", msg)
                result["errors"].append(msg)

        if not dry_run:
            conn.commit()
    finally:
        if own_conn:
            conn.close()

    return result


def export_weekly_overrides_seed(
    output_dir: Path | None = None,
    overrides_path: Path | None = None,
    created_by: str | None = None,
) -> Path:
    """Create a Calendar seed JSON from weekly_overrides.xlsx Absences."""
    from scripts.config import ALL_MEMBERS  # noqa: PLC0415  (incl. former members for historical rows)
    from scripts.paths import CALENDAR_PENDING_DIR, DATA_DIR  # noqa: PLC0415

    output_dir = output_dir or CALENDAR_PENDING_DIR
    overrides_path = overrides_path or DATA_DIR / "weekly_overrides.xlsx"
    created_by = created_by or os.environ.get("USERNAME") or "codex"

    raw_rows = _read_absences_file(overrides_path)
    added: list[dict[str, str]] = []
    for idx, raw in enumerate(raw_rows, start=2):
        cleaned = _validate_row(raw, ALL_MEMBERS, idx)
        if cleaned is None:
            continue
        added.append({
            "member": cleaned["member"],
            "date": cleaned["date"],
            "type": cleaned["type"],
        })

    payload = {
        "version": 1,
        "app": "invoice-process-dashboard",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "created_by": created_by,
        "added": added,
        "deleted": [],
    }
    filename = f"invoice_calendar_seed_from_weekly_overrides_{date.today().isoformat()}.json"
    target = _unique_destination(output_dir, filename)
    _atomic_write_text(target, json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
    return target


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply Invoice Dashboard Calendar absence JSON files.")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--db", metavar="PATH", default=None)
    parser.add_argument("--pending-dir", metavar="PATH", default=None)
    parser.add_argument("--processed-dir", metavar="PATH", default=None)
    parser.add_argument("--rejected-dir", metavar="PATH", default=None)
    parser.add_argument("--seed-from-weekly-overrides", action="store_true", default=False)
    parser.add_argument("--overrides", metavar="PATH", default=None)
    return parser


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    )
    args = _build_arg_parser().parse_args()
    if args.seed_from_weekly_overrides:
        seed_path = export_weekly_overrides_seed(
            output_dir=Path(args.pending_dir) if args.pending_dir else None,
            overrides_path=Path(args.overrides) if args.overrides else None,
        )
        print(f"[OK] Calendar seed created: {seed_path}")
    else:
        summary = apply_calendar_absences(
            db_path=Path(args.db) if args.db else None,
            pending_dir=Path(args.pending_dir) if args.pending_dir else None,
            processed_dir=Path(args.processed_dir) if args.processed_dir else None,
            rejected_dir=Path(args.rejected_dir) if args.rejected_dir else None,
            dry_run=args.dry_run,
        )
        print(
            "[OK] Calendar applied: "
            f"files_processed={summary['files_processed']} "
            f"files_rejected={summary['files_rejected']} "
            f"added={summary['added']} deleted={summary['deleted']} "
            f"errors={len(summary['errors'])}"
        )
