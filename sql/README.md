# sql/

SQL schema, indexes, views, and queries for the SQLite database.

## Files (executed in order)

| File | Purpose |
|------|---------|
| `01_schema.sql` | Table definitions (invoices, weekly_imports) |
| `02_indexes.sql` | 9 indexes for query performance |
| `03_views.sql` | 6 views (daily_summary, weekly_summary, etc.) |
| `04_dashboard_queries.sql` | Named queries for dashboard data extraction |
| `05_staging_rfc.sql` | Staging table for future RFC integration |

## Naming Convention

Files are numbered `NN_name.sql` and executed in numeric order by `sql_loader.py`.
