"""
run_all.py - Runs the full pipeline: import Excel -> SQLite -> data.js + index.html -> deploy.

Usage:
    python -m scripts.run_all                     (import latest + export + deploy)
    python -m scripts.run_all --rebuild            (wipe DB, re-import all + export + deploy)
    python -m scripts.run_all --force-html         (regenerate index.html from Python)
    python -m scripts.run_all --date 13_02_2026   (import specific date + export + deploy)
    python -m scripts.run_all --calendar-only      (apply Calendar pending JSONs + export + deploy)
"""
from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent


def run_module(module: str, extra_args: list[str] | None = None) -> bool:
    """Run a Python module and return success status."""
    cmd = [sys.executable, "-m", module] + (extra_args or [])
    result = subprocess.run(cmd, cwd=str(ROOT_DIR))
    return result.returncode == 0


def build_archive_args(import_args: list[str]) -> list[str]:
    """Build post-export archive args from an optional --date DD_MM_YYYY import."""
    for index, arg in enumerate(import_args):
        raw_date: str | None = None
        if arg == "--date" and index + 1 < len(import_args):
            raw_date = import_args[index + 1]
        elif arg.startswith("--date="):
            raw_date = arg.split("=", 1)[1]

        if raw_date is not None:
            extraction_date = datetime.strptime(raw_date, "%d_%m_%Y").date().strftime("%Y-%m-%d")
            return ["--date", extraction_date, "--strict"]

    return ["--strict"]


def main() -> None:
    """Main entry point for the full pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("=" * 60)
    logger.info("  Invoice Process Dashboard - Full Pipeline")
    logger.info("=" * 60)

    calendar_only = "--calendar-only" in sys.argv
    no_deploy = "--no-deploy" in sys.argv

    if calendar_only:
        logger.info(">>> Calendar-only mode: clearing legacy weekly_overrides absences...")
        try:
            from scripts.etl.apply_calendar_absences import clear_non_calendar_absences
            deleted = clear_non_calendar_absences()
            logger.info("Legacy weekly_overrides absences removed: %d row(s).", deleted)
        except Exception:
            logger.error("Legacy absence cleanup failed.", exc_info=True)
            sys.exit(1)

        logger.info(">>> Calendar-only mode: applying Calendar pending files...")
        try:
            from scripts.etl.apply_calendar_absences import apply_calendar_absences
            calendar_result = apply_calendar_absences()
        except Exception:
            logger.error("Calendar-only apply failed.", exc_info=True)
            sys.exit(1)

        logger.info(
            "Calendar absences: %d file(s) processed, %d rejected, %d added, %d deleted.",
            calendar_result["files_processed"],
            calendar_result["files_rejected"],
            calendar_result["added"],
            calendar_result["deleted"],
        )
        if calendar_result["errors"]:
            logger.warning("Calendar apply completed with %d error(s).", len(calendar_result["errors"]))

        export_args = []
        if "--force-html" in sys.argv:
            export_args.append("--force-html")
        if no_deploy:
            export_args.append("--no-deploy")

        logger.info(">>> Calendar-only mode: running export%s...", " (no deploy)" if no_deploy else " + deploy")
        if not run_module("scripts.dashboard.export_dashboard", export_args):
            logger.error("Export failed.")
            sys.exit(1)

        logger.info("=" * 60)
        logger.info("  CALENDAR UPDATE DONE!")
        logger.info("=" * 60)
        return

    # Step 1: Import
    import_args = [
        arg for arg in sys.argv[1:]
        if arg not in {"--force-html", "--no-deploy"}
    ]
    logger.info(">>> Step 1: Running import (scripts.etl.process_invoices)...")
    if not run_module("scripts.etl.process_invoices", import_args):
        logger.error("Import failed. Stopping.")
        sys.exit(1)

    # Step 2: Apply team-member overrides from weekly_overrides.xlsx
    logger.info(">>> Step 2: Applying team-member overrides...")
    try:
        from scripts.etl.apply_overrides import apply_overrides
        override_result = apply_overrides()
        if override_result["rows_updated"]:
            logger.info(
                "Overrides applied: %d rule(s), %d row(s) updated.",
                override_result["applied"],
                override_result["rows_updated"],
            )
        elif override_result["applied"] == 0:
            logger.info("No overrides to apply.")
    except Exception:
        logger.warning("Override step failed, but continuing...", exc_info=True)

    # Step 3b: weekly_overrides.xlsx no longer feeds absences.
    # Holiday/Sickness/Other/Half Day entries are controlled by Calendar JSON files.
    logger.info(">>> Step 3b: Clearing legacy weekly_overrides absences.")
    try:
        from scripts.etl.apply_calendar_absences import clear_non_calendar_absences
        deleted = clear_non_calendar_absences()
        logger.info("Legacy weekly_overrides absences removed: %d row(s).", deleted)
    except Exception:
        logger.warning("Legacy absence cleanup failed, but continuing...", exc_info=True)

    # Step 3c: Apply Calendar tab absences from published dashboard JSON files (non-blocking)
    logger.info(">>> Step 3c: Applying Calendar tab absences...")
    try:
        from scripts.etl.apply_calendar_absences import apply_calendar_absences
        calendar_result = apply_calendar_absences()
        if calendar_result["files_processed"] or calendar_result["files_rejected"]:
            logger.info(
                "Calendar absences: %d file(s) processed, %d rejected, %d added, %d deleted.",
                calendar_result["files_processed"],
                calendar_result["files_rejected"],
                calendar_result["added"],
                calendar_result["deleted"],
            )
        else:
            logger.info("No Calendar pending files to apply.")
    except Exception:
        logger.warning("Calendar absence step failed, but continuing...", exc_info=True)

    # Step 3d: Apply production credit overrides from published dashboard JSON files (non-blocking)
    logger.info(">>> Step 3d: Applying production credit overrides...")
    try:
        from scripts.etl.apply_production_overrides import apply_production_overrides
        production_result = apply_production_overrides()
        if production_result["files_processed"] or production_result["files_rejected"]:
            logger.info(
                "Production overrides: %d file(s) processed, %d rejected, %d added, %d deleted.",
                production_result["files_processed"],
                production_result["files_rejected"],
                production_result["added"],
                production_result["deleted"],
            )
        else:
            logger.info("No ProductionOverrides pending files to apply.")
    except Exception:
        logger.warning("Production override step failed, but continuing...", exc_info=True)

    # Step 4: Export + Deploy (with data chunking)
    export_args = []
    if "--force-html" in sys.argv:
        export_args.append("--force-html")
    if no_deploy:
        export_args.append("--no-deploy")
    logger.info(">>> Step 4: Running export + deploy (scripts.dashboard.export_dashboard)...")
    if not run_module("scripts.dashboard.export_dashboard", export_args):
        logger.error("Export failed.")
        sys.exit(1)

    # Step 5: Archive processed files only after the full run has succeeded.
    logger.info(">>> Step 5: Running archive (scripts.utils.archive_manager)...")
    if not run_module("scripts.utils.archive_manager", build_archive_args(import_args)):
        logger.error("Archive failed.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("  ALL DONE! Open dashboard/index.html to view.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
