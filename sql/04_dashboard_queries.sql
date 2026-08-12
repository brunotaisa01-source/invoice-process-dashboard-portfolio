-- ============================================================
-- Invoice Process Dashboard  Dashboard Queries
-- ============================================================
-- Documentation of queries used by export_dashboard.py
-- These are reference queries  not executed directly.

-- @kpi_overview
-- Total invoices, daily average, target achievement
SELECT
    COUNT(*)                                        AS total_invoices,
    COUNT(DISTINCT team_member)                     AS active_members,
    COUNT(DISTINCT entry_date)                      AS working_days,
    ROUND(1.0 * COUNT(*) / COUNT(DISTINCT entry_date), 1) AS daily_avg,
    SUM(CASE WHEN is_csv = 0 THEN 1 ELSE 0 END)    AS manual_total,
    SUM(CASE WHEN is_csv = 1 THEN 1 ELSE 0 END)    AS csv_total,
    SUM(CASE WHEN is_csv = 2 THEN 1 ELSE 0 END)    AS envoy_total
FROM invoices
WHERE extraction_date = ?;

-- @member_daily_performance
-- Per member per day: how many invoices processed
SELECT
    team_member,
    entry_date,
    COUNT(*)                                    AS total,
    SUM(CASE WHEN is_csv = 0 THEN 1 ELSE 0 END) AS manual,
    SUM(CASE WHEN is_csv = 1 THEN 1 ELSE 0 END) AS csv,
    SUM(CASE WHEN is_csv = 2 THEN 1 ELSE 0 END) AS envoy
FROM invoices
WHERE extraction_date = ?
GROUP BY team_member, entry_date
ORDER BY team_member, entry_date;

-- @member_weekly_totals
-- Per member per week: weekly totals for trend page
SELECT
    extraction_date,
    week_start,
    week_end,
    team_member,
    COUNT(*)                                    AS total,
    SUM(CASE WHEN is_csv = 0 THEN 1 ELSE 0 END) AS manual,
    SUM(CASE WHEN is_csv = 1 THEN 1 ELSE 0 END) AS csv,
    SUM(CASE WHEN is_csv = 2 THEN 1 ELSE 0 END) AS envoy
FROM invoices
GROUP BY extraction_date, week_start, week_end, team_member
ORDER BY extraction_date, team_member;

-- @country_breakdown
-- Per country per week: geographic distribution
SELECT
    country,
    COUNT(*)       AS total,
    SUM(amount)    AS total_amount
FROM invoices
WHERE extraction_date = ?
GROUP BY country
ORDER BY total DESC;

-- @doc_type_breakdown
-- Per document type per week
SELECT
    document_type,
    COUNT(*)       AS total,
    SUM(amount)    AS total_amount
FROM invoices
WHERE extraction_date = ?
GROUP BY document_type
ORDER BY total DESC;

-- @trend_weekly
-- Weekly trend across all extraction dates
SELECT
    extraction_date,
    week_start,
    week_end,
    COUNT(*)                                    AS total,
    SUM(CASE WHEN is_csv = 0 THEN 1 ELSE 0 END) AS manual,
    SUM(CASE WHEN is_csv = 1 THEN 1 ELSE 0 END) AS csv,
    SUM(CASE WHEN is_csv = 2 THEN 1 ELSE 0 END) AS envoy,
    SUM(amount)                                 AS total_amount
FROM invoices
GROUP BY extraction_date
ORDER BY extraction_date;

-- @all_weeks
-- List all available weeks
SELECT DISTINCT
    extraction_date,
    week_start,
    week_end
FROM weekly_imports
ORDER BY extraction_date DESC;
