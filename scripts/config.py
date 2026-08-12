"""
config.py - Central configuration for the Invoice Process Dashboard.

Edit this file when team composition, ERP column names, or systems change.
All paths are imported from scripts.paths (no hardcoded os.path.join here).
"""
from __future__ import annotations

from scripts.paths import (
    ROOT, DATA_DIR, INCOMING_DIR, ARCHIVE_DIR, DB_DIR, DB_PATH,
    DASHBOARD_DIR, DATA_JS_PATH, LIBS_DIR, DEPLOY_DIR,
    get_incoming_dir,
)

# Re-export paths for backward compatibility with src/config.py consumers
BASE_DIR = str(ROOT)
IMPORTS_DIR = str(get_incoming_dir())

# --- ERP System File Prefixes ---
ERP_SYSTEMS: list[str] = ["SYS-A", "SYS-B", "SYS-C", "SYS-D", "UK"]

# --- Column Mapping (system-specific column name -> standardized name) ---
COLUMN_MAP: dict[str, dict[str, str]] = {
    "SYS-A": {
        "Document Type": "document_type",
        # Note: SYS-A has NO "Entry Date" column - uses Posting Date instead (handled in excel_loader.py)
        "Posting Date": "posting_date",
        "Document Date": "document_date",
        "User Name": "user_id",
        "Vendor Account: Name 1": "vendor_name",
        "Supplier": "supplier_number",
        "Document Number": "document_number",
        "Company Code": "company_code",
        "Company Code Currency Value": "amount",
        "Reference": "reference",
        "Session Name": "session_name",
        "Payment Block": "payment_block",
    },
    "SYS-B": {
        "Document type": "document_type",
        "Entry Date": "entry_date",
        "Posting Date": "posting_date",
        "Document Date": "document_date",
        "User Name": "user_id",
        "Text": "vendor_name",
        "Account": "supplier_number",
        "Document Number": "document_number",
        "Company Code": "company_code",
        "Amount in Doc. Curr.": "amount",
        "Reference": "reference",
        "Payment block": "payment_block",
    },
    "SYS-C": {
        "Document Type": "document_type",
        "Entry Date": "entry_date",
        "Posting Date": "posting_date",
        "Document Date": "document_date",
        "User name": "user_id",
        "Vendor Name 1": "vendor_name",
        "Vendor": "supplier_number",
        "Document Number": "document_number",
        "Company Code": "company_code",
        "Amount in local currency": "amount",
        "Reference": "reference",
        "Session name": "session_name",
    },
    "SYS-D": {
        "Document Type": "document_type",
        "Entry Date": "entry_date",
        "Posting Date": "posting_date",
        "Document Date": "document_date",
        "User name": "user_id",
        "Name 1": "vendor_name",
        "Supplier": "supplier_number",
        "Document Number": "document_number",
        "Company Code": "company_code",
        "Amount in doc. curr.": "amount",
        "Reference": "reference",
        "Session name": "session_name",
        "Payment Block": "payment_block",
    },
    "UK": {
        "Journal Entry Type": "document_type",
        "Posting Date": "posting_date",
        "Journal Entry Date": "document_date",
        "Journal Entry Created By": "user_id",
        "Supplier Name": "vendor_name",
        "Supplier": "supplier_number",
        "Journal Entry": "document_number",
        "Company Code": "company_code",
        "Amount (Tran Cur.)": "amount",
        "Reference": "reference",
        "Item Payment Block": "payment_block",
    },
}

# --- Synthetic source-user ID to synthetic owner (per system) ---
# The mapping keeps the source interface shape without retaining identities.
USER_MAP: dict[str, dict[str, str]] = {
    "SYS-A": {
        "SYN-SYS-A-USER-001": "Synthetic Owner 001",
        "SYN-SYS-A-USER-002": "Synthetic Owner 002",
    },
    "SYS-B": {
        "SYN-SYS-B-USER-001": "Synthetic Owner 001",
        "SYN-SYS-B-USER-002": "Synthetic Owner 002",
    },
    "SYS-C": {
        "SYN-SYS-C-USER-001": "Synthetic Owner 001",
        "SYN-SYS-C-USER-002": "Synthetic Owner 002",
    },
    "SYS-D": {
        "SYN-SYS-D-USER-001": "Synthetic Owner 001",
        "SYN-SYS-D-USER-002": "Synthetic Owner 002",
    },
    "UK": {
        "SYN-UK-USER-001": "Synthetic Owner 001",
        "SYN-UK-USER-002": "Synthetic Owner 002",
    },
}

# --- Former Members (left the team) ---
# Add a name here when a member leaves. KEEP their USER_MAP entries so their
# historical invoices are preserved (rebuild-safe) and keep showing in
# trends/totals/detail. Former members are EXCLUDED from active targets and the
# Overview donut, but INCLUDED in historical aggregation. Generic mechanism --
# applies to anyone removed in the future, not just one person.
FORMER_MEMBERS: set[str] = set()

# --- All mapped members (active + former), sorted -- for historical display ---
ALL_MEMBERS: list[str] = sorted(set(
    name for system_map in USER_MAP.values() for name in system_map.values()
))

# --- Active Team Members (sorted) -- drives targets and the Overview donut ---
TEAM_MEMBERS: list[str] = sorted(set(ALL_MEMBERS) - FORMER_MEMBERS)

# --- Document Type Descriptions ---
DOC_TYPE_LABELS: dict[str, str] = {
    "KR": "Invoice",
    "KG": "Credit Note",
    "RE": "PO Invoice",
    "RB": "48 PO",
    "1H": "Envoy Upload",
    "1H-CSV": "CSV Upload",
    "1P": "Intercompany",
    "ZP": "Payment",
    "K1": "Vendor Invoice",
    "KZ": "Payment Posting",
    "KA": "Vendor Document",
    "ST": "Reversal",
    "1R": "Reversal Doc",
}

# --- Quality Metrics: Reversals & Credit Notes ---
# Credit notes: identified by document type alone (always positive amounts)
CREDIT_NOTE_TYPES: list[str] = ['KG', 'ST', '1R']
# Normally-negative types: positive amount = reversal
NORMAL_NEGATIVE_TYPES: list[str] = ['KR', 'RE', 'RB', '1H']

# --- Company Code -> Country Mapping ---
COMPANY_CODE_COUNTRY_MAP: dict[str, str] = {
    "SYN-CC-001": "Northland",
    "SYN-CC-002": "Southland",
}
COUNTRIES: list[str] = sorted(set(COMPANY_CODE_COUNTRY_MAP.values()))

# --- CSV Upload Identification ---
# Session names that indicate CSV/automated upload
CSV_SESSION_NAMES: list[str] = []

# Vendor name patterns for CSV uploads (case-insensitive partial match)
# These vendors have automated CSV invoice uploads
CSV_VENDOR_PATTERNS: list[str] = [
    "Synthetic Supplier Beta",
]

# --- CSV Suppliers by company code ---
# Supplier numbers that are automated CSV uploads (any doc type).
# For 1H docs: matching suppliers -> CSV; non-matching -> Envoy.
# For other doc types (e.g. KR in GB38): matching suppliers -> CSV.
CSV_SUPPLIERS: dict[str, set[str]] = {
    "SYN-CC-002": {"SYN-SUP-002"},
}

# Supplier numbers that are CSV only when the invoice reference starts with
# one of the configured prefixes.
CSV_SUPPLIER_REFERENCE_PREFIXES: dict[str, dict[str, tuple[str, ...]]] = {
    "SYN-CC-002": {
        "SYN-SUP-002": ("SYN-CSV-",),
    },
}

# --- Envoy (1H) attribution ---
# Envoy invoices are attributed by the uploader's ERP username via USER_MAP,
# exactly like manual posts. There is NO country-based reassignment.
# Country-based reassignment is intentionally disabled to preserve uploader attribution.

# --- Daily Target per team member ---
DAILY_TARGET: int = 100  # invoices per person per day
WORKING_DAYS_PER_WEEK: int = 5  # Mon-Fri (used for weekly target calculation)

# --- Individual Targets (optional override per person) ---
# Leave empty to use DAILY_TARGET for everyone.
# Example: {"Synthetic Owner 001": 120}
INDIVIDUAL_TARGETS: dict[str, int] = {}

# --- Standard columns kept after normalization ---
STANDARD_COLUMNS: list[str] = [
    "document_type",
    "entry_date",
    "posting_date",
    "document_date",
    "user_id",
    "vendor_name",
    "supplier_number",
    "document_number",
    "company_code",
    "amount",
    "reference",
    "system",
    "team_member",
    "session_name",
    "payment_block",
]
