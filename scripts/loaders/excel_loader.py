"""
excel_loader.py - Reads ERP Excel exports and normalizes columns.

Extracts file detection and column normalization logic from the ETL pipeline
for reuse and testability.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from scripts.config import COLUMN_MAP, ERP_SYSTEMS, STANDARD_COLUMNS

logger = logging.getLogger(__name__)

# Regex for ERP file naming: SYSTEM_DD_MM_YYYY.xlsx
FILE_PATTERN = re.compile(
    r'^(?P<system>SYS-A|SYS-B|SYS-C|SYS-D|UK)_(?P<date>\d{2}_\d{2}_\d{4})\.(?:xlsx|XLSX)$',
    re.IGNORECASE,
)


def parse_filename(filename: str) -> Optional[dict]:
    """
    Parse a ERP Excel filename and extract system + date.

    Returns dict with keys: system, date_str, date (date object), or None if no match.
    """
    match = FILE_PATTERN.match(filename)
    if not match:
        return None

    system = match.group("system").upper()
    date_str = match.group("date")
    try:
        date_obj = datetime.strptime(date_str, "%d_%m_%Y").date()
    except ValueError:
        logger.warning("Could not parse date from filename: %s", filename)
        return None

    return {"system": system, "date_str": date_str, "date": date_obj}


def find_excel_files(directory: Path) -> list[dict]:
    """
    Find all ERP Excel files in a directory.

    Returns list of dicts with keys: system, date_str, date, path.
    """
    results = []
    if not directory.exists():
        return results

    for fpath in sorted(directory.iterdir()):
        if fpath.suffix.lower() not in (".xlsx",):
            continue
        parsed = parse_filename(fpath.name)
        if parsed:
            parsed["path"] = fpath
            results.append(parsed)

    return results


def find_files_for_date(
    directory: Path,
    extraction_date: Optional[str] = None,
) -> tuple[dict[str, Path], datetime]:
    """
    Find Excel files for a specific extraction date (or latest).

    Args:
        directory: Path to search for Excel files.
        extraction_date: Optional date string in DD_MM_YYYY format.

    Returns:
        Tuple of (system -> path dict, extraction date as date object).

    Raises:
        FileNotFoundError: If no matching files are found.
    """
    all_parsed = find_excel_files(directory)

    if not all_parsed:
        raise FileNotFoundError(
            f"No ERP Excel files found in {directory}. "
            f"Expected files like SYS-A_13_02_2026.xlsx"
        )

    if extraction_date:
        target_date = datetime.strptime(extraction_date, "%d_%m_%Y").date()
        filtered = [f for f in all_parsed if f["date"] == target_date]
        if not filtered:
            raise FileNotFoundError(
                f"No files found for date {extraction_date} in {directory}"
            )
    else:
        latest_date = max(f["date"] for f in all_parsed)
        filtered = [f for f in all_parsed if f["date"] == latest_date]
        logger.info("Auto-detected extraction date: %s", latest_date.strftime("%d_%m_%Y"))

    files: dict[str, Path] = {}
    for f in filtered:
        files[f["system"]] = f["path"]

    # Warn about missing systems
    for system in ERP_SYSTEMS:
        if system not in files:
            logger.warning("No file found for system %s", system)

    return files, filtered[0]["date"]


def find_all_extraction_dates(directory: Path) -> list[tuple[dict[str, Path], datetime]]:
    """
    Find ALL unique extraction dates across all Excel files.

    Returns list of (files_dict, date) tuples sorted chronologically.
    Used in --rebuild mode.
    """
    all_parsed = find_excel_files(directory)

    if not all_parsed:
        raise FileNotFoundError(f"No valid ERP Excel files found in {directory}")

    dates_map: dict = {}
    for f in all_parsed:
        d = f["date"]
        if d not in dates_map:
            dates_map[d] = {}
        dates_map[d][f["system"]] = f["path"]

    return [(files, date) for date, files in sorted(dates_map.items())]


def read_and_normalize(system_name: str, filepath: Path) -> pd.DataFrame:
    """
    Read one ERP Excel file and normalize columns to standard names.

    Args:
        system_name: ERP system identifier (SYS-A, SYS-B, SYS-C, SYS-D, UK).
        filepath: Path to the Excel file.

    Returns:
        DataFrame with standardized column names.
    """
    df = pd.read_excel(filepath, engine="openpyxl")

    col_map = COLUMN_MAP.get(system_name, {})
    df = df.rename(columns=col_map)

    # RULE: Only SYS-B uses Entry Date column. All other systems use Posting Date.
    # Systems: SYS-A, SYS-C, SYS-D, UK all use posting_date as entry_date
    if system_name != "SYS-B" and "entry_date" not in df.columns:
        df["entry_date"] = df.get("posting_date")

    # Add system identifier
    df["system"] = system_name

    # Ensure all standard columns exist
    for col in STANDARD_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # ERP user IDs are uppercase; normalize before USER_MAP filtering.
    if "user_id" in df.columns:
        df["user_id"] = (
            df["user_id"]
            .astype(str)
            .str.strip()
            .str.replace("\xa0", "", regex=False)
            .str.replace("nan", "", regex=False)
            .str.upper()
        )

    return df
