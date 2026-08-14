# Invoice Process Dashboard

This is a complete local portfolio pack for a generic invoice process dashboard. It preserves the browser frontend, generated distribution asset, loaders, calendar/override/SLA flows, SQL, SQLite handoff and automation entrypoints with deterministic fake inputs.

For the portfolio overview, contribution scope and AI-assisted engineering context, see [PORTFOLIO_CONTEXT.md](PORTFOLIO_CONTEXT.md).

For the visual architecture and validation gates, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## What this project delivers

- A generic invoice process dashboard with overview, details, trends, filters, refresh and CSV export.
- Local invoice ETL, two SQLite handoffs, generated browser data and a validated promotion path.
- Calendar, override, SLA and daily automation entrypoints using deterministic synthetic inputs.
- Python, pytest, preflight, manifest, sanitization and browser validation contracts.

## Problem it solves

It gives finance and operations teams a repeatable view of invoice flow, ownership, aging and SLA-related workload. The local pipeline reduces manual reporting and makes process bottlenecks easier to identify without exposing operational data.

## Quick start

Exact validated dependency set: Python 3.11.9; `pandas==2.2.3`, `numpy==2.4.6`, `openpyxl==3.1.5`, `pywin32==311`, `python-pptx==1.0.2`, `pytest==9.0.2`, `pytest-cov==7.0.0`, and `ruff==0.15.6`. Optional syntax tool: Node.js 24.18.0. Install only from the manifest:

```powershell
python -m pip install -r requirements.txt
python scripts\synthetic_e2e.py
python -m unittest tests\test_synthetic_contract.py
python -m http.server 8764
```

Open `dashboard/index.html` through the local server. Evidence is written to `manifest.json` and `runtime/manifests/e2e_latest.json`. See [PROJECT.md](PROJECT.md) for the complete description.
