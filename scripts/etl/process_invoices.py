"""
process_invoices.py - Import pipeline: reads Excel files, normalizes,
filters team members only, and stores in SQLite.

Usage:
    python -m scripts.etl.process_invoices                     (import latest)
    python -m scripts.etl.process_invoices --date 13_02_2026   (specific date)
    python -m scripts.etl.process_invoices --rebuild            (wipe DB, re-import all)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.config import (
    ERP_SYSTEMS, USER_MAP, ALL_MEMBERS, DOC_TYPE_LABELS,
    COMPANY_CODE_COUNTRY_MAP, CSV_SESSION_NAMES, CSV_VENDOR_PATTERNS,
    CSV_SUPPLIERS, CSV_SUPPLIER_REFERENCE_PREFIXES, NORMAL_NEGATIVE_TYPES,
)
from scripts.paths import DB_DIR, DB_PATH, get_incoming_dir, ARCHIVE_DIR
from scripts.loaders.sql_loader import execute_sql_file
from scripts.loaders.excel_loader import (
    find_files_for_date, find_all_extraction_dates, read_and_normalize,
    find_excel_files,
)

logger = logging.getLogger(__name__)


def init_db() -> sqlite3.Connection:
    """Create SQLite database and tables using SQL files.

    Returns a connection with schema initialized. Caller is responsible
    for closing the connection (preferably via context manager).
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))

    try:
        execute_sql_file(conn, "01_schema.sql")
        execute_sql_file(conn, "02_indexes.sql")
        execute_sql_file(conn, "03_views.sql")
        # Migrate existing DBs: add original_team_member if missing
        from scripts.etl.apply_overrides import migrate_schema
        migrate_schema(conn)
    except Exception:
        conn.close()
        raise

    return conn


def filter_team_members(df: pd.DataFrame, system_name: str) -> pd.DataFrame:
    """Keep only rows where user_id belongs to a team member."""
    user_map = USER_MAP.get(system_name, {})
    if not user_map:
        return df.iloc[0:0]

    mask = df["user_id"].isin(user_map.keys())
    filtered = df[mask].copy()
    filtered["team_member"] = filtered["user_id"].map(user_map)

    # Log unknown user IDs with significant activity
    unknown = df[~mask]
    if len(unknown) > 0:
        unknown_counts = unknown["user_id"].value_counts()
        significant = unknown_counts[unknown_counts >= 10]
        if len(significant) > 0:
            logger.info("Non-team user IDs with 10+ entries in %s:", system_name)
            for uid, count in significant.items():
                if uid and uid != "":
                    logger.info("  %s: %d entries", uid, count)

    return filtered


def detect_week_range(extraction_date: datetime) -> tuple:
    """
    Calculate Friday-to-Thursday week range from the extraction date.

    The extraction happens on Friday, covering the PREVIOUS Friday to Thursday.
    """
    week_start = extraction_date - timedelta(days=7)
    week_end = extraction_date - timedelta(days=1)
    return week_start, week_end


def detect_import_window(extraction_date: datetime, entry_dates: pd.Series) -> tuple:
    """
    Detect the data period represented by an ERP extraction.

    Weekly files contain the previous extraction window in the actual row dates.
    Daily files can be extracted on any weekday, including Friday, and can
    contain yesterday's data; use their actual row date range unless it covers
    the expected weekly window.
    """
    weekly_start, weekly_end = detect_week_range(extraction_date)
    if isinstance(weekly_start, datetime):
        weekly_start = weekly_start.date()
    if isinstance(weekly_end, datetime):
        weekly_end = weekly_end.date()
    parsed = pd.to_datetime(entry_dates, errors="coerce").dropna()
    if parsed.empty:
        return weekly_start, weekly_end

    dates = parsed.dt.date
    actual_start = dates.min()
    actual_end = dates.max()
    if actual_start <= weekly_start and actual_end >= weekly_end:
        return weekly_start, weekly_end
    return actual_start, actual_end


def check_duplicate_import(conn: sqlite3.Connection, extraction_date_str: str) -> tuple | None:
    """Check if this extraction date was already imported."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, total_rows FROM weekly_imports WHERE extraction_date = ?",
        (extraction_date_str,),
    )
    return cursor.fetchone()


def classify_invoices(all_data: pd.DataFrame) -> pd.DataFrame:
    """
    Classify invoices into manual (0), CSV upload (1), or Envoy (2).

    Three-layer classification:
    1. Vendor name patterns -> CSV
    2. Supplier numbers per company code -> CSV
    3. Document type 1H not caught above -> Envoy

    Envoy (1H) rows keep team_member from the uploader's username (USER_MAP),
    exactly like manual posts -- there is NO country-based reassignment.
    """
    # Clean company_code for matching
    cc_clean = (
        all_data["company_code"].astype(str).str.strip()
        .str.replace(r'\.0$', '', regex=True)
    )

    # Map company_code -> country
    all_data["country"] = cc_clean.map(COMPANY_CODE_COUNTRY_MAP).fillna("Other")

    # Step 1: Default classification by vendor name patterns
    session_csv = all_data["session_name"].astype(str).str.strip().isin(CSV_SESSION_NAMES)
    vendor_lower = all_data["vendor_name"].astype(str).str.lower()
    vendor_csv = pd.Series(False, index=all_data.index)
    for pattern in CSV_VENDOR_PATTERNS:
        vendor_csv = vendor_csv | vendor_lower.str.contains(pattern.lower(), na=False)
    all_data["is_csv"] = (session_csv | vendor_csv).astype(int)

    # Step 2: Check CSV supplier numbers per company code
    supplier_clean = (
        all_data["supplier_number"].astype(str).str.strip()
        .str.replace(r'\.0$', '', regex=True)
    )
    for cc_code, suppliers in CSV_SUPPLIERS.items():
        mask = (cc_clean == cc_code) & supplier_clean.isin(suppliers)
        all_data.loc[mask, "is_csv"] = 1

    reference_clean = all_data.get(
        "reference",
        pd.Series("", index=all_data.index),
    ).astype(str).str.strip()
    for cc_code, supplier_prefixes in CSV_SUPPLIER_REFERENCE_PREFIXES.items():
        for supplier, prefixes in supplier_prefixes.items():
            mask = (
                (cc_clean == cc_code)
                & (supplier_clean == supplier)
                & reference_clean.str.startswith(prefixes, na=False)
            )
            all_data.loc[mask, "is_csv"] = 1

    # Step 3: 1H docs that are NOT CSV -> Envoy
    is_1h = all_data["document_type"] == "1H"
    envoy_mask = is_1h & (all_data["is_csv"] == 0)
    all_data.loc[envoy_mask, "is_csv"] = 2

    # Step 4: Rename 1H docs classified as CSV to "1H-CSV"
    # (Envoy team_member is left as the username mapping from filter_team_members.)
    is_1h_csv = (all_data["document_type"] == "1H") & (all_data["is_csv"] == 1)
    all_data.loc[is_1h_csv, "document_type"] = "1H-CSV"

    # Step 5: Flag reversals (positive amount on normally-negative doc types)
    reversal_types = NORMAL_NEGATIVE_TYPES + ['1H-CSV']
    amount_num = pd.to_numeric(all_data["amount"], errors="coerce")
    all_data["is_reversal"] = np.where(
        all_data["document_type"].isin(reversal_types) & (amount_num > 0),
        1, 0,
    )

    return all_data


def insert_to_sqlite(
    conn: sqlite3.Connection,
    df: pd.DataFrame,
    extraction_date_str: str,
    week_start: datetime,
    week_end: datetime,
    files_processed: dict,
) -> None:
    """Insert processed data into SQLite."""
    columns = [
        "system", "document_type", "entry_date", "posting_date", "document_date",
        "user_id", "team_member", "document_number", "vendor_name",
        "company_code", "country", "amount", "reference",
        "session_name", "is_csv", "supplier_number", "payment_block",
        "is_reversal",
    ]
    df_insert = df[columns].copy()

    df_insert["extraction_date"] = extraction_date_str
    df_insert["week_start"] = str(week_start)
    df_insert["week_end"] = str(week_end)

    # Convert date columns to string
    for col in ["entry_date", "posting_date", "document_date"]:
        df_insert[col] = pd.to_datetime(df_insert[col], errors="coerce").dt.strftime("%Y-%m-%d")

    # Convert amount to float
    df_insert["amount"] = pd.to_numeric(df_insert["amount"], errors="coerce")

    # Clean document_number, supplier_number, company_code: strip .0
    for col in ["document_number", "supplier_number", "company_code"]:
        df_insert[col] = (
            df_insert[col].astype(str).str.strip()
            .str.replace(r'\.0$', '', regex=True)
            .replace("None", None).replace("nan", None)
        )

    # Drop duplicate rows within this batch (same document in same system on same date)
    dedup_cols = ["document_number", "supplier_number", "posting_date", "system"]
    before = len(df_insert)
    df_insert = df_insert.drop_duplicates(subset=dedup_cols, keep="first")
    after = len(df_insert)
    if before > after:
        logger.info("  Dropped %d intra-batch duplicate rows", before - after)

    # Insert rows
    df_insert.to_sql("invoices", conn, if_exists="append", index=False)

    # Record the import
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO weekly_imports (extraction_date, week_start, week_end, imported_at, files_processed, total_rows)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        extraction_date_str,
        str(week_start),
        str(week_end),
        datetime.now().isoformat(),
        json.dumps(list(str(k) for k in files_processed.keys())),
        len(df_insert),
    ))
    conn.commit()


def _gather_files(rebuild_mode: bool, extraction_date_arg: str | None) -> list:
    """
    Gather Excel files to process.

    DEFAULT BEHAVIOR: Process ALL weeks from archive (full history).
    This ensures dashboard always shows complete historical data.

    Special cases:
    - If imports/ has new files -> process those PLUS all archive
    - If --date specified -> process only that specific date
    """
    incoming = get_incoming_dir()

    # If specific date requested, process only that date
    if extraction_date_arg:
        merged_files: dict[str, Path] = {}
        extraction_date = None

        search_dirs: list[Path] = []
        if ARCHIVE_DIR.exists():
            for year_dir in sorted(ARCHIVE_DIR.iterdir()):
                if year_dir.is_dir():
                    search_dirs.extend(month_dir for month_dir in sorted(year_dir.iterdir()) if month_dir.is_dir())
        search_dirs.append(incoming)

        for directory in search_dirs:
            try:
                files, found_date = find_files_for_date(directory, extraction_date_arg)
            except FileNotFoundError:
                continue
            merged_files.update(files)
            extraction_date = found_date
            logger.info(
                "Found %d file(s) in %s for %s",
                len(files),
                directory,
                found_date.strftime("%d/%m/%Y"),
            )

        if merged_files and extraction_date is not None:
            logger.info(
                "Using %d system file(s) for requested extraction date %s",
                len(merged_files),
                extraction_date.strftime("%d/%m/%Y"),
            )
            return [(merged_files, extraction_date)]

        logger.error("No files found for date %s", extraction_date_arg)
        sys.exit(1)

    # DEFAULT: Process ALL weeks from archive + any new files in imports/
    all_dates = []

    # Include new files from imports/ if they exist
    if incoming.exists():
        try:
            all_dates.extend(find_all_extraction_dates(incoming))
            logger.info("Found new files in imports/ - will process along with archive")
        except FileNotFoundError:
            pass

    # ALWAYS include ALL weeks from archive
    if ARCHIVE_DIR.exists():
        for year_dir in sorted(ARCHIVE_DIR.iterdir()):
            if year_dir.is_dir():
                for month_dir in sorted(year_dir.iterdir()):
                    if month_dir.is_dir():
                        try:
                            all_dates.extend(find_all_extraction_dates(month_dir))
                        except FileNotFoundError:
                            pass

    if not all_dates:
        logger.error("No files found in imports/ or archive/")
        sys.exit(1)

    # Sort by date and deduplicate (keep last occurrence per date, prefer archive)
    all_dates.sort(key=lambda x: x[1])
    seen_dates: dict = {}
    for files, date in all_dates:
        if date in seen_dates:
            # Merge file dicts (later entries override earlier for same system)
            seen_dates[date].update(files)
        else:
            seen_dates[date] = dict(files)
    all_dates = [(files, date) for date, files in sorted(seen_dates.items())]
    logger.info("Found %d extraction date(s) to process (ALL weeks)", len(all_dates))
    return all_dates


def process_batch(
    conn: sqlite3.Connection,
    batch_files: dict,
    batch_date: datetime,
    rebuild_mode: bool,
) -> int:
    """Process one extraction batch. Returns number of rows inserted."""
    extraction_date_str = batch_date.strftime("%Y-%m-%d")
    logger.info("--- Processing extraction: %s ---", batch_date.strftime("%d/%m/%Y"))

    for system, path in batch_files.items():
        logger.info("  %s: %s", system, Path(path).name)

    # Check for duplicate import (always check, even in rebuild mode)
    existing = check_duplicate_import(conn, extraction_date_str)
    if existing:
        logger.warning(
            "Data for %s already imported (%d rows). Re-importing...",
            extraction_date_str, existing[1],
        )
        cursor = conn.cursor()
        cursor.execute("DELETE FROM invoices WHERE extraction_date = ?", (extraction_date_str,))
        cursor.execute("DELETE FROM weekly_imports WHERE extraction_date = ?", (extraction_date_str,))
        conn.commit()

    # Read, normalize, filter
    all_frames = []
    doc_types_found: set[str] = set()

    for system_name, filepath in batch_files.items():
        df = read_and_normalize(system_name, filepath)
        df = filter_team_members(df, system_name)
        if len(df) > 0:
            doc_types_found.update(df["document_type"].dropna().unique())
            all_frames.append(df)

    if not all_frames:
        logger.info("No team member data found for %s. Skipping.", extraction_date_str)
        return 0

    all_data = pd.concat(all_frames, ignore_index=True)
    logger.info("  Team member rows: %d", len(all_data))

    # Classify invoices
    all_data = classify_invoices(all_data)

    envoy_count = int((all_data["is_csv"] == 2).sum())
    csv_count = int((all_data["is_csv"] == 1).sum())
    manual_count = int((all_data["is_csv"] == 0).sum())
    reversal_count = int(all_data["is_reversal"].sum())
    logger.info("  Classification: %d manual, %d CSV upload, %d Envoy", manual_count, csv_count, envoy_count)
    logger.info("  Reversals (positive amount): %d", reversal_count)

    # Report unknown doc types
    unknown_doc_types = set(doc_types_found) - set(DOC_TYPE_LABELS.keys())
    if unknown_doc_types:
        logger.info("  Unknown doc types: %s", unknown_doc_types)

    # Detect covered range and filter using ENTRY DATE.
    all_data["entry_date_parsed"] = pd.to_datetime(all_data["entry_date"], errors="coerce")
    week_start, week_end = detect_import_window(batch_date, all_data["entry_date_parsed"])
    logger.info(
        "  Covered period: %s to %s",
        week_start.strftime("%d/%m/%Y"),
        week_end.strftime("%d/%m/%Y"),
    )
    in_range = (
        (all_data["entry_date_parsed"].dt.date >= week_start)
        & (all_data["entry_date_parsed"].dt.date <= week_end)
    )
    all_data = all_data[in_range].copy()
    logger.info("  Rows in week range (by entry date): %d", len(all_data))

    # Insert into SQLite
    insert_to_sqlite(conn, all_data, extraction_date_str, week_start, week_end, batch_files)
    logger.info("  Saved %d rows", len(all_data))

    # Summary (ALL_MEMBERS so former members' imported rows are logged too)
    for member in ALL_MEMBERS:
        m_data = all_data[all_data["team_member"] == member]
        count = len(m_data)
        if count > 0:
            m_manual = int((m_data["is_csv"] == 0).sum())
            m_csv = int((m_data["is_csv"] == 1).sum())
            m_envoy = int((m_data["is_csv"] == 2).sum())
            countries = m_data["country"].value_counts().to_dict()
            countries_str = ", ".join(f"{c}:{n}" for c, n in sorted(countries.items()))
            logger.info("    %-12s: %5d  (M:%d C:%d E:%d)  (%s)", member, count, m_manual, m_csv, m_envoy, countries_str)
    logger.info("    %-12s: %5d", "TOTAL", len(all_data))

    return len(all_data)


def main() -> None:
    """Main entry point for the import pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("=" * 60)
    logger.info("  Invoice Process Dashboard - Data Pipeline")
    logger.info("=" * 60)

    # Parse arguments
    extraction_date_arg = None
    rebuild_mode = "--rebuild" in sys.argv

    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            extraction_date_arg = sys.argv[idx + 1]

    if rebuild_mode:
        logger.info("*** REBUILD MODE: Dropping all data and re-importing ***")
        if DB_PATH.exists():
            DB_PATH.unlink()
            logger.info("Deleted: %s", DB_PATH)

    # Step 1: Initialize database
    logger.info("Step 1: Initializing database...")
    conn = init_db()

    try:
        # Step 2: Find files
        logger.info("Step 2: Finding Excel files...")
        all_dates = _gather_files(rebuild_mode, extraction_date_arg)

        # Step 3: Process each extraction date
        total_rows = 0
        for batch_files, batch_date in all_dates:
            total_rows += process_batch(conn, batch_files, batch_date, rebuild_mode)
    finally:
        conn.close()

    logger.info("=" * 60)
    logger.info("  IMPORT DONE! %d total rows.", total_rows)
    logger.info("  ALL DONE! Run export to generate dashboard.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
