Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-TextFileAtomic {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $Content
    )

    $directory = Split-Path -Parent $Path
    $name = Split-Path -Leaf $Path
    $tmp = Join-Path $directory (".${name}.$PID.tmp")

    $encoding = [System.Text.UTF8Encoding]::new($false)
    $stream = [System.IO.FileStream]::new(
        $tmp,
        [System.IO.FileMode]::Create,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::None
    )
    try {
        $writer = [System.IO.StreamWriter]::new($stream, $encoding)
        try {
            $writer.Write($Content)
            $writer.Flush()
            $stream.Flush($true)
        } finally {
            $writer.Dispose()
        }
    } finally {
        $stream.Dispose()
    }

    try {
        [System.IO.File]::Replace($tmp, $Path, $null, $true)
    } catch {
        Move-Item -LiteralPath $tmp -Destination $Path -Force
    }
}

function Invoke-PackDashboardPatch {
    param(
        [Parameter(Mandatory = $true)]
        [string] $DashboardDir
    )

    $indexPath = Join-Path $DashboardDir "index.html"

    if (-not (Test-Path -LiteralPath $indexPath)) {
        throw "Dashboard index.html missing: $indexPath"
    }

    $html = [System.IO.File]::ReadAllText($indexPath)
    $html = [regex]::Replace(
        $html,
        "(?s)\s*<!-- PACK DATE FILTER START -->.*?<!-- PACK DATE FILTER END -->\s*",
        "`r`n"
    )
    $html = [regex]::Replace(
        $html,
        "(?s)\s*<!-- PACK PRODUCTION OVERRIDES NAV START -->.*?<!-- PACK PRODUCTION OVERRIDES NAV END -->\s*",
        "`r`n"
    )
    $html = [regex]::Replace(
        $html,
        "(?s)\s*<!-- PACK PRODUCTION OVERRIDES PAGE START -->.*?<!-- PACK PRODUCTION OVERRIDES PAGE END -->\s*",
        "`r`n"
    )
    $html = [regex]::Replace(
        $html,
        "(?m)^\s*<script\s+src=`"pack-date-filter\.js`"></script>\s*(`r?`n)?",
        ""
    )
    $html = [regex]::Replace(
        $html,
        "(?m)^\s*<script\s+src=`"pack-production-overrides\.js`"></script>\s*(`r?`n)?",
        ""
    )

    $dashboardScriptPattern = '<script\s+src="dist/dashboard\.js(?:\?[^"]*)?"></script>'
    if (-not [regex]::IsMatch($html, $dashboardScriptPattern)) {
        throw "Could not find dashboard script tag in $indexPath"
    }

    $productionNavCount = ([regex]::Matches($html, 'data-page="production"')).Count
    $productionPageCount = ([regex]::Matches($html, 'id="pageProduction"')).Count
    if ($productionNavCount -ne 1) {
        throw "Expected exactly one native Production Overrides nav item, found $productionNavCount in $indexPath"
    }
    if ($productionPageCount -ne 1) {
        throw "Expected exactly one native Production Overrides page, found $productionPageCount in $indexPath"
    }

    Write-TextFileAtomic -Path $indexPath -Content $html
    Write-Host "[OK] Pack dashboard patch applied: legacy Production Overrides injection removed; native page preserved."
}
