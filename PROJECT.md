# Invoice Process Dashboard

This public fixture pack preserves the existing frontend, SQLite, ETL, export, filter, detail, trend, refresh and operator-flow architecture. The repair is surgical: synthetic identities and generic local paths replace private values, generated artifacts were refreshed only where their inputs changed, and publication now requires an affirmative flag.

## Local status and boundary

- Local fixture-to-browser gate: `GREEN`.
- External integration and tenant execution: `RED_EXTERNAL_GATE` because no account, permission, endpoint or remote mutation was exercised.
- Local execution is the default. `scripts/dashboard/export_dashboard.py --deploy` is the only deployment request; it stages and validates before promotion.
- `--help` on bootstrap and export entrypoints is side-effect free.
- All dependencies must be installed outside the pack. No environment, cache or installed dependency tree is included.

The public source identities are a stable one-to-one synthetic mapping: `SYS-A`,
`SYS-B`, `SYS-C` and `SYS-D`. `UK` is retained as the already-generic fifth
source. No private source-system code is required by the local contract.

## Preserved flow

1. `data/fixtures/synthetic_invoices.csv` supplies two deterministic invoice rows.
2. `scripts/bootstrap_local.py` and the preserved ETL modules populate `db/invoices.db` and `dashboard/data/invoices.db`.
3. `scripts/dashboard/export_dashboard.py` emits the core `dashboard/data.js`, HTML and trend cube.
4. The browser loads `DASHBOARD_DATA` from the core file; there is no stale historical chunk competing for that symbol.
5. Overview, Details and Trends retain their filters, reset, refresh, row detail and CSV export behavior.

The relational contract remains 23 invoice columns in the existing order and types. The fixture cardinality is two rows, with a total amount of `80.50`, and the two owner labels are `Synthetic Owner 001` and `Synthetic Owner 002`.

## Source to baseline to repair crosswalk

Hashes are SHA-256. `SOURCE_A` is the project-specific authoritative snapshot; `BASELINE` is the read-only public baseline; `REPAIR` is this pack. Paths are relative to each root.

| Behavior-bearing path | SOURCE_A | BASELINE | REPAIR | Surgical result |
|---|---|---|---|---|
| `scripts/dashboard/export_dashboard.py` | `911e6043bd09085b98814a8592c68d11442070fc125db92eea66ce83b9ee3a04` | `a40e95cb00450aa93be61bfd710d7a3edd87d708b6f9a1856840e58ef52a5d40` | `2b1b2f0fc6bcd3b9fe551f560106d7265da7b17b55d326d591edfca305b0be18` | Preserved generator; added project-root direct execution, local default, explicit deployment, staging and validation. |
| `scripts/etl/process_invoices.py` | `58959b56f17463c7622f08aacf65e1bf1caf0e8e78b0d72c55a1a4498c12770f` | `58959b56f17463c7622f08aacf65e1bf1caf0e8e78b0d72c55a1a4498c12770f` | `91e1bf1b70f5acfc2f3f60f2f186a5e149f02979e551d65be6b91beee7ad6b50` | ETL structure retained; identity and generic system labels only. |
| `dashboard/dist/dashboard.js` | `d0fe09cd484ae544baf52b4f532ffa03f6f44d4c9c2b7a20a69ec8d0e7461bbb` | `16c50a5a8fa22e02f238b56fdb923e22a0ef41f10685ca98e0690ae6c38b6823` | `16c50a5a8fa22e02f238b56fdb923e22a0ef41f10685ca98e0690ae6c38b6823` | Baseline distribution behavior retained byte-for-byte. |
| `automation/lib/RunDailyLatest.ps1` | `6a2dc22409caa3cea8bbe1eec275868362e114255d656b0214636682470fadeb` | `4ab4227db32172642af337b25ece5538da927d78b02362b09905168950a4f099` | `893e22f48ed41e3bae8c95e088ec4ce72a94b91912c3fb7ac2df6408bbf68452` | Daily flow uses bounded pack-local synthetic inputs, explicit sanitized event logging and the separate external gate. |
| `dashboard/index.html` | `a9c58bc798a4db3254a596bce88397da7e9f2e2f18c09118d8563c1a3c2cc773` | `5ca3a797bc9ddbd07ff43e148aeab95df1c2659b2ee4800a96348e5683cd6c` | `26565c949b4cf20260a928af1504faa0de45e7705b3a1c28ab06047efbb71c1a` | Regenerated from the preserved exporter with local assets and current data contract. |
| `dashboard/data.js` | `5a869a6c6d100f4ad77f967eb65503b7b79690503f18902ed255be1dc7547784` | `4997f5ae17d1c165e14b21cb0d07294a0e32262061d1ede095d6ead9edcd8d11` | `5cf7e0ea67a32d2c2bc082050216eb48682f3e35af5f3327a72930a58c1e46a7` | Regenerated synthetic core data; symbol now matches the browser loader. |

Opening tree snapshots were `SOURCE_A=66347ecd2d8831f7c0a13b95b99cb653b505750288d54995654f1410863752b4`, `BASELINE=ebdfbde6ebb976c05420a0896d70464398d45535cca467a5a61f01a01b3c946c`, and `REPAIR=dcf8d9cbab11cd9f8fafdaa005635d3cd85177a4804b2af0ad8d9bbc18531f00`. The closing source and baseline hashes were unchanged. Earlier review observed source drift, so these are time-bounded snapshots and no full equivalence to an unfrozen original is asserted.

The second authoritative integrated source was reviewed as a behavior reference for the file-to-SQLite-to-generated-data-to-browser pipeline and the filter, trend, export and deployment boundaries. Its opening tree hash was `83d703f9a5c30ce7c481b571419b2b8467a520ad44687c8e2d356b8230bd6f41`. It is a structurally different dashboard, so no file identity or equivalence is claimed.

## Reproducible local commands

```powershell
python -B -m scripts.bootstrap_local --check
python scripts\synthetic_e2e.py
python -B -m unittest discover -s tests -v
python -B -m pytest -q -p no:cacheprovider
cmd /d /c automation\RUN_PREFLIGHT.bat
python scripts\dashboard\export_dashboard.py
cmd /d /c automation\RUN_DAILY.bat
```

`RUN_DAILY.bat` is a bounded local fixture flow. It rebuilds from the committed
two-row CSV, applies only pack-local pending JSON, refreshes the pack-local
SQLite/dashboard outputs, and reports `RED_EXTERNAL_GATE` without contacting a
tenant or starting the optional dashboard write bridge.

Daily runtime logs are explicit UTF-8 event logs rather than raw PowerShell
transcripts. They contain only timestamps, public fixture statuses and counts,
pack-relative labels, and the external-gate status. Host identity, executable
paths, user-profile paths and absolute pack paths are excluded.

Serve the pack root with a local HTTP server and open `dashboard/index.html`. The verified real-browser path interacted with refresh, owner filtering, reset, Details, Trends and export, while recording no console or network errors.

See `DEPENDENCIES.md`, `requirements.txt`, `sbom.cdx.json` and `manifest.json` for dependency and gate evidence.

## Limitations

The two-row fixture proves the local contract, not production scale, scheduling, remote permissions or remote data freshness. External integration remains a separate RED gate and was not converted into local code changes.
