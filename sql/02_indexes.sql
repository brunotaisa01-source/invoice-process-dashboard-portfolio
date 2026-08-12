-- ============================================================
-- Invoice Process Dashboard  Indexes
-- ============================================================

-- Core indexes (used by import pipeline)
CREATE INDEX IF NOT EXISTS idx_week         ON invoices(week_start, week_end);
CREATE INDEX IF NOT EXISTS idx_member       ON invoices(team_member);
CREATE INDEX IF NOT EXISTS idx_entry_date   ON invoices(entry_date);
CREATE INDEX IF NOT EXISTS idx_extraction   ON invoices(extraction_date);
CREATE INDEX IF NOT EXISTS idx_country      ON invoices(country);
CREATE INDEX IF NOT EXISTS idx_is_csv       ON invoices(is_csv);

-- Composite indexes (used by dashboard queries)
CREATE INDEX IF NOT EXISTS idx_member_entry   ON invoices(team_member, entry_date);
CREATE INDEX IF NOT EXISTS idx_extract_csv    ON invoices(extraction_date, is_csv);
CREATE INDEX IF NOT EXISTS idx_week_member    ON invoices(week_start, team_member);

-- Prevent duplicate weekly imports (same extraction_date should only be imported once)
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_import ON weekly_imports(extraction_date);

-- Production override lookup for dashboard export
CREATE INDEX IF NOT EXISTS idx_production_overrides_week_type
    ON production_overrides(week_start, work_type);

-- SLA Email Tracker export lookups
CREATE INDEX IF NOT EXISTS idx_sla_open_received
    ON sla_email_tracker_open(received_at);
CREATE INDEX IF NOT EXISTS idx_sla_open_owner
    ON sla_email_tracker_open(owner);
CREATE INDEX IF NOT EXISTS idx_sla_action_received
    ON sla_action_log(received_at);
CREATE INDEX IF NOT EXISTS idx_sla_action_actioned
    ON sla_action_log(actioned_at);
CREATE INDEX IF NOT EXISTS idx_sla_action_owner
    ON sla_action_log(owner);
CREATE INDEX IF NOT EXISTS idx_sla_weekly_owner_week
    ON sla_weekly_owner_summary(week_start, owner);
CREATE INDEX IF NOT EXISTS idx_sla_daily_history_date
    ON sla_folder_daily_history(snapshot_date);
