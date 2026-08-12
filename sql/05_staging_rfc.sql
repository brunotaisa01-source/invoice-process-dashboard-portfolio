-- ============================================================
-- Invoice Process Dashboard  RFC Staging (Future)
-- ============================================================
-- Staging table for raw ERP RFC data.
-- When RFC connection is implemented, data will land here first
-- before being normalized and inserted into the invoices table.

CREATE TABLE IF NOT EXISTS rfc_staging (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    system          TEXT NOT NULL,       -- ERP system: SYS-A, SYS-B, SYS-C, SYS-D, UK
    extraction_date TEXT NOT NULL,       -- YYYY-MM-DD
    raw_data        TEXT,                -- JSON blob with raw RFC response
    row_count       INTEGER DEFAULT 0,  -- Number of rows in raw_data
    received_at     TEXT NOT NULL,       -- ISO timestamp when data was received
    processed       INTEGER DEFAULT 0,  -- 0=pending, 1=processed, 2=error
    processed_at    TEXT,                -- ISO timestamp when processed
    error_message   TEXT                 -- Error details if processed=2
);

CREATE INDEX IF NOT EXISTS idx_rfc_pending
    ON rfc_staging(processed, system);

CREATE INDEX IF NOT EXISTS idx_rfc_date
    ON rfc_staging(extraction_date, system);
