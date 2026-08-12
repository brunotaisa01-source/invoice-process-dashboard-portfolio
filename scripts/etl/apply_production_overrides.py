"""Apply dashboard production credit override JSON files.

The published dashboard writes one JSON file per Save/Delete click into:
    <deploy>/ProductionOverrides/pending/

Overrides adjust aggregate productivity credit only. They do not mutate real
invoice rows, so the Detail table remains the ERP source of truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

WorkType = Literal["manual", "csv", "envoy"]

_VALID_WORK_TYPES: set[str] = {"manual", "csv", "envoy"}
_OPTIONAL_TEXT_FIELDS = ("country", "company_code", "document_type", "reference", "reason")


@dataclass(frozen=True)
class ProductionOverride:
    override_id: str
    week_start: str
    date: str
    from_member: str
    to_member: str
    count: int
    work_type: WorkType
    country: str
    company_code: str
    document_type: str
    reference: str
    reason: str
    created_at: str
    created_by: str


@dataclass(frozen=True)
class ProductionOverrideDeletion:
    override_id: str
    created_by: str


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create production override tables if they are missing."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS production_overrides (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            override_id     TEXT NOT NULL UNIQUE,
            week_start      TEXT NOT NULL,
            date            TEXT NOT NULL,
            from_member     TEXT NOT NULL,
            to_member       TEXT NOT NULL,
            count           INTEGER NOT NULL CHECK(count > 0),
            work_type       TEXT NOT NULL CHECK(work_type IN ('manual', 'csv', 'envoy')),
            country         TEXT NOT NULL DEFAULT '',
            company_code    TEXT NOT NULL DEFAULT '',
            document_type   TEXT NOT NULL DEFAULT '',
            reference       TEXT NOT NULL DEFAULT '',
            reason          TEXT NOT NULL DEFAULT '',
            source          TEXT NOT NULL DEFAULT 'dashboard',
            created_at      TEXT NOT NULL,
            created_by      TEXT,
            applied_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS production_override_deletions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            override_id TEXT NOT NULL UNIQUE,
            source      TEXT NOT NULL DEFAULT 'dashboard',
            deleted_at  TEXT NOT NULL,
            created_by  TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_production_overrides_week_type "
        "ON production_overrides(week_start, work_type)"
    )
    conn.commit()


def _friday_week_start(value: str) -> str:
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    days_since_friday = (parsed.weekday() - 4) % 7
    return (parsed - timedelta(days=days_since_friday)).strftime("%Y-%m-%d")


def _require_iso_date(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD, got {value!r}") from exc
    return text


def _require_member(value: Any, all_members: list[str], field: str) -> str:
    member = str(value or "").strip()
    if not member:
        raise ValueError(f"{field} is required")
    if member not in all_members:
        raise ValueError(f"{field} {member!r} is not in ALL_MEMBERS")
    return member


def _require_work_type(value: Any) -> WorkType:
    work_type = str(value or "").strip().lower()
    if work_type not in _VALID_WORK_TYPES:
        raise ValueError(f"work_type {work_type!r} must be one of {sorted(_VALID_WORK_TYPES)}")
    return work_type  # type: ignore[return-value]


def _require_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"count must be a positive integer, got {value!r}") from exc
    if count <= 0:
        raise ValueError(f"count must be a positive integer, got {value!r}")
    return count


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalise_country(company_code: str, country: str, company_map: dict[str, str]) -> str:
    if company_code:
        if company_code not in company_map:
            raise ValueError(f"company_code {company_code!r} is not in COMPANY_CODE_COUNTRY_MAP")
        expected_country = company_map[company_code]
        if country and country != expected_country:
            raise ValueError(
                f"country {country!r} does not match company_code {company_code!r} ({expected_country!r})"
            )
        return expected_country
    return country


def _stable_override_id(item: dict[str, Any], normalized: dict[str, Any]) -> str:
    supplied = _clean_text(item.get("override_id"))
    if supplied:
        return supplied
    identity = {
        key: normalized[key]
        for key in (
            "date",
            "from_member",
            "to_member",
            "count",
            "work_type",
            "country",
            "company_code",
            "document_type",
            "reference",
        )
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return "prod_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _load_production_file(
    path: Path,
    all_members: list[str],
    company_map: dict[str, str],
) -> tuple[list[ProductionOverride], list[ProductionOverrideDeletion]]:
    """Read and validate one production override JSON file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    if payload.get("app") not in {None, "invoice-process-dashboard"}:
        raise ValueError(f"unexpected app value: {payload.get('app')!r}")
    if payload.get("feature") not in {None, "production-credit-overrides"}:
        raise ValueError(f"unexpected feature value: {payload.get('feature')!r}")

    created_at = _clean_text(payload.get("created_at")) or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    created_by = _clean_text(payload.get("created_by")) or "unknown"
    raw_added = payload.get("added", [])
    raw_deleted = payload.get("deleted", [])
    if not isinstance(raw_added, list):
        raise ValueError("added must be a list")
    if not isinstance(raw_deleted, list):
        raise ValueError("deleted must be a list")

    added: list[ProductionOverride] = []
    for idx, item in enumerate(raw_added, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"added[{idx}] must be an object")
        date = _require_iso_date(item.get("date"), f"added[{idx}].date")
        week_start = _clean_text(item.get("week_start")) or _friday_week_start(date)
        week_start = _require_iso_date(week_start, f"added[{idx}].week_start")
        from_member = _require_member(item.get("from_member"), all_members, f"added[{idx}].from_member")
        to_member = _require_member(item.get("to_member"), all_members, f"added[{idx}].to_member")
        if from_member == to_member:
            raise ValueError(f"added[{idx}] from_member and to_member must be different")

        normalized = {
            "week_start": week_start,
            "date": date,
            "from_member": from_member,
            "to_member": to_member,
            "count": _require_count(item.get("count")),
            "work_type": _require_work_type(item.get("work_type")),
            "country": _clean_text(item.get("country")),
            "company_code": _clean_text(item.get("company_code")).upper(),
            "document_type": _clean_text(item.get("document_type")).upper(),
            "reference": _clean_text(item.get("reference")),
            "reason": _clean_text(item.get("reason")),
        }
        normalized["country"] = _normalise_country(
            normalized["company_code"],
            normalized["country"],
            company_map,
        )
        override_id = _stable_override_id(item, normalized)
        added.append(
            ProductionOverride(
                override_id=override_id,
                created_at=created_at,
                created_by=created_by,
                **normalized,
            )
        )

    deleted: list[ProductionOverrideDeletion] = []
    for idx, item in enumerate(raw_deleted, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"deleted[{idx}] must be an object")
        override_id = _clean_text(item.get("override_id"))
        if not override_id:
            raise ValueError(f"deleted[{idx}].override_id is required")
        deleted.append(ProductionOverrideDeletion(override_id=override_id, created_by=created_by))

    if not added and not deleted:
        raise ValueError("production override file has no added or deleted entries")
    return added, deleted


def _unique_destination(directory: Path, filename: str) -> Path:
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


def _replay_deletions(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT override_id FROM production_override_deletions").fetchall()
    for row in rows:
        conn.execute("DELETE FROM production_overrides WHERE override_id = ?", (row["override_id"],))
    return len(rows)


def _apply_deletion(conn: sqlite3.Connection, deletion: ProductionOverrideDeletion, deleted_at: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO production_override_deletions
            (override_id, source, deleted_at, created_by)
        VALUES (?, 'dashboard', ?, ?)
        """,
        (deletion.override_id, deleted_at, deletion.created_by),
    )
    conn.execute("DELETE FROM production_overrides WHERE override_id = ?", (deletion.override_id,))


def _apply_addition(conn: sqlite3.Connection, override: ProductionOverride) -> None:
    conn.execute(
        "DELETE FROM production_override_deletions WHERE override_id = ?",
        (override.override_id,),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO production_overrides (
            override_id, week_start, date, from_member, to_member, count,
            work_type, country, company_code, document_type, reference, reason,
            source, created_at, created_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'dashboard', ?, ?)
        """,
        (
            override.override_id,
            override.week_start,
            override.date,
            override.from_member,
            override.to_member,
            override.count,
            override.work_type,
            override.country,
            override.company_code,
            override.document_type,
            override.reference,
            override.reason,
            override.created_at,
            override.created_by,
        ),
    )


def _production_file_needs_apply(
    conn: sqlite3.Connection,
    additions: list[ProductionOverride],
    deletions: list[ProductionOverrideDeletion],
) -> bool:
    for deletion in deletions:
        tombstone = conn.execute(
            "SELECT 1 FROM production_override_deletions WHERE override_id = ?",
            (deletion.override_id,),
        ).fetchone()
        active = conn.execute(
            "SELECT 1 FROM production_overrides WHERE override_id = ?",
            (deletion.override_id,),
        ).fetchone()
        if tombstone is None or active is not None:
            return True

    for override in additions:
        applied = conn.execute(
            "SELECT 1 FROM production_overrides WHERE override_id = ?",
            (override.override_id,),
        ).fetchone()
        if applied is None:
            return True

    return False


def apply_production_overrides(
    db_path: Path | None = None,
    pending_dir: Path | None = None,
    processed_dir: Path | None = None,
    rejected_dir: Path | None = None,
    dry_run: bool = False,
    _conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Apply production override JSON files to production_overrides."""
    from scripts.config import ALL_MEMBERS, COMPANY_CODE_COUNTRY_MAP  # noqa: PLC0415
    from scripts.paths import (  # noqa: PLC0415
        DB_PATH,
        PRODUCTION_OVERRIDES_PENDING_DIR,
        PRODUCTION_OVERRIDES_PROCESSED_DIR,
        PRODUCTION_OVERRIDES_REJECTED_DIR,
    )

    db_path = db_path or DB_PATH
    pending_dir = pending_dir or PRODUCTION_OVERRIDES_PENDING_DIR
    processed_dir = processed_dir or PRODUCTION_OVERRIDES_PROCESSED_DIR
    rejected_dir = rejected_dir or PRODUCTION_OVERRIDES_REJECTED_DIR

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
            msg = f"Production override directory unavailable: {exc}"
            logger.warning(msg)
            result["errors"].append(msg)
            return result

    try:
        pending_files = sorted(pending_dir.glob("invoice_production_overrides_*.json"))
        processed_files = sorted(processed_dir.glob("invoice_production_overrides_*.json"))
    except OSError as exc:
        msg = f"Production override directory unavailable: {exc}"
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
                "SELECT COUNT(*) FROM production_override_deletions"
            ).fetchone()[0]
        else:
            result["tombstones_replayed"] = _replay_deletions(conn)

        for path in pending_files:
            try:
                additions, deletions = _load_production_file(path, ALL_MEMBERS, COMPANY_CODE_COUNTRY_MAP)
                if not dry_run:
                    deleted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                    for deletion in deletions:
                        _apply_deletion(conn, deletion, deleted_at)
                    for override in additions:
                        _apply_addition(conn, override)
                    _archive_file(path, processed_dir)
                result["files_processed"] += 1
                result["added"] += len(additions)
                result["deleted"] += len(deletions)
            except Exception as exc:  # noqa: BLE001
                msg = f"{path.name}: {exc}"
                logger.warning("Production override file rejected: %s", msg)
                result["files_rejected"] += 1
                result["errors"].append(msg)
                if not dry_run:
                    _archive_file(path, rejected_dir)

        for path in processed_files:
            try:
                additions, deletions = _load_production_file(path, ALL_MEMBERS, COMPANY_CODE_COUNTRY_MAP)
                if not _production_file_needs_apply(conn, additions, deletions):
                    result["files_already_applied"] += 1
                    continue
                if not dry_run:
                    deleted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                    for deletion in deletions:
                        _apply_deletion(conn, deletion, deleted_at)
                    for override in additions:
                        _apply_addition(conn, override)
                result["files_recovered"] += 1
                result["files_processed"] += 1
                result["added"] += len(additions)
                result["deleted"] += len(deletions)
            except Exception as exc:  # noqa: BLE001
                msg = f"{path.name}: {exc}"
                logger.warning("Processed production override file could not be replayed: %s", msg)
                result["errors"].append(msg)

        if not dry_run:
            conn.commit()
        return result
    finally:
        if own_conn:
            conn.close()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply dashboard production credit override JSON files.")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--db", metavar="PATH", default=None)
    parser.add_argument("--pending-dir", metavar="PATH", default=None)
    parser.add_argument("--processed-dir", metavar="PATH", default=None)
    parser.add_argument("--rejected-dir", metavar="PATH", default=None)
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    summary = apply_production_overrides(
        db_path=Path(args.db) if args.db else None,
        pending_dir=Path(args.pending_dir) if args.pending_dir else None,
        processed_dir=Path(args.processed_dir) if args.processed_dir else None,
        rejected_dir=Path(args.rejected_dir) if args.rejected_dir else None,
        dry_run=args.dry_run,
    )
    print(
        "[OK] Production overrides applied: "
        f"files_processed={summary['files_processed']} "
        f"files_rejected={summary['files_rejected']} "
        f"added={summary['added']} deleted={summary['deleted']} "
        f"errors={len(summary['errors'])}"
    )


if __name__ == "__main__":
    main()
