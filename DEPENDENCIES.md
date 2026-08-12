# Dependency inventory

Dependencies are installed in an environment outside this pack. No environment, package cache, `node_modules` directory or installed dependency tree is included.

## Python pins

`requirements.txt` pins the local runtime, document helper, browser test and quality tooling used by this pack:

- pandas `2.2.3`
- numpy `2.4.6`
- openpyxl `3.1.5`
- pywin32 `311`
- python-pptx `1.0.2`
- pytest `9.0.2`
- pytest-cov `7.0.0`
- playwright `1.58.0`
- ruff `0.15.6`

The SQLite interface is supplied by the Python standard library.

## Vendored browser libraries

| Path | Version | License | Bytes | SHA-256 |
|---|---:|---|---:|---|
| `libs/chart.umd.min.js` | 4.4.0 | MIT | 205201 | `67d64765fe7e5758e8850b2172e9749ee779f1dd1b7ec12caf666a62dfca0885` |
| `libs/pako.min.js` | 2.1.0 | MIT and Zlib | 46828 | `f7f9354862019a7daf4d984715d41272547f90307d850ab2e18e0f892696184a` |

These files are locally vendored because the generated dashboard is designed to run without a network dependency. Their existing license headers are retained.
