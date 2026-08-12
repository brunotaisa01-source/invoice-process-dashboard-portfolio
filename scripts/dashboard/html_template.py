"""
html_template.py - Dashboard HTML template (Python-generated).
This file contains the complete dashboard HTML with placeholder markers
for library injection. Generated content - edit with care.

Placeholders:
  __CHARTJS_INLINE__  = Chart.js library (inlined from libs/)
  __PAKO_INLINE__     = Pako decompression library (inlined from libs/)
"""

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Invoice Process Dashboard  Synthetic Services</title>
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<!-- Offline-first: Use system fonts (no external dependencies) -->
<style>
  :root {
    --font-sans: 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif;
    --font-mono: 'Consolas', 'SF Mono', 'Monaco', 'Courier New', monospace;
  }
</style>
<script>__CHARTJS_INLINE__</script>
<script>__PAKO_INLINE__</script>
<link rel="stylesheet" href="css/dashboard.css">
</head>
<body>

<!--  WAIT MODE OVERLAY  -->
<div class="wait-overlay" id="waitOverlay">
  <div class="wait-logo"><span class="we">Synthetic</span> <span class="wg">Group</span></div>
  <div class="wait-sub">Invoice Process Dashboard</div>
  <div class="wait-spinner"></div>
  <div class="wait-status" id="waitStatus">Loading data&hellip;</div>
</div>

<!--  SIDEBAR  -->
<aside class="sidebar">
  <div class="sb-logo">
    <div class="OK-brand"><span class="OK-e">Synthetic</span> <span class="OK-g">Group</span></div>
    <p>Invoice Process</p>
  </div>

  <nav class="sb-nav">
    <div class="sb-nav-item active" data-page="overview" onclick="switchPage('overview')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg>
      Overview
    </div>
    <div class="sb-nav-item" data-page="trends" onclick="switchPage('trends')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
      Trends
    </div>
    <div class="sb-nav-item" data-page="detail" onclick="switchPage('detail')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/></svg>
      Detail Table
    </div>
    <div class="sb-nav-item" data-page="calendar" onclick="switchPage('calendar')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/><path d="M8 14h.01"/><path d="M12 14h.01"/><path d="M16 14h.01"/><path d="M8 18h.01"/><path d="M12 18h.01"/></svg>
      Calendar
    </div>
    <div class="sb-nav-item" data-page="sla-email-tracker" onclick="switchPage('sla-email-tracker')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h10"/><path d="m18 16 2 2 3-4"/></svg>
      SLA Tracker
    </div>
    <div class="sb-nav-item" data-page="production" onclick="switchPage('production')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
      Overrides
    </div>
  </nav>

  <div class="sb-sep"></div>

  <!-- Filters -->
  <div class="sb-section">
    <div class="sb-section-title">Posting Type</div>
    <div class="multi-select" id="msType">
      <button type="button" class="ms-btn sb-ms-btn" id="msTypeBtn" onclick="toggleTypeDropdown()">All Types</button>
      <div class="ms-dropdown" id="msTypeDropdown">
        <div class="ms-option"><input type="checkbox" id="mst_manual" value="manual" checked onchange="toggleTypeOption(this)"><label for="mst_manual">Manual Post</label></div>
        <div class="ms-option"><input type="checkbox" id="mst_csv" value="csv" checked onchange="toggleTypeOption(this)"><label for="mst_csv">CSV Upload</label></div>
        <div class="ms-option"><input type="checkbox" id="mst_envoy" value="envoy" checked onchange="toggleTypeOption(this)"><label for="mst_envoy">Envoy</label></div>
      </div>
    </div>
  </div>

  <div class="sb-section">
    <div class="sb-section-title">Reporting Period</div>
    <div class="sb-date-range">
      <label class="sb-date-field">
        <span>From</span>
        <input class="sb-date-input" type="date" id="dateRangeFrom">
      </label>
      <label class="sb-date-field">
        <span>To</span>
        <input class="sb-date-input" type="date" id="dateRangeTo">
      </label>
    </div>
  </div>

  <div class="sb-section">
    <div class="sb-section-title">Team Member</div>
    <select id="filterOwner" class="sb-select">
      <option value="all">All Members</option>
    </select>
  </div>

  <div class="sb-section">
    <div class="sb-section-title">Country</div>
    <select id="filterCountry" class="sb-select">
      <option value="all">All Countries</option>
    </select>
  </div>

  <div class="sb-section">
    <div class="sb-section-title">Document Type</div>
    <select id="filterDocType" class="sb-select">
      <option value="all">All Types</option>
    </select>
  </div>

  <div style="padding:.3rem 1.4rem .4rem">
    <button class="btn-reset-filters" onclick="resetAllFilters()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
      Reset Filters
    </button>
  </div>

  <div style="padding:.4rem 0">
    <button class="theme-toggle" id="themeToggle" onclick="toggleTheme()">
      <svg id="themeIcon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>
      <span id="themeLabel">Light Mode</span>
    </button>
  </div>

  <div class="sb-footer">
    <div id="extractionInfo"></div>
    <div style="margin-top:.3rem">Pipeline v1.0</div>
  </div>
</aside>

<!--  MAIN  -->
<div class="main">
  <!-- PAGE: OVERVIEW -->
  <div id="pageOverview" class="page active"></div>

  <!-- PAGE: TRENDS -->
  <div id="pageTrends" class="page"></div>

  <!-- PAGE: DETAIL TABLE -->
  <div id="pageDetail" class="page"></div>

  <!-- PAGE: CALENDAR -->
  <div id="pageCalendar" class="page"></div>

  <!-- PAGE: SLA EMAIL TRACKER -->
  <div id="pageSlaEmailTracker" class="page"></div>

  <!-- PAGE: PRODUCTION OVERRIDES -->
  <div id="pageProduction" class="page"></div>
</div>

<script src="data.js?v=__BUILD_VERSION__"></script>
<script src="dist/dashboard.js?v=__BUILD_VERSION__"></script>
</body>
</html>
"""  # end HTML_TEMPLATE
