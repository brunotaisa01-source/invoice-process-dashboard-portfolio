# Architecture and validation map

This document gives a visual map of the public Invoice Process Dashboard pack. It is documentation only: the invoice ETL, SQLite handoff, dashboard, calendar/override/SLA flows and tests are unchanged.

For the cross-repository view, see the [portfolio architecture map](https://github.com/brunotaisa01-source/escalation-app-portfolio/blob/main/docs/PORTFOLIO_MAP.md).

## Runtime flow

```mermaid
flowchart LR
  F["Synthetic invoice fixture\ndata/fixtures/synthetic_invoices.csv"] --> B["Local bootstrap and ETL\nscripts/bootstrap_local.py + scripts/etl/"]
  B --> DB["Pack-local SQLite handoffs\ndb/invoices.db + dashboard/data/invoices.db"]
  DB --> X["Dashboard exporter\nscripts/dashboard/export_dashboard.py"]
  X --> D["Generated data, HTML and trend cube\ndashboard/data.js + dashboard/"]
  D --> UI["Browser dashboard\noverview, details and trends"]
  A["Calendar, override, SLA and daily automation\nautomation/ + scripts/"] --> B
  UI --> O["Filters, refresh, detail and CSV export"]
  X --> H["Validated local promotion/handoff"]
```

The default path is local and uses the two-row synthetic fixture. Deployment is an explicit opt-in path with staging and validation; the pack does not perform a remote mutation by default.

## Test and status flow

```mermaid
flowchart LR
  A["bootstrap_local.py --check"] --> M["Local validation evidence"]
  B["synthetic_e2e.py"] --> M
  C["unittest + pytest suites"] --> M
  D["Preflight, manifest and sanitization checks"] --> M
  E["Browser smoke: filters, details, trends and export"] --> M
  M --> G["GREEN_LOCAL\nfixture-to-browser evidence"]
  X["External integration, tenant execution, deployment and remote readback\nnot exercised"] --> R["RED_EXTERNAL_GATE"]
```

`GREEN_LOCAL` is limited to the fixture, local database, generated browser assets and documented smoke checks. `RED_EXTERNAL_GATE` remains for remote credentials, permissions, live refresh, production scheduling, deployment and readback.

## Main entrypoints

- `python -B -m scripts.bootstrap_local --check` runs the local preflight.
- `python scripts\synthetic_e2e.py` runs the synthetic end-to-end path.
- `python -B -m unittest discover -s tests -v` and `python -B -m pytest -q -p no:cacheprovider` run the suites.
- `cmd /d /c automation\RUN_PREFLIGHT.bat` and `RUN_DAILY.bat` exercise the bounded automation paths.
- `manifest.json` and `runtime/manifests/e2e_latest.json` record local evidence.
