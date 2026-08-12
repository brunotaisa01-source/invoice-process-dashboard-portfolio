# scripts/dashboard/

Dashboard data export and HTML generation.

## Modules

- `export_dashboard.py` - Queries SQLite, builds compressed data.js, deploys to S: drive
- `html_template.py` - Python string template for index.html (124 KB)

## Usage

```bash
python -m scripts.dashboard.export_dashboard              # Generate data.js + deploy
python -m scripts.dashboard.export_dashboard --force-html  # Regenerate index.html
python -m scripts.dashboard.export_dashboard --no-deploy   # Local only
```
