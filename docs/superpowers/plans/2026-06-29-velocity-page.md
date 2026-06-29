# Velocity Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/velocity` page that shows this week's milestone activity by region (M1–M9 counts in a grid) plus a historical weekly velocity table with user-selectable time range and a Refresh Now button.

**Architecture:** Single FastAPI endpoint `/api/velocity` queries `status_history` and returns both the current-week summary (all theatres) and the historical table (theatre-filterable). A new `static/velocity.html` renders both sections. Nav updated in `solstice.js`.

**Tech Stack:** FastAPI, SQLite (`status_history` + `blocked_data`), vanilla JS, existing Solstice CSS design system.

## Global Constraints

- All milestone data from `status_history` — do not touch `blocked_data.m8_started` or `m9_complete` for counts on this page
- Week boundary: Monday 00:00 → Sunday 23:59 UTC
- Milestones shown: M1 Outreach, M2 Entitlements, M3 Buy-in, M4 Discovery, M5 Tech Validation, M8 Upgrade Started, M9 Upgrade Complete (skip M0, M6, M7)
- Theatre filter applies to history table only; "This Week" grid always shows all 4 theatres
- No charting, no sparklines, no per-account drill-down
- Follow existing CSS classes: `wtbl`, `pill`, `s-main`, `badge-*`
- All new JS uses `var` and `function` (no ES6 — matches rest of codebase)

---

### Task 1: `/api/velocity` endpoint

**Files:**
- Modify: `dashboard.py` — add endpoint after `api_weekly_movements` (~line 2185)
- Create: `tests/test_api_velocity.py`

**Interfaces:**
- Produces: `GET /api/velocity?weeks=12&theatre=EMEA` →
  ```json
  {
    "this_week": {
      "range": "Jun 23 – Jun 29",
      "by_theatre": {
        "AMER":  {"M1 Outreach": 1, "M8 Upgrade Started": 3, "M9 Upgrade Complete": 2},
        "EMEA":  {},
        "JAPAC": {},
        "LATAM": {}
      }
    },
    "history": [
      {"week": "Jun 23", "M1 Outreach": 3, "M8 Upgrade Started": 7, "M9 Upgrade Complete": 3},
      {"week": "Jun 16", "M1 Outreach": 2, "M8 Upgrade Started": 9, "M9 Upgrade Complete": 4}
    ],
    "updated_at": "2026-06-29T15:45:00"
  }
  ```

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_velocity.py`:

```python
"""Tests for /api/velocity."""

import pytest
from contextlib import contextmanager
from unittest.mock import patch
from datetime import date, timedelta, datetime, timezone
from fastapi.testclient import TestClient
from agent.db import init_db, get_db

MILESTONES = [
    "M1 Outreach", "M2 Entitlements", "M3 Buy-in", "M4 Discovery",
    "M5 Tech Validation", "M8 Upgrade Started", "M9 Upgrade Complete",
]


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.db"
    init_db(p)
    return p


def _seed(db, rows):
    """rows: list of (account_id, name, theatre, field_name, changed_at)"""
    with get_db(db) as conn:
        for aid, name, theatre, field_name, changed_at in rows:
            conn.execute(
                "INSERT OR IGNORE INTO accounts (account_id,customer_name,active_cse,sales_region,account_theatre) VALUES (?,?,?,?,?)",
                (aid, name, "CSE", "Region", theatre),
            )
            conn.execute(
                "INSERT OR IGNORE INTO blocked_data (account_id,signal,m9_complete,account_theatre,cohort) VALUES (?,?,?,?,?)",
                (aid, "green", 0, theatre, "Scale cohort"),
            )
            conn.execute(
                "INSERT INTO status_history (account_id,field_name,old_status,new_status,changed_at) VALUES (?,?,?,?,?)",
                (aid, field_name, "N", "Y", changed_at),
            )


@contextmanager
def _client(db):
    with (
        patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)),
        patch("dashboard.init_db"),
        patch("dashboard._ensure_db"),
    ):
        from dashboard import app
        yield TestClient(app, raise_server_exceptions=False)


def _this_monday():
    today = date.today()
    return today - timedelta(days=today.weekday())


def test_this_week_all_theatres(db):
    """this_week.by_theatre always has all 4 theatres regardless of theatre param."""
    monday = _this_monday()
    ts = f"{monday}T10:00:00"
    _seed(db, [
        ("a1", "Alpha", "EMEA", "M8 Upgrade Started", ts),
        ("a2", "Beta",  "AMER", "M9 Upgrade Complete", ts),
    ])
    with _client(db) as c:
        r = c.get("/api/velocity?weeks=4&theatre=EMEA")
    assert r.status_code == 200
    data = r.json()
    assert set(data["this_week"]["by_theatre"].keys()) == {"AMER", "EMEA", "JAPAC", "LATAM"}
    assert data["this_week"]["by_theatre"]["EMEA"]["M8 Upgrade Started"] == 1
    assert data["this_week"]["by_theatre"]["AMER"]["M9 Upgrade Complete"] == 1


def test_history_theatre_filter(db):
    """History rows are filtered by theatre param."""
    monday = _this_monday() - timedelta(weeks=1)
    ts = f"{monday}T10:00:00"
    _seed(db, [
        ("b1", "Bravo", "EMEA", "M8 Upgrade Started", ts),
        ("b2", "Charlie", "AMER", "M8 Upgrade Started", ts),
    ])
    with _client(db) as c:
        r = c.get("/api/velocity?weeks=4&theatre=EMEA")
    data = r.json()
    # history filtered to EMEA only
    week_row = data["history"][0] if data["history"] else {}
    assert week_row.get("M8 Upgrade Started", 0) == 1


def test_history_theatre_all(db):
    """When theatre='', history sums across all theatres."""
    monday = _this_monday() - timedelta(weeks=1)
    ts = f"{monday}T10:00:00"
    _seed(db, [
        ("c1", "Delta", "EMEA", "M8 Upgrade Started", ts),
        ("c2", "Echo",  "AMER", "M8 Upgrade Started", ts),
    ])
    with _client(db) as c:
        r = c.get("/api/velocity?weeks=4")
    data = r.json()
    week_row = data["history"][0] if data["history"] else {}
    assert week_row.get("M8 Upgrade Started", 0) == 2


def test_weeks_param_limits_history(db):
    """history contains at most `weeks` entries."""
    with _client(db) as c:
        r = c.get("/api/velocity?weeks=4")
    data = r.json()
    assert len(data["history"]) <= 4


def test_response_shape(db):
    """Response has required keys."""
    with _client(db) as c:
        r = c.get("/api/velocity")
    data = r.json()
    assert "this_week" in data
    assert "history" in data
    assert "updated_at" in data
    assert "range" in data["this_week"]
    assert "by_theatre" in data["this_week"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
python3 -m pytest tests/test_api_velocity.py -v 2>&1 | head -30
```

Expected: 5 failures, all "404 Not Found" or attribute errors.

- [ ] **Step 3: Implement the endpoint in `dashboard.py`**

Find the line after `api_weekly_movements` ends (search for `@app.get("/weekly"` ~line 3055) and insert before the `/weekly` HTML route. Add this block:

```python
@app.get("/api/velocity")
def api_velocity(weeks: int = 12, theatre: str = ""):
    """Milestone velocity — this week summary + N-week history by region."""
    from datetime import date as _date, timedelta, datetime as _dt, timezone

    _ensure_db()

    MILESTONES = [
        "M1 Outreach", "M2 Entitlements", "M3 Buy-in", "M4 Discovery",
        "M5 Tech Validation", "M8 Upgrade Started", "M9 Upgrade Complete",
    ]
    THEATRES = ["AMER", "EMEA", "JAPAC", "LATAM"]

    today = _date.today()
    this_monday = today - timedelta(days=today.weekday())

    weeks = max(1, min(weeks, 104))  # cap at 2 years

    def _week_label(monday: _date) -> str:
        return monday.strftime("%b %-d")

    def _count_week(monday: _date, theatre_filter: str) -> dict:
        """Count milestone completions in the given Mon–Sun window."""
        sun = monday + timedelta(days=6)
        mon_s = monday.isoformat()
        sun_s = sun.isoformat() + "T23:59:59"
        t_clause = (
            "AND UPPER(COALESCE(b.account_theatre, a.account_theatre,'EMEA'))=UPPER(?)"
            if theatre_filter else ""
        )
        t_params = (theatre_filter,) if theatre_filter else ()
        result = {}
        with get_db() as conn:
            for ms in MILESTONES:
                row = conn.execute(
                    f"""
                    SELECT COUNT(DISTINCT sh.account_id) as cnt
                    FROM status_history sh
                    JOIN accounts a ON a.account_id = sh.account_id
                    LEFT JOIN blocked_data b ON b.account_id = sh.account_id
                    WHERE sh.field_name = ?
                      AND sh.new_status = 'Y'
                      AND sh.changed_at >= ?
                      AND sh.changed_at <= ?
                      {t_clause}
                    """,
                    (ms, mon_s, sun_s) + t_params,
                ).fetchone()
                cnt = row["cnt"] if row else 0
                if cnt:
                    result[ms] = cnt
        return result

    # This week — always all theatres
    this_week_by_theatre = {}
    for t in THEATRES:
        this_week_by_theatre[t] = _count_week(this_monday, t)

    sun = this_monday + timedelta(days=6)
    range_label = f"{this_monday.strftime('%b %-d')} – {sun.strftime('%b %-d')}"

    # History — N weeks ending last Sunday
    history = []
    last_monday = this_monday - timedelta(weeks=1)
    for i in range(weeks):
        w_monday = last_monday - timedelta(weeks=i)
        counts = _count_week(w_monday, theatre)
        row = {"week": _week_label(w_monday)}
        row.update(counts)
        history.append(row)

    return {
        "this_week": {
            "range": range_label,
            "by_theatre": this_week_by_theatre,
        },
        "history": history,
        "updated_at": _dt.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    }
```

Also add the HTML route immediately after the endpoint (before or after the `/weekly` HTML route):

```python
@app.get("/velocity", response_class=HTMLResponse)
def page_velocity():
    html_path = Path(__file__).parent / "static" / "velocity.html"
    if html_path.exists():
        return html_path.read_text()
    return "<h1>velocity.html not found</h1>"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_api_velocity.py -v
```

Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add tests/test_api_velocity.py dashboard.py
git commit -m "feat(velocity): add /api/velocity endpoint and /velocity route"
```

---

### Task 2: `static/velocity.html` — new page

**Files:**
- Create: `static/velocity.html`
- Modify: `static/solstice.js` — add velocity to nav

**Interfaces:**
- Consumes: `GET /api/velocity?weeks=N&theatre=X` (Task 1)
- Consumes: `S.initNav('velocity')`, `S.restoreCard()`, `S.esc()` from `solstice.js`

- [ ] **Step 1: Add velocity to nav in `solstice.js`**

In `static/solstice.js`, find the `_PAGES` array (around line 295). Insert the velocity entry between `weekly` and `scope`:

```javascript
var _PAGES = [
  {id:'ops',      label:'Ops',        url:'/ops'},
  {id:'blockers', label:'Blockers',   url:'/blockers'},
  {id:'forecast', label:'Forecast',   url:'/forecast'},
  {id:'daily',    label:'Daily',      url:'/daily'},
  {id:'audit',    label:'Audit',      url:'/audit'},
  {id:'cse',      label:'CSE',        url:'/cse'},
  {id:'weekly',   label:'Weekly',     url:'/weekly'},
  {id:'velocity', label:'Velocity',   url:'/velocity'},   // ← add this line
  {id:'scope',    label:'Scope',      url:'/scope'},
  {id:'wins',     label:'🏆 Wins',    url:'/wins'},
];
```

- [ ] **Step 2: Create `static/velocity.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>&#x2600;</text></svg>">
<title>Solstice — Velocity</title>
<link rel="stylesheet" href="/static/solstice.css">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
.vel-controls{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-bottom:1.2rem}
.vel-controls .sep{color:var(--border);padding:0 .2rem;font-size:14px;align-self:center}
.vel-refresh{margin-left:auto;display:flex;align-items:center;gap:.5rem}
.vel-ts{font-size:9px;color:var(--muted);font-family:var(--mono)}
.vel-section{margin-bottom:2rem}
.vel-section-title{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:.6rem;display:flex;align-items:center;gap:.5rem}
.vel-range{font-size:9px;color:var(--muted);font-weight:400;font-family:var(--mono)}
.vtbl{width:100%;border-collapse:collapse}
.vtbl th{padding:.4rem .7rem;font-size:8px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-family:var(--mono);font-weight:700;background:var(--surface);border-bottom:2px solid var(--border);text-align:left;white-space:nowrap}
.vtbl th.r{text-align:right}
.vtbl td{padding:.55rem .7rem;font-size:.85rem;border-bottom:1px solid var(--border-soft);color:var(--text);vertical-align:middle;font-family:var(--mono)}
.vtbl td.r{text-align:right}
.vtbl tr:hover td{background:var(--surface-2)}
.vtbl td.muted{color:var(--muted);font-size:.75rem}
.m9-val{display:inline-flex;align-items:center;justify-content:center;min-width:24px;padding:2px 6px;border-radius:4px;background:var(--sky-light);color:var(--sky);font-weight:700;border:1px solid var(--sky-border)}
.m8-val{display:inline-flex;align-items:center;justify-content:center;min-width:24px;padding:2px 6px;border-radius:4px;background:#fff7ed;color:#f97316;font-weight:700;border:1px solid #fed7aa}
.empty-state{padding:2rem;text-align:center;color:var(--muted);font-size:10px}
</style>
</head>
<body>
<nav id="s-nav" class="s-nav"></nav>
<div class="s-main">

  <div class="vel-controls">
    <!-- Theatre pills -->
    <span class="pill active" data-t="" onclick="setTheatre(this,'')">All</span>
    <span class="pill" data-t="EMEA" onclick="setTheatre(this,'EMEA')">EMEA</span>
    <span class="pill" data-t="AMER" onclick="setTheatre(this,'AMER')">AMER</span>
    <span class="pill" data-t="JAPAC" onclick="setTheatre(this,'JAPAC')">JAPAC</span>
    <span class="pill" data-t="LATAM" onclick="setTheatre(this,'LATAM')">LATAM</span>
    <span class="sep">|</span>
    <!-- Time range pills -->
    <span class="pill" data-w="4" onclick="setWeeks(this,4)">4w</span>
    <span class="pill active" data-w="12" onclick="setWeeks(this,12)">12w</span>
    <span class="pill" data-w="26" onclick="setWeeks(this,26)">26w</span>
    <span class="pill" data-w="ytd" onclick="setWeeks(this,'ytd')">YTD</span>
    <!-- Refresh -->
    <div class="vel-refresh">
      <span class="vel-ts" id="vel-ts"></span>
      <button class="pill" onclick="load()" id="vel-btn" style="border-color:var(--sky-border);color:var(--sky);background:var(--sky-light)">&#10227; Refresh Now</button>
    </div>
  </div>

  <!-- This Week -->
  <div class="vel-section">
    <div class="vel-section-title">
      This Week
      <span class="vel-range" id="vel-range"></span>
    </div>
    <div id="this-week-wrap"></div>
  </div>

  <!-- Historical -->
  <div class="vel-section">
    <div class="vel-section-title">Historical Velocity</div>
    <div id="history-wrap"></div>
  </div>

</div>
<script src="/static/solstice.js?v=2"></script>
<script>
S.initNav('velocity');
S.restoreCard();

var E = S.esc;
var _theatre = '';
var _weeks = 12;
var _loading = false;

var MILESTONES = [
  'M1 Outreach', 'M2 Entitlements', 'M3 Buy-in', 'M4 Discovery',
  'M5 Tech Validation', 'M8 Upgrade Started', 'M9 Upgrade Complete'
];
var THEATRES = ['AMER', 'EMEA', 'JAPAC', 'LATAM'];

function setTheatre(el, t) {
  _theatre = t;
  document.querySelectorAll('.vel-controls [data-t]').forEach(function(p) {
    p.classList.toggle('active', p.dataset.t === t);
  });
  load();
}

function setWeeks(el, w) {
  _weeks = w;
  document.querySelectorAll('.vel-controls [data-w]').forEach(function(p) {
    p.classList.toggle('active', p.dataset.w === String(w));
  });
  load();
}

function _weeksParam() {
  if (_weeks === 'ytd') {
    var now = new Date();
    var jan1 = new Date(now.getFullYear(), 0, 1);
    return Math.ceil((now - jan1) / (7 * 86400000)) + 1;
  }
  return _weeks;
}

function load() {
  if (_loading) return;
  _loading = true;
  var btn = document.getElementById('vel-btn');
  btn.textContent = '…';
  var url = '/api/velocity?weeks=' + _weeksParam() + (_theatre ? '&theatre=' + encodeURIComponent(_theatre) : '');
  fetch(url)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      renderThisWeek(data.this_week);
      renderHistory(data.history);
      document.getElementById('vel-ts').textContent = 'Updated ' + (data.updated_at || '').slice(0, 16).replace('T', ' ');
    })
    .catch(function() {
      document.getElementById('this-week-wrap').innerHTML = '<div class="empty-state">Error loading data</div>';
    })
    .finally(function() {
      _loading = false;
      btn.textContent = '↺ Refresh Now';
    });
}

function _cell(ms, val) {
  if (!val) return '<td class="r muted">—</td>';
  if (ms === 'M9 Upgrade Complete') return '<td class="r"><span class="m9-val">' + val + '</span></td>';
  if (ms === 'M8 Upgrade Started')  return '<td class="r"><span class="m8-val">' + val + '</span></td>';
  return '<td class="r">' + val + '</td>';
}

function renderThisWeek(tw) {
  document.getElementById('vel-range').textContent = tw.range || '';
  var by = tw.by_theatre || {};
  var hasAny = false;
  var html = '<table class="vtbl"><thead><tr><th>Milestone</th>';
  THEATRES.forEach(function(t) { html += '<th class="r">' + t + '</th>'; });
  html += '</tr></thead><tbody>';
  MILESTONES.forEach(function(ms) {
    var rowHasVal = THEATRES.some(function(t) { return (by[t] || {})[ms]; });
    if (!rowHasVal) return;
    hasAny = true;
    html += '<tr><td>' + E(ms) + '</td>';
    THEATRES.forEach(function(t) { html += _cell(ms, (by[t] || {})[ms]); });
    html += '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById('this-week-wrap').innerHTML = hasAny
    ? html
    : '<div class="empty-state">No milestone activity this week</div>';
}

function renderHistory(history) {
  if (!history || !history.length) {
    document.getElementById('history-wrap').innerHTML = '<div class="empty-state">No data for this period</div>';
    return;
  }
  // Determine which milestones have any non-zero value
  var activeMilestones = MILESTONES.filter(function(ms) {
    return history.some(function(row) { return row[ms]; });
  });
  if (!activeMilestones.length) {
    document.getElementById('history-wrap').innerHTML = '<div class="empty-state">No data for this period</div>';
    return;
  }
  var html = '<table class="vtbl"><thead><tr><th>Milestone</th>';
  history.forEach(function(row) { html += '<th class="r">' + E(row.week) + '</th>'; });
  html += '</tr></thead><tbody>';
  activeMilestones.forEach(function(ms) {
    html += '<tr><td>' + E(ms) + '</td>';
    history.forEach(function(row) { html += _cell(ms, row[ms]); });
    html += '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById('history-wrap').innerHTML = html;
}

load();
</script>
</body>
</html>
```

- [ ] **Step 3: Rebuild container and smoke-test manually**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
docker compose up -d --build 2>&1 | tail -3
sleep 5
curl -s "http://localhost:8200/api/velocity?weeks=4" | python3 -c "import sys,json; d=json.load(sys.stdin); print('theatres:', list(d['this_week']['by_theatre'].keys())); print('history rows:', len(d['history'])); print('updated_at:', d['updated_at'])"
```

Expected output:
```
theatres: ['AMER', 'EMEA', 'JAPAC', 'LATAM']
history rows: 4
updated_at: 2026-...
```

Then open `http://localhost:8200/velocity` in browser and verify:
- Nav shows "Velocity" between Weekly and Scope
- "This Week" grid renders with theatre columns
- "Historical Velocity" table shows weeks as columns
- Clicking theatre pills filters history
- Clicking time range pills changes column count
- Refresh Now button re-fetches and updates timestamp

- [ ] **Step 4: Commit**

```bash
git add static/velocity.html static/solstice.js
git commit -m "feat(velocity): add velocity page with this-week grid and history table"
```

---

### Task 3: Run full test suite and push

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
python3 -m pytest tests/ -q 2>&1 | tail -10
```

Expected: all existing tests pass + 5 new velocity tests pass. No regressions.

- [ ] **Step 2: Push**

```bash
git push
```
