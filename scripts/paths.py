"""
paths.py - Centralized path resolution for the Invoice Process Dashboard.

All paths are ROOT-relative and portable. No hardcoded absolute paths.
Import this module wherever you need file system paths.

Usage:
    from scripts.paths import ROOT, DATA_DIR, DB_PATH, DASHBOARD_DIR
"""
from __future__ import annotations

import os
from pathlib import Path

# Project root: two levels up from scripts/paths.py
ROOT = Path(__file__).resolve().parent.parent

# --- Data directories ---
DATA_DIR = ROOT / "data"
ARCHIVE_DIR = DATA_DIR / "archive"

# --- Incoming directory: data/incoming/ is the staging area for latest week ---
INCOMING_DIR = DATA_DIR / "incoming"

def get_incoming_dir() -> Path:
    """Return the incoming directory (data/incoming/ folder for latest week only)."""
    return INCOMING_DIR


# --- Database ---
DB_DIR = ROOT / "db"
DB_PATH_ENV = os.environ.get("INVOICE_DASHBOARD_DB_PATH")
DB_PATH = Path(DB_PATH_ENV) if DB_PATH_ENV else DB_DIR / "invoices.db"

# --- Dashboard ---
DASHBOARD_DIR = ROOT / "dashboard"
DATA_JS_PATH = DASHBOARD_DIR / "data.js"
DATA_CHUNKS_DIR = DASHBOARD_DIR / "data_chunks"

# --- Libraries ---
LIBS_DIR = ROOT / "libs"

# --- SQL ---
SQL_DIR = ROOT / "sql"

# --- Logs ---
LOGS_DIR = ROOT / "logs"

# --- Deploy Path (pack-local only) ---
DEPLOY_DIR_ENV = os.environ.get("INVOICE_DASHBOARD_DEPLOY_DIR")
DEPLOY_DIR = Path(DEPLOY_DIR_ENV) if DEPLOY_DIR_ENV else DASHBOARD_DIR

# --- Calendar absences (saved by the published dashboard) ---
CALENDAR_DIR_ENV = os.environ.get("INVOICE_DASHBOARD_CALENDAR_DIR")
CALENDAR_DIR = Path(CALENDAR_DIR_ENV) if CALENDAR_DIR_ENV else DEPLOY_DIR / "Calendar"
CALENDAR_PENDING_DIR = CALENDAR_DIR / "pending"
CALENDAR_PROCESSED_DIR = CALENDAR_DIR / "processed"
CALENDAR_REJECTED_DIR = CALENDAR_DIR / "rejected"

# --- Production credit overrides (saved by the published dashboard) ---
PRODUCTION_OVERRIDES_DIR_ENV = os.environ.get("INVOICE_DASHBOARD_PRODUCTION_OVERRIDES_DIR")
PRODUCTION_OVERRIDES_DIR = (
    Path(PRODUCTION_OVERRIDES_DIR_ENV)
    if PRODUCTION_OVERRIDES_DIR_ENV
    else DEPLOY_DIR / "ProductionOverrides"
)
PRODUCTION_OVERRIDES_PENDING_DIR = PRODUCTION_OVERRIDES_DIR / "pending"
PRODUCTION_OVERRIDES_PROCESSED_DIR = PRODUCTION_OVERRIDES_DIR / "processed"
PRODUCTION_OVERRIDES_REJECTED_DIR = PRODUCTION_OVERRIDES_DIR / "rejected"

# --- SLA Email Tracker controlled snapshots (Local Fixture Store/Microsoft Lists exports) ---
DEFAULT_SLA_SITE_URL = ""
SLA_TRACKER_SNAPSHOT_DIR_ENV = os.environ.get("INVOICE_DASHBOARD_SLA_TRACKER_SNAPSHOT_DIR")
SLA_TRACKER_SNAPSHOT_DIR = (
    Path(SLA_TRACKER_SNAPSHOT_DIR_ENV)
    if SLA_TRACKER_SNAPSHOT_DIR_ENV
    else DATA_DIR / "sla_tracker_snapshots"
)
SLA_SITE_URL_ENV = os.environ.get("INVOICE_DASHBOARD_SLA_SITE_URL")
SLA_SITE_URL = (
    SLA_SITE_URL_ENV.strip()
    if SLA_SITE_URL_ENV and SLA_SITE_URL_ENV.strip()
    else DEFAULT_SLA_SITE_URL
)

# --- Tests ---
TESTS_DIR = ROOT / "tests"
FIXTURES_DIR = TESTS_DIR / "fixtures"


def ensure_dirs() -> None:
    """Create all required directories if they don't exist."""
    for d in [DATA_DIR, ARCHIVE_DIR, DB_DIR,
              DASHBOARD_DIR, LOGS_DIR, DATA_CHUNKS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    # INCOMING_DIR is optional - only create when needed


def ensure_calendar_dirs() -> None:
    """Create the published Calendar folders without touching their contents."""
    for d in [CALENDAR_DIR, CALENDAR_PENDING_DIR, CALENDAR_PROCESSED_DIR, CALENDAR_REJECTED_DIR]:
        try:
            if d.is_dir():
                continue
        except OSError:
            continue
        d.mkdir(parents=True, exist_ok=True)


def ensure_production_override_dirs() -> None:
    """Create the published ProductionOverrides folders without touching contents."""
    for d in [
        PRODUCTION_OVERRIDES_DIR,
        PRODUCTION_OVERRIDES_PENDING_DIR,
        PRODUCTION_OVERRIDES_PROCESSED_DIR,
        PRODUCTION_OVERRIDES_REJECTED_DIR,
    ]:
        try:
            if d.is_dir():
                continue
        except OSError:
            continue
        d.mkdir(parents=True, exist_ok=True)
