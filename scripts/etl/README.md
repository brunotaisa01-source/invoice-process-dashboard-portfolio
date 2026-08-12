# scripts/etl/

Extract-Transform-Load pipeline for invoice data.

## Modules

- `process_invoices.py` - Main ETL: reads Excel files, normalizes, classifies, stores in SQLite

## Usage

```bash
python -m scripts.etl.process_invoices              # Import latest extraction date
python -m scripts.etl.process_invoices --date 13_02_2026  # Import specific date
python -m scripts.etl.process_invoices --rebuild     # Wipe DB and re-import all
```
