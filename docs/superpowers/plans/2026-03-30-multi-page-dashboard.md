# Multi-Page Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the single long /v2 dashboard into 5 focused pages: /ops (cleaned-up current), /blockers (call prep), /forecast (velocity + next week), /daily (existing), /audit (extracted history).

**Architecture:** Each page is a standalone HTML file served by FastAPI. New API endpoints (/api/blockers, /api/forecast) added to dashboard.py. Shared nav bar component inlined into each page. Theatre/CSE filters wire to the same _theatre global pattern used in v2.html.

**Tech Stack:** FastAPI, vanilla JS, SQLite, existing dashboard.py data layer, no new dependencies.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `static/blockers.html` | /blockers page — blocker review call prep |
| Create | `static/forecast.html` | /forecast page — velocity + next week targets |
| Create | `static/audit.html` | /audit page — full change history |
| Modify | `static/v2.html` | Remove audit section, add nav links to all pages |
| Modify | `dashboard.py` | Add routes + /api/blockers + /api/forecast APIs |

---

## Task 1: `/api/blockers` endpoint

**Files:**
- Modify: `dashboard.py` (add after existing API endpoints, around line 1080)

- [ ] **Step 1: Add the endpoint**

Find the line `@app.get("/api/dq")` in dashboard.py and add BEFORE it:

```python
@app.get("/api/blockers")
def api_blockers(theatre: str = "", region: str = "", cse: str = ""):
    """Blocked accounts grouped by blocker type for call prep."""
    _ensure_db()
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT a.customer_name, a.active_cse, a.sales_region,
                       COALESCE(a.account_theatre,'EMEA') as account_theatre,
                       b.signal, b.subtype, b.status_detail, b.upgrade_notes,
                       b.health_notes, b.dc_progress, b.churn_risk,
                       b.cc_rep, b.cc_dsm, b.cohort, b.area, b.district,
                       b.m8_started, b.m9_complete, b.m3_complete
                FROM accounts a JOIN blocked_data b ON a.account_id=b.account_id
                WHERE a.customer_name != ''
                  AND b.signal IN ('blocked','at_risk')
                  AND b.m9_complete = 0
                  AND (? = '' OR UPPER(COALESCE(a.account_theatre,'EMEA'))=UPPER(?))
                  AND (? = '' OR LOWER(a.sales_region) LIKE LOWER(?))
                  AND (? = '' OR a.active_cse = ?)
                ORDER BY b.subtype, a.sales_region, a.customer_name
            """, (theatre, theatre,
                  region, f"%{region}%",
                  cse, cse)).fetchall()
        result = {"no_contact": [], "core_rep_blocking": [], "tech_blocker": [], "active_deal": [], "other": []}
        for r in rows:
            d = dict(r)
            st = d.get("subtype") or "other"
            bucket = st if st in result else "other"
            result[bucket].append(d)
        return result
    except Exception as e:
        return {"error": str(e)}
```

- [ ] **Step 2: Test the endpoint**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
curl -s "http://localhost:8200/api/blockers?theatre=EMEA" | python3 -c "
import json,sys; d=json.load(sys.stdin)
for k,v in d.items(): print(f'{k}: {len(v)}')
"
```
Expected output (approximately):
```
no_contact: 61
core_rep_blocking: 22
tech_blocker: 9
active_deal: 2
other: 0
```

- [ ] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "feat: /api/blockers endpoint — grouped by subtype with theatre/region/cse filters"
```

---

## Task 2: `/api/forecast` endpoint

**Files:**
- Modify: `dashboard.py` (add after /api/blockers)

- [ ] **Step 1: Add the endpoint**

Add immediately after the `/api/blockers` endpoint:

```python
@app.get("/api/forecast")
def api_forecast(theatre: str = ""):
    """Next 7 days M8/M9 targets + 4-week velocity."""
    _ensure_db()
    from datetime import datetime, timedelta
    today = datetime.utcnow().date()
    next_week_end = today + timedelta(days=7)

    try:
        with get_db() as conn:
            # Next 7 days targets
            targets = conn.execute("""
                SELECT a.customer_name, a.active_cse, a.sales_region,
                       COALESCE(a.account_theatre,'EMEA') as account_theatre,
                       b.m9_planned, b.m8_planned, b.m8_started, b.m9_complete,
                       b.dc_progress, b.churn_risk, b.m8_actual
                FROM accounts a JOIN blocked_data b ON a.account_id=b.account_id
                WHERE a.customer_name != '' AND b.m9_complete=0
                  AND (? = '' OR UPPER(COALESCE(a.account_theatre,'EMEA'))=UPPER(?))
                ORDER BY b.m9_planned
            """, (theatre, theatre)).fetchall()

            # 4-week velocity: M9 completions per week
            velocity = []
            for w in range(3, -1, -1):
                week_start = (today - timedelta(days=today.weekday()) - timedelta(weeks=w))
                week_end = week_start + timedelta(days=6)
                n = conn.execute("""
                    SELECT COUNT(*) FROM status_history sh
                    LEFT JOIN accounts a ON a.account_id=sh.account_id
                    WHERE sh.field_name='M9 Upgrade Complete'
                      AND sh.new_status='Y'
                      AND sh.source IN ('pipeline','backfill')
                      AND date(sh.changed_at) BETWEEN ? AND ?
                      AND (? = '' OR UPPER(COALESCE(a.account_theatre,'EMEA'))=UPPER(?))
                """, (str(week_start), str(week_end), theatre, theatre)).fetchone()[0]
                velocity.append({"week_start": str(week_start), "week_end": str(week_end), "m9_count": n,
                                 "label": week_start.strftime("%d %b")})

        def parse_date(s):
            if not s: return None
            for f in ('%m/%d/%Y','%Y-%m-%d','%m/%d/%Y %H:%M:%S'):
                try:
                    from datetime import datetime as dt
                    return dt.strptime(s.strip().split(' ')[0], f).date()
                except: pass
            return None

        next_targets = []
        overdue = []
        for r in targets:
            d = dict(r)
            m9d = parse_date(d.get('m9_planned'))
            if not m9d: continue
            confidence = "HIGH" if d['m8_started'] and d['dc_progress']=='Green' else \
                         "MED" if d['m8_started'] else "LOW"
            d['confidence'] = confidence
            d['m9_date'] = str(m9d)
            if m9d < today:
                d['status'] = 'overdue'
                overdue.append(d)
            elif m9d <= next_week_end:
                d['status'] = 'upcoming'
                next_targets.append(d)

        # Velocity trend direction
        counts = [v['m9_count'] for v in velocity]
        trend = "up" if counts[-1] > counts[0] else "down" if counts[-1] < counts[0] else "flat"

        return {"next_targets": next_targets, "overdue": overdue,
                "velocity": velocity, "trend": trend}
    except Exception as e:
        return {"error": str(e)}
```

- [ ] **Step 2: Test the endpoint**

```bash
curl -s "http://localhost:8200/api/forecast" | python3 -c "
import json,sys; d=json.load(sys.stdin)
print('Next targets:', len(d['next_targets']))
print('Overdue:', len(d['overdue']))
print('Velocity:', [(v['label'],v['m9_count']) for v in d['velocity']])
print('Trend:', d['trend'])
"
```

- [ ] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "feat: /api/forecast endpoint — next 7 days M8/M9 targets + 4-week velocity"
```

---

## Task 3: Add routes for all new pages

**Files:**
- Modify: `dashboard.py` (find the `/daily` route section, add after it)

- [ ] **Step 1: Add three new routes**

Find `@app.get("/daily",response_class=HTMLResponse)` and add AFTER that block:

```python
@app.get("/blockers",response_class=HTMLResponse)
def page_blockers():
    html_path = Path(__file__).parent / "static" / "blockers.html"
    if html_path.exists(): return html_path.read_text()
    return "<h1>blockers page not found</h1>"

@app.get("/forecast",response_class=HTMLResponse)
def page_forecast():
    html_path = Path(__file__).parent / "static" / "forecast.html"
    if html_path.exists(): return html_path.read_text()
    return "<h1>forecast page not found</h1>"

@app.get("/audit",response_class=HTMLResponse)
def page_audit():
    html_path = Path(__file__).parent / "static" / "audit.html"
    if html_path.exists(): return html_path.read_text()
    return "<h1>audit page not found</h1>"
```

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import py_compile; py_compile.compile('dashboard.py'); print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "feat: add routes /blockers /forecast /audit"
```

---

## Task 4: Shared nav component (inline snippet)

This is a JS string used in every page. Define it once per page (no external file — keeps pages self-contained).

The nav HTML to embed at the top of each new page:

```html
<nav style="background:#161B22;border-bottom:1px solid #21262D;padding:.6rem 1.5rem;display:flex;align-items:center;gap:.25rem;position:sticky;top:0;z-index:100">
  <span style="font-weight:800;font-size:12px;color:#14B8A6;letter-spacing:.05em;margin-right:1rem">SOLSTICE</span>
  <a href="/ops" class="nav-link" data-page="ops">Ops</a>
  <a href="/blockers" class="nav-link" data-page="blockers">Blockers</a>
  <a href="/forecast" class="nav-link" data-page="forecast">Forecast</a>
  <a href="/daily" class="nav-link" data-page="daily">Daily</a>
  <a href="/audit" class="nav-link" data-page="audit">Audit</a>
</nav>
```

CSS for nav links (embed in `<style>` of each page):
```css
.nav-link{font-size:10.5px;color:#8B949E;text-decoration:none;padding:4px 12px;border-radius:5px;border:1px solid transparent;transition:all .15s}
.nav-link:hover{background:rgba(255,255,255,.05);color:#E6EDF3}
.nav-link.active{color:#E6EDF3;background:rgba(255,255,255,.08);border-color:#21262D}
```

JS to auto-highlight current page (embed in `<script>` of each page):
```javascript
document.querySelectorAll('.nav-link').forEach(function(a){
  if(window.location.pathname===a.getAttribute('href'))a.classList.add('active');
});
```

Also add `/ops` as an alias for `/v2`:

In `dashboard.py`, find `@app.get("/v2"...)` and add before it:
```python
@app.get("/ops",response_class=HTMLResponse)
def dashboard_ops():
    return dashboard_v2()  # same page, cleaner URL
```

- [ ] **Step: Commit the ops alias**

```bash
git add dashboard.py
git commit -m "feat: /ops alias for /v2 — cleaner URL"
```

---

## Task 5: Build `/blockers` page

**Files:**
- Create: `static/blockers.html`

- [ ] **Step 1: Create the file**

Create `static/blockers.html` with this complete content:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Solstice — Blocker Review</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0D1117;--card:#161B22;--border:#21262D;--text:#E6EDF3;--muted:#8B949E;--teal:#14B8A6;--red:#EF4444;--amber:#F59E0B;--green:#22C55E;--mono:'Geist Mono',monospace}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh}
.nav-link{font-size:10.5px;color:var(--muted);text-decoration:none;padding:4px 12px;border-radius:5px;border:1px solid transparent;transition:all .15s}
.nav-link:hover{background:rgba(255,255,255,.05);color:var(--text)}
.nav-link.active{color:var(--text);background:rgba(255,255,255,.08);border-color:var(--border)}
.page{max-width:1160px;margin:0 auto;padding:1.25rem 1.5rem}
/* Filters */
.fbar{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-bottom:1rem}
.fpill{font-size:8.5px;font-weight:700;letter-spacing:.07em;padding:4px 11px;border-radius:20px;cursor:pointer;border:1px solid var(--border);color:var(--muted);background:transparent;transition:all .15s}
.fpill:hover{border-color:#30363D;color:var(--text)}
.fpill.act-emea{border-color:var(--teal);color:var(--teal);background:rgba(20,184,166,.08)}
.fpill.act-amer{border-color:#3B82F6;color:#3B82F6;background:rgba(59,130,246,.08)}
.fpill.act-japac{border-color:#8B5CF6;color:#8B5CF6;background:rgba(139,92,246,.08)}
.fpill.act-latam{border-color:var(--amber);color:var(--amber);background:rgba(245,158,11,.08)}
select.fsel{background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--muted);font-size:9px;padding:5px 8px;font-family:var(--mono)}
input.fsearch{background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:9px;padding:5px 10px;outline:none;min-width:180px}
/* Summary */
.sumbar{display:flex;gap:.6rem;margin-bottom:1.1rem;flex-wrap:wrap}
.schip{font-size:9px;font-weight:600;padding:3px 10px;border-radius:4px;cursor:pointer}
/* Section */
.bsec{margin-bottom:1.25rem}
.shdr{display:flex;align-items:center;gap:.6rem;padding:.5rem .8rem;background:var(--card);border:1px solid var(--border);border-radius:8px 8px 0 0;cursor:pointer;user-select:none}
.shdr:hover{background:#1C2128}
.shdr .ico{font-size:13px;width:18px;text-align:center}
.shdr h3{font-size:11px;font-weight:700}
.shdr .cnt{font-size:9px;color:var(--muted)}
.shdr .chev{margin-left:auto;color:var(--muted);font-size:10px;transition:transform .2s}
.sbody{border:1px solid var(--border);border-top:none;border-radius:0 0 8px 8px;overflow:hidden}
.sbody.col{display:none}
.shdr.open .chev{transform:rotate(180deg)}
/* Region group */
.rghdr{padding:.3rem .8rem;background:var(--bg);border-bottom:1px solid rgba(33,38,45,.5);display:flex;align-items:center;gap:.5rem}
.rghdr span{font-size:8px;text-transform:uppercase;letter-spacing:.1em;color:#484F58;font-weight:700}
.rghdr .rc{font-size:8px;color:#30363D}
/* Table */
.thdr{display:grid;grid-template-columns:2fr 1.3fr 1fr 2.5fr;background:var(--bg);border-bottom:1px solid var(--border)}
.thdr span{padding:.28rem .7rem;font-size:7.5px;text-transform:uppercase;letter-spacing:.09em;color:#484F58;font-weight:700;border-right:1px solid rgba(33,38,45,.4)}
.thdr span:last-child{border-right:none}
.arow{display:grid;grid-template-columns:2fr 1.3fr 1fr 2.5fr;border-bottom:1px solid rgba(33,38,45,.4);align-items:stretch}
.arow:last-child{border-bottom:none}
.arow:hover{background:rgba(255,255,255,.015)}
.ac{padding:.5rem .7rem;font-size:9.5px;border-right:1px solid rgba(33,38,45,.3)}
.ac:last-child{border-right:none}
.aname{font-weight:700;font-size:10px;margin-bottom:2px}
.asub{font-size:8.5px;color:var(--muted)}
.chip{display:inline-flex;align-items:center;gap:3px;background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:3px;padding:2px 6px;font-size:8px;color:var(--muted);margin-bottom:2px}
.chip .role{font-size:7px;color:#484F58;font-weight:700}
.notes{font-size:8.5px;color:#6E7681;line-height:1.45}
.dcdot{display:inline-block;width:7px;height:7px;border-radius:50%;vertical-align:middle;margin-right:2px}
.empty{padding:1.5rem;text-align:center;color:var(--muted);font-size:10px}
</style>
</head>
<body>
<nav style="background:#161B22;border-bottom:1px solid #21262D;padding:.6rem 1.5rem;display:flex;align-items:center;gap:.25rem;position:sticky;top:0;z-index:100">
  <span style="font-weight:800;font-size:12px;color:#14B8A6;letter-spacing:.05em;margin-right:1rem">SOLSTICE</span>
  <a href="/ops" class="nav-link">Ops</a>
  <a href="/blockers" class="nav-link">Blockers</a>
  <a href="/forecast" class="nav-link">Forecast</a>
  <a href="/daily" class="nav-link">Daily</a>
  <a href="/audit" class="nav-link">Audit</a>
</nav>

<div class="page">
  <div class="fbar">
    <span class="fpill" data-t="" onclick="setT(this,'')">All</span>
    <span class="fpill" data-t="EMEA" onclick="setT(this,'EMEA')">EMEA</span>
    <span class="fpill" data-t="AMER" onclick="setT(this,'AMER')">AMER/NAM</span>
    <span class="fpill" data-t="JAPAC" onclick="setT(this,'JAPAC')">JAPAC</span>
    <span class="fpill" data-t="LATAM" onclick="setT(this,'LATAM')">LATAM</span>
    <span style="color:var(--border);margin:0 .1rem">|</span>
    <select class="fsel" id="f-region" onchange="load()"><option value="">All Regions</option></select>
    <select class="fsel" id="f-cse" onchange="load()"><option value="">All CSEs</option></select>
    <input class="fsearch" id="f-search" placeholder="Search account…" oninput="render()">
  </div>
  <div class="sumbar" id="sumbar"></div>
  <div id="sections"></div>
</div>

<script>
var E=function(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');};
var _t='',_data={};
var TYPES=[
  {key:'no_contact',     icon:'🛑',label:'No Internal Kickoff',     desc:'Not able to contact NGS Sales Specialist'},
  {key:'core_rep_blocking',icon:'👎',label:'Blocked by Account Team',desc:'Rep asked CSE to hold'},
  {key:'tech_blocker',   icon:'⚙',label:'Technical Blocker',       desc:'CoE / product gap'},
  {key:'active_deal',    icon:'💼',label:'Active Deal',             desc:'XSIAM or other deal in flight'},
  {key:'other',          icon:'•', label:'Other',                   desc:'Other blockers'},
];
var DC_C={'Green':'#22C55E','Yellow':'#F59E0B','Red':'#EF4444'};

function setT(el,t){
  _t=t;
  document.querySelectorAll('.fpill').forEach(function(p){
    p.className='fpill';
    if(p.dataset.t===t){
      var cls={'EMEA':'act-emea','AMER':'act-amer','JAPAC':'act-japac','LATAM':'act-latam','':''}[t];
      p.className='fpill '+(cls||'act-emea');
    }
  });
  load();
}

function load(){
  var region=document.getElementById('f-region').value;
  var cse=document.getElementById('f-cse').value;
  var url='/api/blockers?theatre='+encodeURIComponent(_t)+'&region='+encodeURIComponent(region)+'&cse='+encodeURIComponent(cse);
  fetch(url).then(r=>r.json()).then(function(d){
    _data=d;
    // Populate CSE filter
    var cses={};
    TYPES.forEach(function(t){(d[t.key]||[]).forEach(function(a){if(a.active_cse)cses[a.active_cse]=1;});});
    var cEl=document.getElementById('f-cse');
    var cur=cEl.value;
    cEl.innerHTML='<option value="">All CSEs</option>';
    Object.keys(cses).sort().forEach(function(c){var o=document.createElement('option');o.value=c;o.textContent=c;if(c===cur)o.selected=true;cEl.appendChild(o);});
    render();
  }).catch(function(e){document.getElementById('sections').innerHTML='<div class="empty">Error loading data</div>';});
}

function render(){
  var q=(document.getElementById('f-search').value||'').toLowerCase();
  var total=0;
  var sumHtml='';
  var secHtml='';
  TYPES.forEach(function(type){
    var items=(_data[type.key]||[]).filter(function(a){
      return !q||(a.customer_name||'').toLowerCase().includes(q)||(a.active_cse||'').toLowerCase().includes(q);
    });
    if(!items.length)return;
    total+=items.length;
    sumHtml+='<span class="schip" style="background:rgba(255,255,255,.04);border:1px solid var(--border);color:var(--muted)">'+type.icon+' '+type.label+': <b style="color:var(--text)">'+items.length+'</b></span>';
    // Group by region
    var byReg={};var regOrder=[];
    items.forEach(function(a){var r=a.sales_region||'—';if(!byReg[r]){byReg[r]=[];regOrder.push(r);}byReg[r].push(a);});
    var bodyHtml='<div class="thdr"><span>Account</span><span>Rep / DSM</span><span>CSE · DC</span><span>Notes</span></div>';
    regOrder.forEach(function(reg){
      bodyHtml+='<div class="rghdr"><span>'+E(reg)+'</span><span class="rc">'+byReg[reg].length+'</span></div>';
      byReg[reg].forEach(function(a){
        var dc=a.dc_progress||'—';
        var dcc=DC_C[dc]||'var(--muted)';
        var rep=a.cc_rep&&a.cc_rep!=='-'?'<div class="chip"><span class="role">REP</span>'+E(a.cc_rep)+'</div>':'';
        var dsm=a.cc_dsm&&a.cc_dsm!=='-'?'<div class="chip"><span class="role">DSM</span>'+E(a.cc_dsm)+'</div>':'<div style="font-size:8px;color:#484F58">No DSM</div>';
        var notes=E((a.upgrade_notes||a.health_notes||a.status_detail||'—').substring(0,160));
        bodyHtml+='<div class="arow">'
          +'<div class="ac"><div class="aname">'+E(a.customer_name)+'</div><div class="asub">'+E(a.active_cse||'—')+'</div></div>'
          +'<div class="ac">'+rep+dsm+'</div>'
          +'<div class="ac"><div class="asub" style="margin-bottom:3px">'+E(a.active_cse||'—')+'</div><div><span class="dcdot" style="background:'+dcc+'"></span><span style="font-size:8.5px;color:'+dcc+'">'+E(dc)+'</span></div></div>'
          +'<div class="ac"><div class="notes">'+notes+'</div></div>'
          +'</div>';
      });
    });
    secHtml+='<div class="bsec">'
      +'<div class="shdr open" onclick="toggleSec(this)"><span class="ico">'+type.icon+'</span><h3>'+E(type.label)+'</h3><span class="cnt">'+items.length+' accounts — '+E(type.desc)+'</span><span class="chev">▾</span></div>'
      +'<div class="sbody">'+bodyHtml+'</div>'
      +'</div>';
  });
  document.getElementById('sumbar').innerHTML=sumHtml+(total?'<span class="schip" style="color:var(--muted);font-size:9px">Total: '+total+'</span>':'');
  document.getElementById('sections').innerHTML=secHtml||'<div class="empty">No blocked accounts match current filters</div>';
}

function toggleSec(hdr){
  hdr.classList.toggle('open');
  hdr.nextElementSibling.classList.toggle('col');
}

document.querySelectorAll('.nav-link').forEach(function(a){if(window.location.pathname===a.getAttribute('href'))a.classList.add('active');});
load();
</script>
</body>
</html>
```

- [ ] **Step 2: Test it**

```bash
# Restart server
kill $(ps aux | grep "dashboard.py" | grep -v grep | awk '{print $2}') 2>/dev/null
sleep 1 && nohup python3 dashboard.py > /tmp/solstice.log 2>&1 &
sleep 3
curl -s -o /dev/null -w "%{http_code}" http://localhost:8200/blockers
```
Expected: `200`

Open `http://localhost:8200/blockers` — should show theatre pills, blocker sections, account rows.

- [ ] **Step 3: Commit**

```bash
git add static/blockers.html
git commit -m "feat: /blockers page — account-by-account blocker review with theatre/region/CSE filters"
```

---

## Task 6: Build `/forecast` page

**Files:**
- Create: `static/forecast.html`

- [ ] **Step 1: Create the file**

Create `static/forecast.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Solstice — Velocity & Forecast</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0D1117;--card:#161B22;--border:#21262D;--text:#E6EDF3;--muted:#8B949E;--teal:#14B8A6;--green:#22C55E;--amber:#F59E0B;--red:#EF4444;--mono:'Geist Mono',monospace}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.nav-link{font-size:10.5px;color:var(--muted);text-decoration:none;padding:4px 12px;border-radius:5px;border:1px solid transparent}
.nav-link:hover{background:rgba(255,255,255,.05);color:var(--text)}
.nav-link.active{color:var(--text);background:rgba(255,255,255,.08);border-color:var(--border)}
.page{max-width:1100px;margin:0 auto;padding:1.25rem 1.5rem;display:grid;grid-template-columns:1fr 320px;gap:1.25rem;align-items:start}
@media(max-width:800px){.page{grid-template-columns:1fr}}
.left,.right{display:flex;flex-direction:column;gap:1.1rem}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;overflow:hidden}
.card-hdr{padding:.6rem 1rem;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.card-hdr h3{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.card-hdr .sub{font-size:9px;color:#484F58}
/* Theatre pills */
.tpills{padding:.5rem 1rem;display:flex;gap:.4rem;border-bottom:1px solid var(--border);flex-wrap:wrap}
.tpill{font-size:8.5px;padding:3px 9px;border-radius:12px;cursor:pointer;border:1px solid var(--border);color:var(--muted)}
.tpill.act{border-color:var(--green);color:var(--green);background:rgba(34,197,94,.08)}
/* Forecast table */
.ft-hdr{display:grid;grid-template-columns:16px 2fr .8fr .8fr .7fr .8fr;background:var(--bg);border-bottom:1px solid var(--border)}
.ft-hdr span{padding:.28rem .5rem;font-size:7.5px;text-transform:uppercase;letter-spacing:.09em;color:#484F58;font-weight:700;border-right:1px solid rgba(33,38,45,.4)}
.ft-hdr span:last-child{border-right:none}
.ftrow{display:grid;grid-template-columns:16px 2fr .8fr .8fr .7fr .8fr;border-bottom:1px solid rgba(33,38,45,.4);align-items:center}
.ftrow:last-child{border-bottom:none}
.ftrow:hover{background:rgba(255,255,255,.015)}
.fc{padding:.45rem .5rem;font-size:9.5px}
.conf{display:inline-flex;align-items:center;font-size:8px;font-weight:700;padding:2px 6px;border-radius:3px}
.conf-high{background:rgba(34,197,94,.12);color:var(--green)}
.conf-med{background:rgba(245,158,11,.12);color:var(--amber)}
.conf-low{background:rgba(239,68,68,.12);color:var(--red)}
.tag{font-size:7px;font-weight:700;padding:1px 5px;border-radius:2px}
.tag-emea{background:rgba(20,184,166,.1);color:var(--teal)}
.tag-amer{background:rgba(59,130,246,.1);color:#3B82F6}
.tag-japac{background:rgba(139,92,246,.1);color:#8B5CF6}
.tag-latam{background:rgba(245,158,11,.1);color:var(--amber)}
.tag-other{background:rgba(139,148,158,.1);color:var(--muted)}
.dcdot{display:inline-block;width:7px;height:7px;border-radius:50%;vertical-align:middle;margin-right:2px}
.overdue-banner{padding:.4rem 1rem;background:rgba(239,68,68,.06);border-top:1px solid rgba(239,68,68,.12);font-size:9px;color:var(--red)}
/* Velocity */
.vel-grid{display:grid;grid-template-columns:repeat(4,1fr)}
.vel-w{padding:.75rem;text-align:center;border-right:1px solid var(--border);position:relative}
.vel-w:last-child{border-right:none}
.vel-w.cur{background:rgba(34,197,94,.04)}
.wlbl{font-size:8px;font-family:var(--mono);color:#484F58;margin-bottom:.3rem}
.wnum{font-size:26px;font-weight:700;line-height:1;margin-bottom:2px}
.wsub{font-size:8px;color:var(--muted)}
.varr{font-size:12px;position:absolute;top:8px;right:8px}
.trend-footer{padding:.4rem 1rem;font-size:9.5px;font-weight:600;border-top:1px solid var(--border);text-align:center}
/* Theatre tiles */
.th-grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--border)}
.th-tile{background:var(--card);padding:.65rem 1rem}
.th-name{font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#484F58;margin-bottom:.4rem}
.th-nums{display:flex;gap:.75rem}
.th-big{font-size:20px;font-weight:700;line-height:1}
.th-sub{font-size:8px;color:var(--muted);margin-top:1px}
.empty{padding:1.5rem;text-align:center;color:var(--muted);font-size:10px}
</style>
</head>
<body>
<nav style="background:#161B22;border-bottom:1px solid #21262D;padding:.6rem 1.5rem;display:flex;align-items:center;gap:.25rem;position:sticky;top:0;z-index:100">
  <span style="font-weight:800;font-size:12px;color:#14B8A6;letter-spacing:.05em;margin-right:1rem">SOLSTICE</span>
  <a href="/ops" class="nav-link">Ops</a>
  <a href="/blockers" class="nav-link">Blockers</a>
  <a href="/forecast" class="nav-link">Forecast</a>
  <a href="/daily" class="nav-link">Daily</a>
  <a href="/audit" class="nav-link">Audit</a>
</nav>

<div class="page">
<div class="left">
  <!-- NEXT WEEK TARGETS -->
  <div class="card">
    <div class="card-hdr"><h3>Next 7 Days — M8 + M9 Targets</h3><span class="sub" id="date-range">—</span></div>
    <div class="tpills">
      <span class="tpill act" data-t="" onclick="setT(this,'')">All Theatres</span>
      <span class="tpill" data-t="EMEA" onclick="setT(this,'EMEA')">EMEA</span>
      <span class="tpill" data-t="AMER" onclick="setT(this,'AMER')">AMER</span>
      <span class="tpill" data-t="JAPAC" onclick="setT(this,'JAPAC')">JAPAC</span>
      <span class="tpill" data-t="LATAM" onclick="setT(this,'LATAM')">LATAM</span>
    </div>
    <div class="ft-hdr">
      <span></span><span>Account</span><span>Date</span><span>Theatre</span><span>DC</span><span>Confidence</span>
    </div>
    <div id="forecast-body"></div>
  </div>

  <!-- VELOCITY -->
  <div class="card">
    <div class="card-hdr"><h3>4-Week M9 Velocity</h3><span class="sub" id="theatre-label">All Theatres</span></div>
    <div class="vel-grid" id="vel-grid"></div>
    <div class="trend-footer" id="trend-footer">—</div>
  </div>
</div>

<div class="right">
  <!-- THEATRE BREAKDOWN -->
  <div class="card">
    <div class="card-hdr"><h3>Next Week by Theatre</h3><span class="sub">M9 targets</span></div>
    <div class="th-grid" id="th-tiles"></div>
  </div>

  <!-- CONFIDENCE LEGEND -->
  <div class="card">
    <div class="card-hdr"><h3>Confidence Logic</h3></div>
    <div style="padding:.75rem 1rem;font-size:9px;color:var(--muted);line-height:1.7">
      <div style="margin-bottom:.4rem"><span class="conf conf-high" style="margin-right:.4rem">HIGH</span>M8 active + DC Green</div>
      <div style="margin-bottom:.4rem"><span class="conf conf-med" style="margin-right:.4rem">MED</span>M8 active + DC Yellow or Red</div>
      <div><span class="conf conf-low" style="margin-right:.4rem">LOW</span>M8 not started or DC Red</div>
    </div>
  </div>
</div>
</div>

<script>
var E=function(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');};
var _t='',_raw={};
var DC_C={'Green':'#22C55E','Yellow':'#F59E0B','Red':'#EF4444'};
var TH_COLS={'EMEA':'#14B8A6','AMER':'#3B82F6','JAPAC':'#8B5CF6','LATAM':'#F59E0B'};

function setT(el,t){
  _t=t;
  document.querySelectorAll('.tpill').forEach(function(p){p.classList.remove('act');});
  el.classList.add('act');
  document.getElementById('theatre-label').textContent=t||'All Theatres';
  load();
}

function load(){
  fetch('/api/forecast?theatre='+encodeURIComponent(_t)).then(r=>r.json()).then(function(d){
    _raw=d;
    renderForecast(d);
    renderVelocity(d);
    renderTheatreTiles(d);
  }).catch(function(){document.getElementById('forecast-body').innerHTML='<div class="empty">Error loading</div>';});
}

function fmtDate(s){
  if(!s) return '—';
  var p=s.split('-');
  if(p.length===3){var months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];return p[2]+' '+(months[parseInt(p[1])-1]||p[1]);}
  return s;
}

function renderForecast(d){
  var targets=(d.next_targets||[]);
  var overdue=(d.overdue||[]);
  var html='';

  // Sort: M9 first then M8, then by date
  targets.sort(function(a,b){
    var am=a.m9_complete?0:a.m8_started?1:2;
    var bm=b.m9_complete?0:b.m8_started?1:2;
    if(am!==bm)return am-bm;
    return (a.m9_date||'').localeCompare(b.m9_date||'');
  });

  if(!targets.length&&!overdue.length){html='<div class="empty">No targets in next 7 days</div>';}
  else {
    targets.forEach(function(a){
      var isM9=!a.m9_complete&&a.m8_started;
      var col=isM9?'var(--green)':'var(--teal)';
      var label=isM9?'M9':'M8';
      var dc=a.dc_progress||'—';
      var dcc=DC_C[dc]||'var(--muted)';
      var conf=a.confidence||'LOW';
      var cclass={'HIGH':'conf-high','MED':'conf-med','LOW':'conf-low'}[conf]||'conf-low';
      var th=a.account_theatre||'';
      var thcol=TH_COLS[th]||'var(--muted)';
      html+='<div class="ftrow">'
        +'<div class="fc" style="color:'+col+';font-size:10px;text-align:center;font-weight:700">'+label+'</div>'
        +'<div class="fc"><b>'+E(a.customer_name)+'</b><div style="font-size:8px;color:var(--muted)">'+E(a.active_cse||'—')+'</div></div>'
        +'<div class="fc" style="font-family:var(--mono);font-size:8.5px;color:var(--muted)">'+fmtDate(a.m9_date)+'</div>'
        +'<div class="fc"><span class="tag" style="background:'+thcol+'18;color:'+thcol+'">'+E(th)+'</span></div>'
        +'<div class="fc"><span class="dcdot" style="background:'+dcc+'"></span><span style="font-size:8.5px;color:'+dcc+'">'+E(dc)+'</span></div>'
        +'<div class="fc"><span class="conf '+cclass+'">'+conf+'</span></div>'
        +'</div>';
    });

    if(overdue.length){
      html+='<div class="overdue-banner">⚠ '+overdue.length+' overdue: '
        +overdue.slice(0,3).map(function(a){return E(a.customer_name);}).join(', ')
        +(overdue.length>3?' + '+(overdue.length-3)+' more':'')+'</div>';
    }
  }
  document.getElementById('forecast-body').innerHTML=html;
  // Date range label
  var now=new Date();
  var end=new Date(now); end.setDate(end.getDate()+7);
  var months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  document.getElementById('date-range').textContent=now.getDate()+' '+months[now.getMonth()]+' – '+end.getDate()+' '+months[end.getMonth()];
}

function renderVelocity(d){
  var vel=d.velocity||[];
  var max=Math.max(1,Math.max.apply(null,vel.map(function(v){return v.m9_count;})));
  var html='';
  vel.forEach(function(v,i){
    var isCur=(i===vel.length-1);
    var prev=i>0?vel[i-1].m9_count:null;
    var arr=prev===null?'':v.m9_count>prev?'↑':v.m9_count<prev?'↓':'';
    var arrc=arr==='↑'?'#22C55E':arr==='↓'?'#EF4444':'var(--muted)';
    html+='<div class="vel-w'+(isCur?' cur':'')+'">'
      +'<div class="wlbl">'+E(v.label)+'</div>'
      +'<div class="wnum" style="color:'+(isCur?'#22C55E':'var(--muted)')+'">'+v.m9_count+'</div>'
      +'<div class="wsub">M9 done</div>'
      +(arr?'<span class="varr" style="color:'+arrc+'">'+arr+'</span>':'')
      +'</div>';
  });
  document.getElementById('vel-grid').innerHTML=html;
  var trend=d.trend||'flat';
  var tc={'up':'color:#22C55E','down':'color:#EF4444','flat':'color:var(--muted)'}[trend];
  var tl={'up':'▲ Trending UP','down':'▼ Trending DOWN','flat':'→ Flat'}[trend];
  document.getElementById('trend-footer').style.cssText=tc;
  document.getElementById('trend-footer').textContent=tl+' over last 4 weeks';
}

function renderTheatreTiles(d){
  var targets=d.next_targets||[];
  var byT={'EMEA':0,'AMER':0,'JAPAC':0,'LATAM':0};
  targets.forEach(function(a){var t=a.account_theatre||'EMEA';if(byT[t]!==undefined)byT[t]++;});
  var html='';
  ['EMEA','AMER','JAPAC','LATAM'].forEach(function(t){
    var c=TH_COLS[t];
    html+='<div class="th-tile">'
      +'<div class="th-name" style="color:'+c+'">'+t+'</div>'
      +'<div class="th-nums"><div><div class="th-big" style="color:'+c+'">'+byT[t]+'</div><div class="th-sub">M9 targets</div></div></div>'
      +'</div>';
  });
  document.getElementById('th-tiles').innerHTML=html;
}

document.querySelectorAll('.nav-link').forEach(function(a){if(window.location.pathname===a.getAttribute('href'))a.classList.add('active');});
load();
</script>
</body>
</html>
```

- [ ] **Step 2: Test it**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8200/forecast
```
Expected: `200`

Open `http://localhost:8200/forecast` — should show next week targets table, 4-week velocity, theatre tiles.

- [ ] **Step 3: Commit**

```bash
git add static/forecast.html
git commit -m "feat: /forecast page — next week M8/M9 targets + 4-week velocity trend by theatre"
```

---

## Task 7: Build `/audit` page

**Files:**
- Create: `static/audit.html`

- [ ] **Step 1: Create the file**

Create `static/audit.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Solstice — Audit Log</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0D1117;--card:#161B22;--border:#21262D;--text:#E6EDF3;--muted:#8B949E;--teal:#14B8A6;--green:#22C55E;--amber:#F59E0B;--red:#EF4444;--purple:#A78BFA;--mono:'Geist Mono',monospace}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.nav-link{font-size:10.5px;color:var(--muted);text-decoration:none;padding:4px 12px;border-radius:5px;border:1px solid transparent}
.nav-link:hover{background:rgba(255,255,255,.05);color:var(--text)}
.nav-link.active{color:var(--text);background:rgba(255,255,255,.08);border-color:var(--border)}
.page{max-width:1100px;margin:0 auto;padding:1.25rem 1.5rem}
/* Stats */
.stats{display:grid;grid-template-columns:repeat(6,1fr);gap:.6rem;margin-bottom:1.1rem}
.stat{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:.6rem 1rem;text-align:center}
.stat .n{font-size:22px;font-weight:700}
.stat .l{font-size:8px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);margin-top:2px}
/* Filters */
.fbar{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-bottom:1.1rem}
.fbar input{background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--text);font-size:9px;padding:5px 10px;flex:1;min-width:200px;outline:none}
select.fsel{background:var(--card);border:1px solid var(--border);border-radius:5px;color:var(--muted);font-size:9px;padding:5px 8px;font-family:var(--mono)}
/* Timeline */
.day-grp{margin-bottom:1.25rem}
.day-hdr{font-size:8px;font-family:var(--mono);letter-spacing:.1em;color:#484F58;padding:.3rem 0 .35rem;border-bottom:1px solid rgba(33,38,45,.6);margin-bottom:.4rem;display:flex;align-items:center;gap:.5rem}
.day-cnt{color:#30363D}
.entry{display:grid;grid-template-columns:3px 1fr;gap:0 .65rem;margin-bottom:.28rem}
.bar{border-radius:2px;align-self:stretch;margin:.15rem 0}
.body{background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.06);border-radius:6px;padding:.45rem .75rem}
.body.glow-m9{box-shadow:0 0 12px rgba(34,197,94,.12);border-color:rgba(34,197,94,.2)}
.body.glow-m8{border-color:rgba(20,184,166,.14)}
.body.glow-reg{border-color:rgba(239,68,68,.18)}
.etop{display:flex;align-items:center;gap:.4rem;margin-bottom:.2rem}
.ebadge{font-family:var(--mono);font-size:7.5px;font-weight:700;padding:1px 6px;border-radius:3px}
.eacct{font-size:10px;font-weight:700}
.etime{margin-left:auto;font-family:var(--mono);font-size:8px;color:#484F58}
.echg{font-family:var(--mono);font-size:9px;margin-bottom:.18rem}
.emeta{font-size:8px;color:#6E7681;display:flex;gap:.5rem;align-items:center}
.tag{font-size:7px;font-weight:700;padding:1px 4px;border-radius:2px}
.tag-emea{background:rgba(20,184,166,.1);color:var(--teal)}
.tag-amer{background:rgba(59,130,246,.1);color:#3B82F6}
.tag-japac{background:rgba(139,92,246,.1);color:#8B5CF6}
.tag-latam{background:rgba(245,158,11,.1);color:var(--amber)}
.empty{padding:2rem;text-align:center;color:var(--muted);font-size:11px}
</style>
</head>
<body>
<nav style="background:#161B22;border-bottom:1px solid #21262D;padding:.6rem 1.5rem;display:flex;align-items:center;gap:.25rem;position:sticky;top:0;z-index:100">
  <span style="font-weight:800;font-size:12px;color:#14B8A6;letter-spacing:.05em;margin-right:1rem">SOLSTICE</span>
  <a href="/ops" class="nav-link">Ops</a>
  <a href="/blockers" class="nav-link">Blockers</a>
  <a href="/forecast" class="nav-link">Forecast</a>
  <a href="/daily" class="nav-link">Daily</a>
  <a href="/audit" class="nav-link">Audit</a>
</nav>

<div class="page">
  <div class="stats" id="stats"></div>
  <div class="fbar">
    <input id="f-search" placeholder="Search accounts…" oninput="render()">
    <select class="fsel" id="f-theatre" onchange="load()">
      <option value="">All Theatres</option>
      <option value="EMEA">EMEA</option><option value="AMER">AMER/NAM</option>
      <option value="JAPAC">JAPAC</option><option value="LATAM">LATAM</option>
    </select>
    <select class="fsel" id="f-field" onchange="render()">
      <option value="">All Fields</option>
      <option value="M9 Upgrade Complete">M9 Complete</option>
      <option value="M8 Upgrade Started">M8 Started</option>
      <option value="M3 Buy-in">M3 Buy-in</option>
      <option value="M1 Outreach">M1 Outreach</option>
      <option value="cse">CSE Change</option>
    </select>
    <select class="fsel" id="f-sort" onchange="render()">
      <option value="asc">Oldest First</option>
      <option value="desc">Newest First</option>
    </select>
  </div>
  <div id="timeline"></div>
</div>

<script>
var E=function(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');};
var _rows=[];
var MC={'M9 Upgrade Complete':'#22C55E','M8 Upgrade Started':'#14B8A6','M7 Legal':'#8B5CF6',
  'M5 Tech Validation':'#3B82F6','M4 Discovery':'#06b6d4','M3 Buy-in':'#F59E0B',
  'M2 Entitlements':'#F97316','M1 Outreach':'#A78BFA','cse':'#EC4899','status':'#8B949E'};
var MI={'M9 Upgrade Complete':'M9','M8 Upgrade Started':'M8','M7 Legal':'M7',
  'M5 Tech Validation':'M5','M4 Discovery':'M4','M3 Buy-in':'M3',
  'M2 Entitlements':'M2','M1 Outreach':'M1','cse':'CSE','status':'STS'};
var TH_C={'EMEA':'#14B8A6','AMER':'#3B82F6','JAPAC':'#8B5CF6','LATAM':'#F59E0B'};

function fmtDt(s){
  if(!s) return '—';
  var months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  var iso=/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}:\d{2})?/.exec(s);
  if(iso) return iso[3]+' '+months[parseInt(iso[2])-1]+' '+(iso[4]||'');
  return s.substring(0,16);
}

function load(){
  var theatre=document.getElementById('f-theatre').value;
  fetch('/api/audit-log?theatre='+encodeURIComponent(theatre)).then(r=>r.json()).then(function(rows){
    _rows=rows;
    // Stats
    var m9=rows.filter(function(r){return r.field_name==='M9 Upgrade Complete';}).length;
    var m8=rows.filter(function(r){return r.field_name==='M8 Upgrade Started';}).length;
    var m3=rows.filter(function(r){return r.field_name==='M3 Buy-in';}).length;
    var cse=rows.filter(function(r){return r.field_name==='cse';}).length;
    var reg=rows.filter(function(r){return r.old_status==='Y'&&r.new_status==='N';}).length;
    document.getElementById('stats').innerHTML=
      '<div class="stat"><div class="n" style="color:#22C55E">'+m9+'</div><div class="l">M9 Complete</div></div>'
      +'<div class="stat"><div class="n" style="color:#14B8A6">'+m8+'</div><div class="l">M8 Started</div></div>'
      +'<div class="stat"><div class="n" style="color:#F59E0B">'+m3+'</div><div class="l">M3 Buy-in</div></div>'
      +'<div class="stat"><div class="n" style="color:#EC4899">'+cse+'</div><div class="l">CSE Changes</div></div>'
      +'<div class="stat"><div class="n" style="color:#EF4444">'+reg+'</div><div class="l">Regressions</div></div>'
      +'<div class="stat"><div class="n" style="color:var(--muted)">'+rows.length+'</div><div class="l">Total</div></div>';
    render();
  }).catch(function(){document.getElementById('timeline').innerHTML='<div class="empty">Error loading audit log</div>';});
}

function render(){
  var q=(document.getElementById('f-search').value||'').toLowerCase();
  var ff=document.getElementById('f-field').value;
  var sort=document.getElementById('f-sort').value;
  var rows=_rows.filter(function(r){
    if(ff&&r.field_name!==ff)return false;
    if(q&&!((r.customer_name||r.new_status||'')+(r.active_cse||'')).toLowerCase().includes(q))return false;
    return true;
  });
  if(sort==='desc')rows=rows.slice().reverse();
  if(!rows.length){document.getElementById('timeline').innerHTML='<div class="empty">No entries match filters</div>';return;}
  // Group by day
  var byDay={},dayOrder=[];
  rows.forEach(function(r){
    var day=(r.changed_at||'').substring(0,10);
    var months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var p=day.split('-');
    var label=p.length===3?p[2]+' '+(months[parseInt(p[1])-1]||p[1])+' '+p[0].substring(2):day;
    if(!byDay[day]){byDay[day]={label:label,entries:[]};dayOrder.push(day);}
    byDay[day].entries.push(r);
  });
  var html='';
  dayOrder.forEach(function(day){
    var grp=byDay[day];
    html+='<div class="day-grp">'
      +'<div class="day-hdr">'+E(grp.label)+' <span class="day-cnt">('+grp.entries.length+')</span></div>';
    grp.entries.forEach(function(r){
      var mc=MC[r.field_name]||'#8B949E';
      var mi=MI[r.field_name]||r.field_name||'?';
      var isM9=r.field_name==='M9 Upgrade Complete';
      var isM8=r.field_name==='M8 Upgrade Started';
      var isReg=r.old_status==='Y'&&r.new_status==='N';
      var isCse=r.field_name==='cse';
      if(isReg)mc='#EF4444';
      var glow=isM9?'glow-m9':isM8?'glow-m8':isReg?'glow-reg':'';
      var time=(r.changed_at||'').substring(11,16);
      var name=r.customer_name||r.new_status||'?';
      var th=r.account_theatre||'';
      var thcol=TH_C[th]||'';
      var chgHtml='';
      if(isCse)chgHtml='<span style="color:var(--muted)">'+E(r.old_status||'—')+'</span> → <span style="color:'+mc+';font-weight:700">'+E(r.new_status||'—')+'</span>';
      else if(isReg)chgHtml='<span style="color:#EF4444;font-weight:700">↓ REGRESSION: '+E(r.field_name)+'</span>';
      else chgHtml='<span style="color:'+mc+';font-weight:700">✅ '+E(r.field_name)+'</span>';
      html+='<div class="entry">'
        +'<div class="bar" style="background:'+mc+'"></div>'
        +'<div class="body '+glow+'">'
          +'<div class="etop">'
            +'<span class="ebadge" style="background:'+mc+'22;color:'+mc+'">'+E(mi)+'</span>'
            +'<span class="eacct" style="color:'+(isM9?'#4ade80':isM8?'#5eead4':'var(--text)')+'">'+E(name)+'</span>'
            +(time?'<span class="etime">'+E(time)+'</span>':'')
          +'</div>'
          +'<div class="echg">'+chgHtml+'</div>'
          +'<div class="emeta">'
            +(r.active_cse?'<span>'+E(r.active_cse)+'</span>':'')
            +(th?'<span class="tag" style="background:'+thcol+'18;color:'+thcol+'">'+E(th)+'</span>':'')
          +'</div>'
        +'</div>'
      +'</div>';
    });
    html+='</div>';
  });
  document.getElementById('timeline').innerHTML=html;
}

document.querySelectorAll('.nav-link').forEach(function(a){if(window.location.pathname===a.getAttribute('href'))a.classList.add('active');});
load();
</script>
</body>
</html>
```

- [ ] **Step 2: Test it**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8200/audit
```
Expected: `200`

Open `http://localhost:8200/audit` — should show stats bar + filters + timeline.

- [ ] **Step 3: Commit**

```bash
git add static/audit.html
git commit -m "feat: /audit page — full change history with stats, filters, theatre selector, timeline"
```

---

## Task 8: Update `/v2` → add nav links, remove audit section

**Files:**
- Modify: `static/v2.html`

- [ ] **Step 1: Add nav bar to v2.html**

In `static/v2.html`, find the `<nav>` element (the existing sidebar nav). Add a **top bar** just before `<nav>` by inserting immediately after `<body>`:

```html
<div style="background:#161B22;border-bottom:1px solid #21262D;padding:.5rem 1.5rem;display:flex;align-items:center;gap:.25rem">
  <span style="font-weight:800;font-size:12px;color:#14B8A6;letter-spacing:.05em;margin-right:1rem">SOLSTICE</span>
  <a href="/ops" style="font-size:10.5px;color:#E6EDF3;text-decoration:none;padding:3px 10px;border-radius:5px;background:rgba(255,255,255,.08);border:1px solid #21262D">Ops</a>
  <a href="/blockers" style="font-size:10.5px;color:#EF4444;text-decoration:none;padding:3px 10px;border-radius:5px">Blockers</a>
  <a href="/forecast" style="font-size:10.5px;color:#22C55E;text-decoration:none;padding:3px 10px;border-radius:5px">Forecast</a>
  <a href="/daily" style="font-size:10.5px;color:#8B949E;text-decoration:none;padding:3px 10px;border-radius:5px">Daily</a>
  <a href="/audit" style="font-size:10.5px;color:#A78BFA;text-decoration:none;padding:3px 10px;border-radius:5px">Audit</a>
</div>
```

- [ ] **Step 2: Remove the audit section from v2.html sidebar nav and body**

In the sidebar nav, find the audit link and remove it:
```html
  <a class="ni" href="#audit">◈ Audit Log <span class="nb" id="nb-audit">—</span></a>
```

In the main body, find the audit section and remove it:
```html
  <div class="sec" id="audit">
    ... (entire audit section)
  </div>
```

Also remove `loadAudit()` from `loadAll()`:
```javascript
// Change:
function loadAll(){loadStats();loadFunnel();loadWeekly();loadM1();loadMs();loadSLA();loadCSE();loadCompleted();loadAudit();initTheatre();}
// To:
function loadAll(){loadStats();loadFunnel();loadWeekly();loadM1();loadMs();loadSLA();loadCSE();loadCompleted();initTheatre();}
```

- [ ] **Step 3: Verify JS still valid**

```bash
node -e "
var c=require('fs').readFileSync('static/v2.html','utf8');
var vm=require('vm');
var js=c.substring(c.indexOf('<script>')+8,c.indexOf('</script>'));
try{new vm.Script(js);console.log('JS OK');}catch(e){console.log('ERR:',e.message);}
"
```
Expected: `JS OK`

- [ ] **Step 4: Commit**

```bash
git add static/v2.html
git commit -m "feat: add cross-page nav to /ops, remove audit section (now at /audit)"
```

---

## Task 9: Final integration test

- [ ] **Step 1: Restart server**

```bash
kill $(ps aux | grep "dashboard.py" | grep -v grep | awk '{print $2}') 2>/dev/null
sleep 1
nohup python3 dashboard.py > /tmp/solstice.log 2>&1 &
sleep 4
```

- [ ] **Step 2: Verify all pages return 200**

```bash
for page in / /ops /v2 /blockers /forecast /daily /audit; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8200$page")
  echo "$code  $page"
done
```

Expected:
```
307  /          (redirects to /ops)
200  /ops
200  /v2
200  /blockers
200  /forecast
200  /daily
200  /audit
```

- [ ] **Step 3: Verify all new APIs return data**

```bash
curl -s "http://localhost:8200/api/blockers?theatre=EMEA" | python3 -c "import json,sys;d=json.load(sys.stdin);print('blockers OK, no_contact:',len(d.get('no_contact',[])))"
curl -s "http://localhost:8200/api/forecast" | python3 -c "import json,sys;d=json.load(sys.stdin);print('forecast OK, trend:',d.get('trend'))"
```

- [ ] **Step 4: Final commit**

```bash
git add -A -- ':!data/' ':!../money/'
git commit -m "feat: complete multi-page dashboard — /blockers /forecast /audit + cross-page nav"
```

---

## Summary

| What | Where |
|---|---|
| Blocker review call | `/blockers` |
| Velocity + next week | `/forecast` |
| Change history | `/audit` |
| Main ops (cleaned) | `/ops` (= `/v2`) |
| Leadership trend | `/daily` (unchanged) |
