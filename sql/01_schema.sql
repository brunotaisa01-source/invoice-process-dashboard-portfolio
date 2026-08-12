-- ============================================================
-- Invoice Process Dashboard  Schema
-- ============================================================

-- Main invoices table: one row per processed document
CREATE TABLE IF NOT EXISTS invoices (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    extraction_date   TEXT,           -- YYYY-MM-DD when ERP data was extracted
    week_start        TEXT,           -- YYYY-MM-DD Friday (start of covered week)
    week_end          TEXT,           -- YYYY-MM-DD Thursday (end of covered week)
    system            TEXT,           -- Source ERP system: SYS-A, SYS-B, SYS-C, SYS-D, UK, ENVOY
    document_type     TEXT,           -- KR, KG, RE, RB, 1H, 1P, ZP, K1, KZ, KA, ST, 1R, KN
    entry_date        TEXT,           -- YYYY-MM-DD when user entered the document
    posting_date      TEXT,           -- YYYY-MM-DD posting date
    document_date     TEXT,           -- YYYY-MM-DD document date
    user_id           TEXT,           -- synthetic source-system user identifier
    team_member       TEXT,           -- synthetic mapped owner identifier
    original_team_member TEXT,        -- Pre-override team member (set once, NULL if never overridden)
    document_number   TEXT,           -- Invoice/PO/credit note number
    vendor_name       TEXT,           -- Supplier name (or Envoy_AP for Envoy rows)
    company_code      TEXT,           -- synthetic company code
    country           TEXT,           -- Mapped: UK, Germany, France, Belgium, Netherlands, Luxemburg
    amount            REAL,           -- Document amount in local currency
    reference         TEXT,           -- Reference code
    session_name      TEXT,           -- ERP session name (or ENVOY_AP)
    is_csv            INTEGER DEFAULT 0,  -- 0=manual, 1=CSV upload, 2=Envoy
    supplier_number   TEXT,           -- Vendor/supplier number
    payment_block     TEXT,           -- Payment block flag
    is_reversal       INTEGER DEFAULT 0  -- 0=normal, 1=reversal (positive amount on normally-negative type)
);

-- Audit trail: one row per weekly import
CREATE TABLE IF NOT EXISTS weekly_imports (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    extraction_date   TEXT,           -- YYYY-MM-DD
    week_start        TEXT,           -- YYYY-MM-DD
    week_end          TEXT,           -- YYYY-MM-DD
    imported_at       TEXT,           -- ISO timestamp of import
    files_processed   TEXT,           -- JSON list of systems processed
    total_rows        INTEGER         -- Total rows inserted
);

-- Team absences: one row per person per absent day
CREATE TABLE IF NOT EXISTS team_absences (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start   TEXT NOT NULL,   -- YYYY-MM-DD (Friday of the covered week)
    member       TEXT NOT NULL,
    date         TEXT NOT NULL,   -- YYYY-MM-DD (the specific absent day)
    type         TEXT NOT NULL,   -- Holiday | Sickness | Other | Half Day
    source       TEXT NOT NULL DEFAULT 'weekly_overrides',
    UNIQUE(week_start, member, date)
);

-- Calendar deletions: persistent tombstones so weekly_overrides cannot
-- resurrect an absence removed from the dashboard Calendar tab.
CREATE TABLE IF NOT EXISTS team_absence_deletions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    member      TEXT NOT NULL,
    date        TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'calendar',
    deleted_at  TEXT NOT NULL,
    created_by  TEXT,
    UNIQUE(member, date)
);

-- Production credit overrides: dashboard-created aggregate adjustments.
-- These do not mutate invoice rows; export applies them to Overview/Trends only.
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
);

-- Persistent tombstones so deleted dashboard overrides are not replayed.
CREATE TABLE IF NOT EXISTS production_override_deletions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    override_id TEXT NOT NULL UNIQUE,
    source      TEXT NOT NULL DEFAULT 'dashboard',
    deleted_at  TEXT NOT NULL,
    created_by  TEXT
);

-- SLA Email Tracker snapshots: imported from controlled Local Fixture Store/Microsoft Lists exports.
-- UI exports intentionally omit run IDs, Local Fixture Store item IDs, message IDs, and conversation IDs.
CREATE TABLE IF NOT EXISTS sla_folder_summary_fast (
    folder_path        TEXT PRIMARY KEY,
    owner              TEXT NOT NULL DEFAULT '',
    open_count         INTEGER NOT NULL DEFAULT 0,
    unread_count       INTEGER NOT NULL DEFAULT 0,
    oldest_received_at TEXT NOT NULL DEFAULT '',
    source_updated_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sla_folder_daily_history (
    snapshot_date      TEXT NOT NULL,
    folder_path        TEXT NOT NULL,
    owner              TEXT NOT NULL DEFAULT '',
    open_count         INTEGER NOT NULL DEFAULT 0,
    unread_count       INTEGER NOT NULL DEFAULT 0,
    net_change         INTEGER NOT NULL DEFAULT 0,
    source_updated_at  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (snapshot_date, folder_path)
);

CREATE TABLE IF NOT EXISTS sla_weekly_owner_summary (
    week_start         TEXT NOT NULL,
    week_end           TEXT NOT NULL,
    owner              TEXT NOT NULL,
    open_count         INTEGER NOT NULL DEFAULT 0,
    folder_count       INTEGER NOT NULL DEFAULT 0,
    start_count        INTEGER NOT NULL DEFAULT 0,
    net_change         INTEGER NOT NULL DEFAULT 0,
    start_unread_count INTEGER NOT NULL DEFAULT 0,
    unread_count       INTEGER NOT NULL DEFAULT 0,
    net_unread_change  INTEGER NOT NULL DEFAULT 0,
    last_snapshot_at   TEXT NOT NULL DEFAULT '',
    weekly_status      TEXT NOT NULL DEFAULT '',
    source_updated_at  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (week_start, owner)
);

CREATE TABLE IF NOT EXISTS sla_email_tracker_open (
    email_key          TEXT PRIMARY KEY,
    received_at        TEXT NOT NULL,
    sender_email       TEXT NOT NULL DEFAULT '',
    sender_name        TEXT NOT NULL DEFAULT '',
    subject            TEXT NOT NULL DEFAULT '',
    owner              TEXT NOT NULL DEFAULT '',
    folder_path        TEXT NOT NULL DEFAULT '',
    sla_status         TEXT NOT NULL DEFAULT '',
    supplier_key       TEXT NOT NULL DEFAULT '',
    source_updated_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sla_action_log (
    action_key         TEXT PRIMARY KEY,
    email_key          TEXT NOT NULL,
    received_at        TEXT NOT NULL,
    actioned_at        TEXT NOT NULL,
    sender_email       TEXT NOT NULL DEFAULT '',
    sender_name        TEXT NOT NULL DEFAULT '',
    subject            TEXT NOT NULL DEFAULT '',
    owner              TEXT NOT NULL DEFAULT '',
    action             TEXT NOT NULL DEFAULT '',
    folder_path        TEXT NOT NULL DEFAULT '',
    supplier_key       TEXT NOT NULL DEFAULT '',
    source_updated_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sla_folder_audit_state (
    folder_path        TEXT PRIMARY KEY,
    last_seen_at       TEXT NOT NULL DEFAULT '',
    oldest_received_at TEXT NOT NULL DEFAULT '',
    open_count         INTEGER NOT NULL DEFAULT 0,
    source_updated_at  TEXT NOT NULL DEFAULT ''
);
