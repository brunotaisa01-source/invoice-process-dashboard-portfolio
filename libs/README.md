# Local browser libraries

The exporter reads these vendored files and inlines them into `dashboard/index.html`, allowing the generated dashboard to run without a network dependency.

- `chart.umd.min.js`: Chart.js 4.4.0, MIT, SHA-256 `67d64765fe7e5758e8850b2172e9749ee779f1dd1b7ec12caf666a62dfca0885`.
- `pako.min.js`: pako 2.1.0, MIT and Zlib, SHA-256 `f7f9354862019a7daf4d984715d41272547f90307d850ab2e18e0f892696184a`.

License headers are retained in the files. The full pack inventory is in `DEPENDENCIES.md` and `sbom.cdx.json`.
