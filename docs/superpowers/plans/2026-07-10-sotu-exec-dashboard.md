# State of the Union Exec Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/sotu` exec dashboard page to Solstice showing stuck reason boxes with counts, M9 historical completions by month/region, and M9 forecast by month/region.

**Architecture:** New `/api/sotu` FastAPI endpoint in `dashboard.py` serving four data blocks (KPI banner, stuck reasons, historical completions, forecast). New `static/sotu.html` consuming it. Nav entry added to `solstice.js`.

**Tech Stack:** FastAPI, SQLite (solstice.db), vanilla JS, existing Solstice CSS (solstice.css)

## Global Constraints

- No npm/npx — everything is vanilla JS + existing CDN fonts
- SQLite DB path: `/data/solstice.db` (Docker mount); Python accesses via `get_db()` helper
- `blocked_data` stores integers `0`/`1` for boolean columns (m8_started, m9_complete, etc.)
- `m9_planned` is stored as MM/DD/YYYY strings — must parse with `datetime.strptime(v, '%m/%d/%Y')`
- `account_theatre` is on both `accounts` and `blocked_data` tables; prefer `blocked_data.account_theatre`
- Theatre values: `AMER`, `EMEA`, `JAPAC`, `LATAM`
- Nav version bump: all HTML pages reference `/static/solstice.js?v=3` — bump to `v=4` across all pages when adding nav entry
- Never git from CC/ root. Commit from `Solstice/` only: `git -C Solstice/ commit ...`
- Page title format: `Solstice — SOTU`

## Data Reference (verified from DB 2026-07-10)

**Stuck reason subtypes (m9_complete=0, subtype!='churn'):**
- customer_delay: AMER=119, EMEA=37, JAPAC=68, LATAM=36 → total 260
- tech_blocker: AMER=68, EMEA=47, JAPAC=50, LATAM=21 → total 186
- core_rep_blocking: AMER=24, EMEA=75, JAPAC=61, LATAM=2 → total 162
- no_contact: AMER=70, EMEA=38, JAPAC=25, LATAM=1 → total 134
- active_deal: AMER=3, EMEA=10, JAPAC=4 → total 17
- legal_blocker: EMEA=1, JAPAC=2 → total 3

**M9 completions (status_history):** Jan=5, Feb=10, Mar=20, Apr=16, May=14, Jun=23, Jul=6 (partial)

**M9 forecast (m9_planned, non-churn, non-complete):** Jul=177, Aug=169, Sep=148, Oct=249, Nov=112, Dec=194

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `dashboard.py` | Modify | Add `/api/sotu` endpoint + `/sotu` page route |
| `static/sotu.html` | Create | Exec dashboard HTML + JS |
| `static/solstice.js` | Modify | Add SOTU to `_PAGES` nav array, bump to v=4 |
| All other `static/*.html` | Modify | Bump solstice.js reference from `?v=3` to `?v=4` |

---

## Task 1: `/api/sotu` backend endpoint

**Files:**
- Modify: `dashboard.py` (add after line ~2968, before `/api/velocity`)

**Interfaces:**
- Produces: `GET /api/sotu?theatre=` → JSON (shape below)
- Consumes: `get_db()` helper, `blocked_data` table, `accounts` table, `status_history` table

**Response shape:**
```json
{
  "kpi": {
    "in_scope": 1727,
    "m9_complete": 94,
    "m8_inflight": 283,
    "not_started": 1053,
    "churn": 310
  },
  "stuck": [
    {"subtype": "customer_delay", "label": "Customer Delay", "total": 260,
     "by_theatre": {"AMER": 119, "EMEA": 37, "JAPAC": 68, "LATAM": 36}},
    ...
  ],
  "completions": [
    {"month": "2026-01", "AMER": 3, "EMEA": 1, "JAPAC": 0, "LATAM": 1, "total": 5},
    ...
  ],
  "forecast": [
    {"month": "2026-07", "AMER": 65, "EMEA": 46, "JAPAC": 42, "LATAM": 24, "total": 177},
    ...
  ]
}
```

- [ ] **Step 1: Add the endpoint to dashboard.py**

Find the line `@app.get("/api/velocity")` (around line 2990) and insert the following **above** it:

```python
@app.get("/api/sotu")
def api_sotu(theatre: str = ""):
    """State of the Union exec dashboard data."""
    _ensure_db()
    THEATRES = ["AMER", "EMEA", "JAPAC", "LATAM"]
    SUBTYPE_LABELS = {
        "customer_delay": "Customer Delay",
        "tech_blocker": "Tech Blocker",
        "core_rep_blocking": "Core Rep Blocking",
        "no_contact": "No Contact",
        "active_deal": "Active Deal",
        "legal_blocker": "Legal Blocker",
    }
    th_filter = theatre.upper() if theatre else ""

    with get_db() as conn:
        # ── KPI banner ──────────────────────────────────────────────
        def _kpi_count(where_extra: str, params: list) -> int:
            base = "SELECT COUNT(*) FROM blocked_data b JOIN accounts a ON a.account_id = b.account_id WHERE b.cohort = 'Scale cohort'"
            if th_filter:
                base += " AND UPPER(COALESCE(b.account_theatre,'')) = ?"
                params = [th_filter] + params
            row = conn.execute(base + (" AND " + where_extra if where_extra else ""), params).fetchone()
            return row[0] if row else 0

        th_cond = "AND UPPER(COALESCE(b.account_theatre,'')) = ?" if th_filter else ""
        th_params = [th_filter] if th_filter else []

        in_scope = _kpi_count("", [])
        m9_complete = _kpi_count("b.m9_complete = 1", [])
        m8_inflight = _kpi_count("b.m8_started = 1 AND b.m9_complete = 0", [])
        churn = _kpi_count("b.subtype = 'churn'", [])
        not_started = _kpi_count("b.m8_started = 0 AND b.m9_complete = 0 AND b.subtype != 'churn'", [])

        # ── Stuck reasons ────────────────────────────────────────────
        stuck_sql = f"""
            SELECT b.subtype, b.account_theatre, COUNT(*) as cnt
            FROM blocked_data b JOIN accounts a ON a.account_id = b.account_id
            WHERE b.cohort = 'Scale cohort'
              AND b.m9_complete = 0
              AND b.subtype != '' AND b.subtype != 'churn'
              {th_cond}
            GROUP BY b.subtype, b.account_theatre
            ORDER BY b.subtype, b.account_theatre
        """
        stuck_rows = conn.execute(stuck_sql, th_params).fetchall()

        stuck_by_type: dict = {}
        for subtype, theatre_val, cnt in stuck_rows:
            if subtype not in stuck_by_type:
                stuck_by_type[subtype] = {"subtype": subtype, "label": SUBTYPE_LABELS.get(subtype, subtype), "total": 0, "by_theatre": {}}
            stuck_by_type[subtype]["total"] += cnt
            stuck_by_type[subtype]["by_theatre"][theatre_val or "Unknown"] = cnt

        subtype_order = ["customer_delay", "tech_blocker", "core_rep_blocking", "no_contact", "active_deal", "legal_blocker"]
        stuck = [stuck_by_type[k] for k in subtype_order if k in stuck_by_type]
        # Append any unexpected subtypes at end
        for k, v in stuck_by_type.items():
            if k not in subtype_order:
                stuck.append(v)

        # ── Historical completions (status_history) ──────────────────
        hist_th_cond = "AND UPPER(COALESCE(b.account_theatre,'')) = ?" if th_filter else ""
        hist_sql = f"""
            SELECT strftime('%Y-%m', h.changed_at) as month,
                   COALESCE(b.account_theatre, 'Unknown') as theatre,
                   COUNT(*) as cnt
            FROM status_history h
            JOIN accounts a ON a.account_id = h.account_id
            LEFT JOIN blocked_data b ON b.account_id = h.account_id
            WHERE h.field_name = 'M9 Upgrade Complete'
              AND h.new_status = 'Y'
              AND h.changed_at >= '2026-01-01'
              {hist_th_cond}
            GROUP BY month, theatre
            ORDER BY month, theatre
        """
        hist_rows = conn.execute(hist_sql, th_params).fetchall()

        comp_by_month: dict = {}
        for month, theatre_val, cnt in hist_rows:
            if month not in comp_by_month:
                comp_by_month[month] = {t: 0 for t in THEATRES}
                comp_by_month[month]["month"] = month
            if theatre_val in THEATRES:
                comp_by_month[month][theatre_val] = cnt

        completions = []
        for month in sorted(comp_by_month.keys()):
            row = comp_by_month[month]
            row["total"] = sum(row.get(t, 0) for t in THEATRES)
            completions.append(row)

        # ── Forecast (m9_planned, non-churn, non-complete) ───────────
        from datetime import datetime as _dt
        fcast_th_cond = "AND UPPER(COALESCE(b.account_theatre,'')) = ?" if th_filter else ""
        fcast_sql = f"""
            SELECT b.m9_planned, b.account_theatre
            FROM blocked_data b JOIN accounts a ON a.account_id = b.account_id
            WHERE b.cohort = 'Scale cohort'
              AND b.m9_complete = 0
              AND b.subtype != 'churn'
              AND b.m9_planned IS NOT NULL AND b.m9_planned != ''
              {fcast_th_cond}
        """
        fcast_rows = conn.execute(fcast_sql, th_params).fetchall()

        fcast_by_month: dict = {}
        for m9p, theatre_val in fcast_rows:
            try:
                d = _dt.strptime(str(m9p).strip(), "%m/%d/%Y")
                ym = d.strftime("%Y-%m")
                if ym < "2026-07":
                    continue
                if ym not in fcast_by_month:
                    fcast_by_month[ym] = {t: 0 for t in THEATRES}
                    fcast_by_month[ym]["month"] = ym
                if (theatre_val or "") in THEATRES:
                    fcast_by_month[ym][theatre_val] = fcast_by_month[ym].get(theatre_val, 0) + 1
            except (ValueError, TypeError):
                pass

        forecast = []
        for month in sorted(fcast_by_month.keys())[:8]:
            row = fcast_by_month[month]
            row["total"] = sum(row.get(t, 0) for t in THEATRES)
            forecast.append(row)

    return {
        "kpi": {
            "in_scope": in_scope,
            "m9_complete": m9_complete,
            "m8_inflight": m8_inflight,
            "not_started": not_started,
            "churn": churn,
        },
        "stuck": stuck,
        "completions": completions,
        "forecast": forecast,
    }
```

- [ ] **Step 2: Add the page route to dashboard.py**

Find `@app.get("/cse", response_class=HTMLResponse)` (around line 3144) and insert **above** it:

```python
@app.get("/sotu", response_class=HTMLResponse)
def page_sotu():
    html_path = Path(__file__).parent / "static" / "sotu.html"
    if html_path.exists():
        return html_path.read_text()
    return "<h1>sotu.html not found</h1>"
```

- [ ] **Step 3: Verify endpoint (no rebuild needed — uvicorn auto-reloads)**

```bash
curl -s "http://localhost:8200/api/sotu" | python3 -m json.tool | head -60
```
Expected: JSON with keys `kpi`, `stuck`, `completions`, `forecast`. `kpi.m9_complete` should be `94`, `kpi.m8_inflight` should be `283`.

- [ ] **Step 4: Test theatre filter**

```bash
curl -s "http://localhost:8200/api/sotu?theatre=EMEA" | python3 -m json.tool | python3 -c "import sys,json; d=json.load(sys.stdin); print('stuck total customer_delay:', next(s['total'] for s in d['stuck'] if s['subtype']=='customer_delay'))"
```
Expected: `37`

---

## Task 2: `static/sotu.html` — exec dashboard page

**Files:**
- Create: `Solstice/static/sotu.html`

**Interfaces:**
- Consumes: `GET /api/sotu?theatre=<t>` (from Task 1)
- Produces: Visual exec dashboard page at `http://localhost:8200/sotu`

**Layout sections:**
1. Theatre filter pills (All / EMEA / AMER / JAPAC / LATAM)
2. KPI banner (5 cards: In Scope, M9 Done, M8 In-flight, Not Started, Churn)
3. Stuck Reasons grid — one card per subtype, big number + theatre breakdown
4. M9 Completions table — rows=months, cols=AMER/EMEA/JAPAC/LATAM/Total
5. M9 Forecast table — same structure, future months

- [ ] **Step 1: Create `static/sotu.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>&#x1F4CA;</text></svg>">
<title>Solstice — SOTU</title>
<link rel="stylesheet" href="/static/solstice.css">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
.sotu-controls{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-bottom:1.5rem}
.sotu-section{margin-bottom:2.5rem}
.sotu-title{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:.8rem}

/* KPI banner */
.sotu-kpi{display:flex;gap:.75rem;flex-wrap:wrap;margin-bottom:2rem}
.sotu-kpi .kpi-card{flex:1;min-width:140px}

/* Stuck reason grid */
.stuck-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.75rem}
.stuck-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem 1.25rem}
.stuck-card.customer_delay{border-left:4px solid #f97316}
.stuck-card.tech_blocker{border-left:4px solid #ef4444}
.stuck-card.core_rep_blocking{border-left:4px solid #8b5cf6}
.stuck-card.no_contact{border-left:4px solid #64748b}
.stuck-card.active_deal{border-left:4px solid #0ea5e9}
.stuck-card.legal_blocker{border-left:4px solid #f59e0b}
.stuck-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-family:var(--mono);margin-bottom:.35rem}
.stuck-num{font-size:2.4rem;font-weight:800;line-height:1;margin-bottom:.6rem;color:var(--text)}
.stuck-breakdown{display:flex;flex-wrap:wrap;gap:.3rem}
.stuck-th{font-size:8px;font-family:var(--mono);background:var(--surface-2);border:1px solid var(--border);border-radius:3px;padding:1px 5px;color:var(--muted)}
.stuck-th span{color:var(--text);font-weight:700}

/* Monthly tables */
.mtbl{width:100%;border-collapse:collapse}
.mtbl th{padding:.4rem .7rem;font-size:8px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-family:var(--mono);font-weight:700;background:var(--surface);border-bottom:2px solid var(--border);text-align:left;white-space:nowrap}
.mtbl th.r,.mtbl td.r{text-align:right}
.mtbl td{padding:.5rem .7rem;font-size:.85rem;border-bottom:1px solid var(--border-soft);color:var(--text);font-family:var(--mono)}
.mtbl tr:hover td{background:var(--surface-2)}
.mtbl td.muted{color:var(--muted)}
.total-cell{font-weight:700;color:var(--sky)}
.fcast-badge{display:inline-flex;align-items:center;justify-content:center;min-width:32px;padding:2px 7px;border-radius:4px;background:var(--sky-light);color:var(--sky);font-weight:700;border:1px solid var(--sky-border)}
.hist-badge{display:inline-flex;align-items:center;justify-content:center;min-width:28px;padding:2px 6px;border-radius:4px;background:#d1fae5;color:#065f46;font-weight:700;border:1px solid #6ee7b7}
.partial-tag{font-size:7px;color:var(--muted);font-family:var(--mono);margin-left:.25rem;vertical-align:middle}
</style>
</head>
<body>
<nav id="s-nav" class="s-nav"></nav>
<div class="s-main">

  <!-- Theatre filter -->
  <div class="sotu-controls">
    <span class="pill active" data-t="" onclick="setTheatre(this,'')">All</span>
    <span class="pill" data-t="EMEA" onclick="setTheatre(this,'EMEA')">EMEA</span>
    <span class="pill" data-t="AMER" onclick="setTheatre(this,'AMER')">AMER</span>
    <span class="pill" data-t="JAPAC" onclick="setTheatre(this,'JAPAC')">JAPAC</span>
    <span class="pill" data-t="LATAM" onclick="setTheatre(this,'LATAM')">LATAM</span>
  </div>

  <!-- KPI Banner -->
  <div class="sotu-kpi" id="sotu-kpi">
    <div class="kpi-card" style="background:var(--surface);border:1px solid var(--border)"><div class="kpi-label">In Scope</div><div class="kpi-number" id="kpi-scope">—</div><div class="kpi-delta delta-neu">Scale cohort</div></div>
    <div class="kpi-card green"><div class="kpi-label">M9 Complete</div><div class="kpi-number" id="kpi-m9">—</div><div class="kpi-delta delta-pos">Migrations done</div></div>
    <div class="kpi-card sky"><div class="kpi-label">M8 In-flight</div><div class="kpi-number" id="kpi-m8">—</div><div class="kpi-delta delta-neu">Upgrade started</div></div>
    <div class="kpi-card amber"><div class="kpi-label">Not Started</div><div class="kpi-number" id="kpi-ns">—</div><div class="kpi-delta delta-neu">No M8 yet</div></div>
    <div class="kpi-card red"><div class="kpi-label">Churn</div><div class="kpi-number" id="kpi-churn">—</div><div class="kpi-delta delta-neg">Confirmed churn</div></div>
  </div>

  <!-- Stuck Reasons -->
  <div class="sotu-section">
    <div class="sotu-title">Stuck Reasons — Accounts Not Yet M9 (Non-Churn)</div>
    <div class="stuck-grid" id="stuck-grid"></div>
  </div>

  <!-- Historical completions -->
  <div class="sotu-section">
    <div class="sotu-title">M9 Completions — 2026 by Month &amp; Region</div>
    <div style="overflow-x:auto"><table class="mtbl" id="comp-tbl"><tbody><tr><td class="muted">Loading…</td></tr></tbody></table></div>
  </div>

  <!-- Forecast -->
  <div class="sotu-section">
    <div class="sotu-title">M9 Forecast — Planned Completions by Month &amp; Region</div>
    <div style="overflow-x:auto"><table class="mtbl" id="fcast-tbl"><tbody><tr><td class="muted">Loading…</td></tr></tbody></table></div>
  </div>

</div>

<script src="/static/solstice.js?v=4"></script>
<script>
S.initNav('sotu');
S.restoreCard();

var E = S.esc;
var _theatre = '';
var THEATRES = ['AMER','EMEA','JAPAC','LATAM'];

var STUCK_META = {
  customer_delay:   {label:'Customer Delay',   color:'#f97316'},
  tech_blocker:     {label:'Tech Blocker',      color:'#ef4444'},
  core_rep_blocking:{label:'Core Rep Blocking', color:'#8b5cf6'},
  no_contact:       {label:'No Contact',        color:'#64748b'},
  active_deal:      {label:'Active Deal',       color:'#0ea5e9'},
  legal_blocker:    {label:'Legal Blocker',     color:'#f59e0b'},
};

function setTheatre(el, t) {
  _theatre = t;
  document.querySelectorAll('.sotu-controls [data-t]').forEach(function(p) {
    p.classList.toggle('active', p.dataset.t === t);
  });
  load();
}

function load() {
  var url = '/api/sotu' + (_theatre ? '?theatre=' + encodeURIComponent(_theatre) : '');
  fetch(url).then(function(r){ return r.json(); }).then(render).catch(function() {
    document.getElementById('stuck-grid').innerHTML = '<div style="color:var(--muted);font-size:10px">Error loading data</div>';
  });
}

function render(d) {
  renderKpi(d.kpi);
  renderStuck(d.stuck);
  renderCompletions(d.completions);
  renderForecast(d.forecast);
}

function renderKpi(k) {
  document.getElementById('kpi-scope').textContent  = (k.in_scope  || 0).toLocaleString();
  document.getElementById('kpi-m9').textContent     = (k.m9_complete || 0).toLocaleString();
  document.getElementById('kpi-m8').textContent     = (k.m8_inflight || 0).toLocaleString();
  document.getElementById('kpi-ns').textContent     = (k.not_started || 0).toLocaleString();
  document.getElementById('kpi-churn').textContent  = (k.churn || 0).toLocaleString();
}

function renderStuck(stuck) {
  if (!stuck || !stuck.length) {
    document.getElementById('stuck-grid').innerHTML = '<div style="color:var(--muted);font-size:10px">No blocked accounts</div>';
    return;
  }
  var html = '';
  stuck.forEach(function(s) {
    var meta = STUCK_META[s.subtype] || {label: s.label || s.subtype};
    html += '<div class="stuck-card ' + E(s.subtype) + '">';
    html += '<div class="stuck-label">' + E(meta.label || s.label) + '</div>';
    html += '<div class="stuck-num">' + (s.total || 0) + '</div>';
    html += '<div class="stuck-breakdown">';
    var by = s.by_theatre || {};
    THEATRES.forEach(function(t) {
      var v = by[t];
      if (v) {
        html += '<span class="stuck-th">' + E(t) + ' <span>' + v + '</span></span>';
      }
    });
    html += '</div></div>';
  });
  document.getElementById('stuck-grid').innerHTML = html;
}

function _monthLabel(ym) {
  var parts = ym.split('-');
  var d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, 1);
  return d.toLocaleString('default', {month:'short'}) + ' ' + parts[0].slice(2);
}

function renderCompletions(rows) {
  if (!rows || !rows.length) {
    document.getElementById('comp-tbl').innerHTML = '<tbody><tr><td class="muted">No data</td></tr></tbody>';
    return;
  }
  var thisMonth = new Date().toISOString().slice(0,7);
  var html = '<thead><tr><th>Month</th>';
  THEATRES.forEach(function(t){ html += '<th class="r">' + E(t) + '</th>'; });
  html += '<th class="r">Total</th></tr></thead><tbody>';
  rows.forEach(function(row) {
    var isPartial = row.month === thisMonth;
    html += '<tr><td>' + _monthLabel(row.month) + (isPartial ? '<span class="partial-tag">partial</span>' : '') + '</td>';
    THEATRES.forEach(function(t) {
      var v = row[t] || 0;
      html += '<td class="r">' + (v ? '<span class="hist-badge">' + v + '</span>' : '<span class="muted">—</span>') + '</td>';
    });
    html += '<td class="r total-cell">' + (row.total || 0) + '</td></tr>';
  });
  html += '</tbody>';
  document.getElementById('comp-tbl').innerHTML = html;
}

function renderForecast(rows) {
  if (!rows || !rows.length) {
    document.getElementById('fcast-tbl').innerHTML = '<tbody><tr><td class="muted">No forecast data</td></tr></tbody>';
    return;
  }
  var html = '<thead><tr><th>Month</th>';
  THEATRES.forEach(function(t){ html += '<th class="r">' + E(t) + '</th>'; });
  html += '<th class="r">Total (Planned)</th></tr></thead><tbody>';
  rows.forEach(function(row) {
    html += '<tr><td>' + _monthLabel(row.month) + '</td>';
    THEATRES.forEach(function(t) {
      var v = row[t] || 0;
      html += '<td class="r">' + (v ? '<span class="fcast-badge">' + v + '</span>' : '<span class="muted">—</span>') + '</td>';
    });
    html += '<td class="r total-cell">' + (row.total || 0) + '</td></tr>';
  });
  html += '</tbody>';
  document.getElementById('fcast-tbl').innerHTML = html;
}

load();
</script>
</body>
</html>
```

- [ ] **Step 2: Verify page loads in browser**

Open `http://localhost:8200/sotu`

Expected:
- Theatre pills at top
- 5 KPI cards: In Scope ~1727, M9 Complete 94, M8 In-flight 283, Not Started ~1053, Churn 310
- 6 stuck reason cards with big numbers and theatre breakdown chips
- Completions table: Jan–Jul 2026 rows, per-theatre green badges
- Forecast table: Jul–Dec 2026 rows (and beyond), blue badges

---

## Task 3: Add SOTU to nav + bump JS version

**Files:**
- Modify: `static/solstice.js` (add nav entry, no version bump in this file — version is in HTML references)
- Modify: all `static/*.html` files — change `?v=3` → `?v=4`

**Interfaces:**
- Consumes: nothing new
- Produces: SOTU appears in nav bar on every page

- [ ] **Step 1: Add SOTU to `_PAGES` in `solstice.js`**

Find in `static/solstice.js`:
```javascript
var _PAGES = [
  {id:'ops',     label:'Ops',      url:'/ops'},
```

Add `sotu` as the **second** entry (exec-facing, high visibility):
```javascript
var _PAGES = [
  {id:'ops',     label:'Ops',      url:'/ops'},
  {id:'sotu',    label:'SOTU',     url:'/sotu'},
  {id:'blockers',label:'Blockers', url:'/blockers'},
```

- [ ] **Step 2: Bump solstice.js reference to v=4 in all HTML files**

Run this to find all HTML files referencing v=3:
```bash
grep -rl "solstice.js?v=3" /Users/mbanica/Documents/Code_Samples/CC/Solstice/static/
```

For each file returned, replace `solstice.js?v=3` with `solstice.js?v=4`.

Files expected: velocity.html, scope.html, wins.html, cse.html, blockers.html, v2.html, daily.html, forecast.html, audit.html, weekly.html (and sotu.html already has v=4).

- [ ] **Step 3: Hard-refresh browser and verify SOTU appears in nav**

Open any page (e.g. `http://localhost:8200/ops`), hard refresh (Cmd+Shift+R), confirm "SOTU" link appears in nav.

---

## Task 4: Commit

- [ ] **Step 1: Stage and commit**

```bash
git -C /Users/mbanica/Documents/Code_Samples/CC/Solstice add \
  static/sotu.html \
  static/solstice.js \
  dashboard.py \
  static/velocity.html static/scope.html static/wins.html \
  static/cse.html static/blockers.html static/v2.html \
  static/daily.html static/forecast.html static/audit.html static/weekly.html

git -C /Users/mbanica/Documents/Code_Samples/CC/Solstice commit -m "feat: add State of the Union exec dashboard (/sotu)

- New /api/sotu endpoint: KPI banner, stuck reasons by subtype+theatre,
  M9 historical completions by month, M9 forecast from m9_planned
- New static/sotu.html: exec-facing page with theatre filter pills,
  5 KPI cards, 6 stuck reason cards, completions + forecast tables
- Add SOTU to nav (position 2, after Ops)
- Bump solstice.js reference to ?v=4 across all pages"
```

- [ ] **Step 2: Verify git status is clean**

```bash
git -C /Users/mbanica/Documents/Code_Samples/CC/Solstice status
```
Expected: `nothing to commit, working tree clean`
