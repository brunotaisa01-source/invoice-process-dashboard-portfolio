-- ============================================================
-- Invoice Process Dashboard  Views
-- ============================================================

-- Latest extraction week
CREATE VIEW IF NOT EXISTS v_latest_week AS
SELECT *
FROM invoices
WHERE extraction_date = (SELECT MAX(extraction_date) FROM invoices);

-- Daily summary: per member per day with manual/csv/envoy breakdown
CREATE VIEW IF NOT EXISTS v_daily_summary AS
SELECT
    entry_date,
    team_member,
    COUNT(*)                                    AS total,
    SUM(CASE WHEN is_csv = 0 THEN 1 ELSE 0 END) AS manual,
    SUM(CASE WHEN is_csv = 1 THEN 1 ELSE 0 END) AS csv,
    SUM(CASE WHEN is_csv = 2 THEN 1 ELSE 0 END) AS envoy,
    SUM(amount)                                 AS total_amount,
    extraction_date,
    week_start,
    week_end
FROM invoices
GROUP BY entry_date, team_member, extraction_date;

-- Weekly summary: per member per week with breakdown
CREATE VIEW IF NOT EXISTS v_weekly_summary AS
SELECT
    extraction_date,
    week_start,
    week_end,
    team_member,
    COUNT(*)                                    AS total,
    SUM(CASE WHEN is_csv = 0 THEN 1 ELSE 0 END) AS manual,
    SUM(CASE WHEN is_csv = 1 THEN 1 ELSE 0 END) AS csv,
    SUM(CASE WHEN is_csv = 2 THEN 1 ELSE 0 END) AS envoy,
    SUM(amount)                                 AS total_amount,
    COUNT(DISTINCT country)                     AS countries_served
FROM invoices
GROUP BY extraction_date, week_start, week_end, team_member;

-- Country summary: per country per week
CREATE VIEW IF NOT EXISTS v_country_summary AS
SELECT
    extraction_date,
    week_start,
    week_end,
    country,
    COUNT(*)                                    AS total,
    SUM(CASE WHEN is_csv = 0 THEN 1 ELSE 0 END) AS manual,
    SUM(CASE WHEN is_csv = 1 THEN 1 ELSE 0 END) AS csv,
    SUM(CASE WHEN is_csv = 2 THEN 1 ELSE 0 END) AS envoy,
    SUM(amount)                                 AS total_amount,
    COUNT(DISTINCT team_member)                 AS members_active
FROM invoices
GROUP BY extraction_date, week_start, week_end, country;

-- Document type summary: per doc type per week
CREATE VIEW IF NOT EXISTS v_doc_type_summary AS
SELECT
    extraction_date,
    week_start,
    week_end,
    document_type,
    COUNT(*)                                    AS total,
    SUM(CASE WHEN is_csv = 0 THEN 1 ELSE 0 END) AS manual,
    SUM(CASE WHEN is_csv = 1 THEN 1 ELSE 0 END) AS csv,
    SUM(CASE WHEN is_csv = 2 THEN 1 ELSE 0 END) AS envoy,
    SUM(amount)                                 AS total_amount
FROM invoices
GROUP BY extraction_date, week_start, week_end, document_type;

-- System summary: per ERP system per week
CREATE VIEW IF NOT EXISTS v_system_summary AS
SELECT
    extraction_date,
    week_start,
    week_end,
    system,
    COUNT(*)                                    AS total,
    SUM(CASE WHEN is_csv = 0 THEN 1 ELSE 0 END) AS manual,
    SUM(CASE WHEN is_csv = 1 THEN 1 ELSE 0 END) AS csv,
    SUM(CASE WHEN is_csv = 2 THEN 1 ELSE 0 END) AS envoy,
    SUM(amount)                                 AS total_amount,
    COUNT(DISTINCT team_member)                 AS members_active
FROM invoices
GROUP BY extraction_date, week_start, week_end, system;
