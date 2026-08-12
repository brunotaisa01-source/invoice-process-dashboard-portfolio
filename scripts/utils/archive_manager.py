"""
archive_manager.py - Moves processed Excel files to data/archive/YYYY/MM/.

Detects files in data/incoming/ that have already been imported (checked via
the weekly_imports table in SQLite), and moves them to the archive directory
organized by year and month extracted from the filename date.

Usage:
    python -m scripts.utils.archive_manager           # Archive processed files
    python -m scripts.utils.archive_manager --dry-run  # Preview without moving
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from scripts.paths import DB_PATH, ARCHIVE_DIR, get_incoming_dir
from scripts.loaders.excel_loader import parse_filename

logger = logging.getLogger(__name__)


def normalize_extraction_date(value: str | None) -> str | None:
    """Validate and normalize an optional YYYY-MM-DD extraction date."""
    if value is None:
        return None

    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as err:
        raise ValueError(f"extraction date must use YYYY-MM-DD: {value}") from err
    return parsed.strftime("%Y-%m-%d")


def get_imported_dates(db_path: Path) -> set[str]:
    """
    Query the weekly_imports table for all imported extraction dates.

    Returns set of date strings in YYYY-MM-DD format.
    """
    if not db_path.exists():
        return set()

    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.execute("SELECT DISTINCT extraction_date FROM weekly_imports")
        return {row[0] for row in cursor.fetchall()}


def compute_archive_path(filename: str, archive_root: Path) -> Path | None:
    """
    Compute the archive destination path for a file.

    Given 'SYS-A_13_02_2026.xlsx', returns archive_root/2026/02/SYS-A_13_02_2026.xlsx.
    Returns None if the filename doesn't match the expected pattern.
    """
    parsed = parse_filename(filename)
    if not parsed:
        return None

    file_date = parsed["date"]
    year = str(file_date.year)
    month = f"{file_date.month:02d}"
    return archive_root / year / month / filename


def archive_processed_files(
    dry_run: bool = False,
    extraction_date: str | None = None,
    strict: bool = False,
) -> list[tuple[Path, Path]]:
    """
    Move processed Excel files from incoming/ to archive/YYYY/MM/.

    A file is considered "processed" if its extraction date exists
    in the weekly_imports table.

    Args:
        dry_run: If True, only log what would be moved without moving.
        extraction_date: Optional YYYY-MM-DD date. When provided, archive only
            incoming files whose filename date matches this extraction date.
        strict: If True, raise when the requested date is not imported or a
            matching file cannot be moved.

    Returns:
        List of (source, destination) tuples for files moved (or would be moved).
    """
    incoming_dir = get_incoming_dir()

    # If incoming directory doesn't exist, nothing to archive
    if not incoming_dir.exists():
        logger.info("Incoming directory does not exist. Nothing to archive.")
        return []

    requested_date = normalize_extraction_date(extraction_date)
    imported_dates = get_imported_dates(DB_PATH)

    if not imported_dates:
        logger.info("No imported dates found in database. Nothing to archive.")
        return []

    if requested_date is not None and requested_date not in imported_dates:
        message = f"Requested extraction date is not imported: {requested_date}"
        if strict:
            raise RuntimeError(message)
        logger.info("%s. Nothing to archive.", message)
        return []

    moved: list[tuple[Path, Path]] = []
    failures: list[str] = []

    for fpath in sorted(incoming_dir.iterdir()):
        if fpath.suffix.lower() != ".xlsx":
            continue

        parsed = parse_filename(fpath.name)
        if not parsed:
            continue

        # Check if this file's extraction date was imported
        date_str = parsed["date"].strftime("%Y-%m-%d")
        if requested_date is not None and date_str != requested_date:
            logger.debug("Skipping %s (outside requested extraction date)", fpath.name)
            continue

        if date_str not in imported_dates:
            logger.debug("Skipping %s (not yet imported)", fpath.name)
            continue

        dest = compute_archive_path(fpath.name, ARCHIVE_DIR)
        if dest is None:
            continue

        if dry_run:
            logger.info("[DRY-RUN] Would move: %s -> %s", fpath.name, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                if dest.exists():
                    fpath.replace(dest)
                    logger.info("Replaced archived copy: %s -> %s", fpath.name, dest)
                else:
                    shutil.move(str(fpath), str(dest))
                    logger.info("Moved: %s -> %s", fpath.name, dest)
            except OSError as exc:
                logger.error("Failed to move %s: %s", fpath.name, exc)
                failures.append(f"{fpath} -> {dest}: {exc}")
                continue

        moved.append((fpath, dest))

    if failures and strict:
        raise RuntimeError("Archive failed for one or more files: " + "; ".join(failures))

    if not moved:
        logger.info("No files to archive (all files are current or unprocessed).")
    else:
        action = "Would archive" if dry_run else "Archived"
        logger.info("%s %d file(s).", action, len(moved))

    return moved


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse archive manager CLI arguments."""
    parser = argparse.ArgumentParser(description="Archive processed ERP extraction files.")
    parser.add_argument("--dry-run", action="store_true", help="Preview moves without changing files.")
    parser.add_argument("--date", dest="extraction_date", help="Archive only this YYYY-MM-DD extraction date.")
    parser.add_argument("--strict", action="store_true", help="Return a non-zero exit code on archive failures.")
    return parser.parse_args(argv)


def main() -> None:
    """Main entry point for the archive manager."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    args = parse_args(sys.argv[1:])

    logger.info("=" * 60)
    logger.info("  Archive Manager%s", " (DRY RUN)" if args.dry_run else "")
    logger.info("=" * 60)

    try:
        archive_processed_files(
            dry_run=args.dry_run,
            extraction_date=args.extraction_date,
            strict=args.strict,
        )
    except Exception:
        logger.error("Archive failed.", exc_info=True)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("  Done!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
