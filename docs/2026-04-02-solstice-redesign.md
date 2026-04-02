# Solstice Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign all 8 Solstice pages from dark ops-center aesthetic to clean light SaaS (white cards, dark navy nav, sky blue accent, Plus Jakarta Sans).

**Architecture:** Rewrite `solstice.css` with a complete new design token system, update `S.initNav()` in `solstice.js` for the new nav markup, then update each HTML page's font link and component classes. No API, routing, or JS logic changes — pure CSS/markup.

**Tech Stack:** Vanilla HTML/CSS/JS, FastAPI static serving, Plus Jakarta Sans + JetBrains Mono (Google Fonts)

---

## File Map

| File | Action | What changes |
|---|---|---|
| `static/solstice.css` | **Rewrite** | Full new design token system + component classes |
| `static/solstice.js` | **Modify** `S.initNav()` | Dark navy nav, sky blue active state, Plus Jakarta Sans |
| `static/v2.html` | **Modify** | Font link, body bg, card/table/badge classes, remove dark inline styles |
| `static/blockers.html` | **Modify** | Same pattern |
| `static/forecast.html` | **Modify** | Same pattern |
| `static/daily.html` | **Modify** | Same pattern |
| `static/cse.html` | **Modify** | Same pattern |
| `static/audit.html` | **Modify** | Same pattern |
| `static/weekly.html` | **Modify** | Same pattern |
| `static/compare.html` | **Modify** | Same pattern |

> WARNING — CLAUDE.md rule: HTML files containing .innerHTML MUST be written via bash cat heredoc. The Write tool is blocked for them.

---

## Task 1: New Design System (solstice.css)

**Files:**
- Rewrite: `Solstice/static/solstice.css`

- [ ] **Step 1: Write new solstice.css using Write tool** (no innerHTML in CSS)

Full content of new solstice.css:

```
/* Solstice Design System v2 — Light SaaS */
/* Fonts: Plus Jakarta Sans (UI) + JetBrains Mono (data) */

:root {
  --bg:          #f8fafc;
  --surface:     #ffffff;
  --surface-2:   #f1f5f9;
  --nav-bg:      #0c4a6e;
  --border:      #e2e8f0;
  --border-soft: #f1f5f9;
  --text:        #0f172a;
  --text-2:      #374151;
  --muted:       #94a3b8;
  --sky:         #0ea5e9;
  --sky-light:   #e0f2fe;
  --sky-border:  #bae6fd;
  --green:       #10b981;
  --amber:       #f59e0b;
  --red:         #ef4444;
  --green-light: #d1fae5;
  --amber-light: #fef3c7;
  --red-light:   #fee2e2;
  --mono:        'JetBrains Mono', monospace;
  --font:        'Plus Jakarta Sans', system-ui, sans-serif;
  --shadow-sm:   0 1px 3px rgba(0,0,0,.07), 0 1px 2px rgba(0,0,0,.04);
  --shadow-md:   0 4px 6px rgba(0,0,0,.07), 0 2px 4px rgba(0,0,0,.04);
  --radius:      10px;
  --radius-sm:   6px;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: var(--font); }

/* Nav */
.s-nav { background: var(--nav-bg); height: 44px; padding: 0 24px; display: flex; align-items: center; border-bottom: 1px solid rgba(255,255,255,.08); }

/* Layout */
.s-main { max-width: 1280px; margin: 0 auto; padding: 24px; }

/* Cards */
.card { background: var(--surface); border-radius: var(--radius); box-shadow: var(--shadow-sm); overflow: hidden; }
.card-head { padding: 12px 16px; border-bottom: 1px solid var(--border-soft); display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 12px; font-weight: 700; color: var(--text); }
.card-body  { padding: 16px; }

/* KPI Cards */
.kpi-card { background: var(--surface); border-radius: var(--radius); padding: 16px; box-shadow: var(--shadow-sm); border-left: 3px solid transparent; }
.kpi-card.sky   { border-left-color: var(--sky); }
.kpi-card.amber { border-left-color: var(--amber); }
.kpi-card.red   { border-left-color: var(--red); }
.kpi-card.green { border-left-color: var(--green); }
.kpi-label  { font-size: 10px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
.kpi-number { font-family: var(--mono); font-size: 32px; font-weight: 700; color: var(--text); line-height: 1; }
.kpi-delta  { font-size: 11px; font-weight: 600; margin-top: 6px; }
.delta-up   { color: var(--green); }
.delta-down { color: var(--red); }
.delta-neu  { color: var(--muted); }

/* Badges */
.badge { display: inline-flex; align-items: center; font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 20px; white-space: nowrap; }
.badge-red   { background: var(--red-light);   color: #dc2626; }
.badge-amber { background: var(--amber-light);  color: #d97706; }
.badge-green { background: var(--green-light);  color: #059669; }
.badge-sky   { background: var(--sky-light);    color: #0284c7; }
.badge-gray  { background: var(--surface-2);    color: #64748b; }

/* Pills */
.pill { font-size: 11px; font-weight: 600; padding: 4px 12px; border-radius: 20px; cursor: pointer; border: 1px solid var(--border); background: var(--surface); color: #64748b; transition: all .15s; user-select: none; }
.pill.active { background: var(--sky-light); color: #0284c7; border-color: var(--sky-border); }
.pill:hover:not(.active) { border-color: #cbd5e1; color: var(--text); }

/* Tables */
.s-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.s-table th { text-align: left; padding: 8px 12px; font-size: 9px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; background: var(--surface-2); border-bottom: 1px solid var(--border-soft); }
.s-table td { padding: 8px 12px; border-bottom: 1px solid var(--border-soft); color: var(--text-2); vertical-align: middle; }
.s-table tr:last-child td { border-bottom: none; }
.s-table tr:hover td { background: var(--surface-2); }

/* Funnel */
.funnel-row   { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.funnel-label { font-size: 10px; font-weight: 700; color: var(--muted); width: 24px; font-family: var(--mono); }
.funnel-track { flex: 1; height: 8px; background: var(--surface-2); border-radius: 4px; overflow: hidden; }
.funnel-bar   { height: 100%; border-radius: 4px; }
.funnel-pct   { font-size: 10px; font-weight: 700; font-family: var(--mono); width: 32px; text-align: right; }
.funnel-count { font-size: 10px; color: var(--muted); font-family: var(--mono); width: 44px; text-align: right; }

/* Utility */
.mono       { font-family: var(--mono); }
.text-link  { color: var(--sky); font-size: 10px; font-weight: 600; text-decoration: none; }
.text-link:hover { text-decoration: underline; }
.text-muted { color: var(--muted); }
.fw-600     { font-weight: 600; }
.fw-700     { font-weight: 700; }
```

- [ ] **Step 2: Syntax check and restart**

```bash
cd Solstice
python3 -c "import py_compile; py_compile.compile('dashboard.py'); print('OK')"
pkill -f dashboard.py; sleep 1; python3 dashboard.py &
curl -s http://localhost:8200/api/theatres | head -1
```

- [ ] **Step 3: Commit**

```bash
git add Solstice/static/solstice.css
git commit -m "feat(Solstice): new design system v2 — light SaaS tokens and component classes"
```

---

## Task 2: Update Nav (solstice.js S.initNav)

**Files:**
- Modify: `Solstice/static/solstice.js` around line 257

- [ ] **Step 1: Read current initNav to confirm line numbers**

```bash
grep -n "initNav\|nav.innerHTML" Solstice/static/solstice.js
```

- [ ] **Step 2: Replace initNav function body**

In `solstice.js`, replace the body of `S.initNav` (lines ~257-279) with the new version that uses:
- Dark navy `#0c4a6e` background (set via `.s-nav` CSS class on the `#s-nav` element — change each page's `<nav id="s-nav">` if needed)
- Sky blue `#0ea5e9` active bottom border
- Plus Jakarta Sans font
- White active link, rgba(255,255,255,.45) inactive
- Wordmark: sky rounded square + "Solstice" text

Key changes to the nav.innerHTML string:
1. Brand area: sky `#0ea5e9` logo square + bold "Solstice" white wordmark
2. Link styling: `color: active ? '#ffffff' : 'rgba(255,255,255,.45)'`, `border-bottom: active ? '2px solid #0ea5e9' : '2px solid transparent'`, `font-family: 'Plus Jakarta Sans',system-ui`
3. Search input: `background: rgba(255,255,255,.08)`, `border: 1px solid rgba(255,255,255,.12)`, white text, Plus Jakarta Sans
4. Dropdown: white bg `#ffffff`, border `#e2e8f0`, shadow `0 8px 24px rgba(0,0,0,.12)`

Also update each page's `<nav>` element: replace `style="..."` on the nav tag with `class="s-nav"` so the CSS handles the background.

- [ ] **Step 3: Verify nav on all pages**

Open `http://localhost:8200/ops` and `http://localhost:8200/blockers`. Nav should be dark navy, sky underline on active.

- [ ] **Step 4: Commit**

```bash
git add Solstice/static/solstice.js
git commit -m "feat(Solstice): update nav — dark navy, sky blue active, Plus Jakarta Sans"
```

---

## Task 3: Ops Page (v2.html)

**Files:**
- Modify: `Solstice/static/v2.html`

- [ ] **Step 1: Read the full file**

```bash
cat -n Solstice/static/v2.html
```

- [ ] **Step 2: Update head and body — 4 changes**

1. Replace JetBrains-only font link with:
   `<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">`

2. Replace `<body style="background:#0a0e1a;color:#e2e8f0;min-height:100vh">` with `<body>`

3. Replace `<nav id="s-nav" style="display:flex;...">` with `<nav id="s-nav" class="s-nav"></nav>`

4. Replace `<div id="main" style="max-width:1200px;margin:0 auto;padding:1.5rem">` with `<div id="main" class="s-main">`

- [ ] **Step 3: Update theatre pills row**

Replace the pill container div with:
```html
<div style="display:flex;align-items:center;gap:.5rem;margin-bottom:1.5rem;flex-wrap:wrap">
  <div id="theatre-pills" style="display:flex;gap:.5rem;flex-wrap:wrap;flex:1"></div>
  <span id="last-sync" class="mono text-muted" style="font-size:9px"></span>
  <button onclick="refreshData()" class="pill" style="border-color:var(--sky-border);color:var(--sky);background:var(--sky-light)">&#10227; Refresh Data</button>
</div>
```

In the JS `renderTheatrePills()` function, update pill generation to use `class="pill${active?' active':''}"` instead of inline dark styles.

- [ ] **Step 4: Update KPI grid**

Replace the 3 KPI divs:
```html
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:1.5rem">
  <div class="kpi-card sky">
    <div class="kpi-label">M9 COMPLETE</div>
    <div class="kpi-number" id="kpi-m9-val">—</div>
    <div class="kpi-delta delta-neu" style="font-size:10px">Upgrades done</div>
  </div>
  <div class="kpi-card amber">
    <div class="kpi-label">AT RISK</div>
    <div class="kpi-number" id="kpi-risk-val">—</div>
    <div class="kpi-delta delta-neu" style="font-size:10px">Signal at_risk, not done</div>
  </div>
  <div class="kpi-card red">
    <div class="kpi-label">BLOCKED</div>
    <div class="kpi-number" id="kpi-blocked-val">—</div>
    <div class="kpi-delta delta-neu" style="font-size:10px">Signal blocked, not done</div>
  </div>
</div>
```

- [ ] **Step 5: Update milestone funnel card**

```html
<div class="card" style="margin-bottom:1.5rem">
  <div class="card-head"><span class="card-title">MILESTONE FUNNEL</span></div>
  <div class="card-body"><div id="funnel-bars"></div></div>
</div>
```

In the JS funnel render function, update bar HTML to use `.funnel-row`, `.funnel-label`, `.funnel-track`, `.funnel-bar`, `.funnel-pct`, `.funnel-count` classes. Track background: `var(--surface-2)` not `rgba(255,255,255,.05)`. Bar colors: sky for M0-M3, amber for M8, green for M9.

- [ ] **Step 6: Update SLA card**

```html
<div class="card" style="margin-bottom:1.5rem">
  <div class="card-head">
    <div style="display:flex;align-items:center;gap:.75rem">
      <span class="card-title">SLA BREACHES</span>
      <span class="badge badge-red mono" id="sla-count">—</span>
    </div>
    <a href="/blockers" class="text-link">→ Blockers for full call prep</a>
  </div>
  <div style="overflow-x:auto">
    <table id="sla-table" class="s-table"></table>
  </div>
</div>
```

Update JS sla table render to use `<th>` with class `s-table` header pattern and `.badge` classes.

- [ ] **Step 7: Update M1 card**

```html
<div class="card" style="margin-bottom:1.5rem">
  <div class="card-head">
    <div style="display:flex;align-items:center;gap:.5rem">
      <span class="card-title">M1 ACTION PLAN</span>
      <span class="badge badge-sky">AI-assisted</span>
    </div>
  </div>
  <div style="overflow-x:auto">
    <table id="m1-table" class="s-table"></table>
  </div>
</div>
```

- [ ] **Step 8: Verify and commit**

Open `http://localhost:8200/ops`. Check: white bg, dark nav, sky KPI borders, clean tables, no dark artifacts.

```bash
git add Solstice/static/v2.html
git commit -m "feat(Solstice): redesign /ops page — light SaaS v2"
```

---

## Tasks 4-10: Remaining Pages (blockers, forecast, daily, cse, audit, weekly, compare)

Each page follows the same 4-step pattern:

**Step 1: Read the file** — `cat -n Solstice/static/<page>.html`

**Step 2: Update head + body** (same every time):
- Replace font link → Plus Jakarta Sans + JetBrains Mono combo
- Replace `<body style="background:#0a0e1a;...">` → `<body>`
- Replace `<nav id="s-nav" style="...">` → `<nav id="s-nav" class="s-nav"></nav>`
- Wrap main content in `<div class="s-main">` if not already

**Step 3: Update components** (page-specific):

| Page | Key changes |
|---|---|
| blockers.html | Remove dark `<style>` block; `.tpill` → `.pill`; dark card divs → `.card`; tables → `.s-table`; dropdown panels → `.card` |
| forecast.html | KPI cards → `.kpi-card`; Chart.js colors: white bg, `#f1f5f9` gridlines, `#94a3b8` ticks, sky/amber/green dataset colors |
| daily.html | Movement summary cards → `.card`; delta badges → `.badge-green`/`.badge-red`; Chart.js colors same as forecast |
| cse.html | Workload table → `.s-table`; KPI row → `.kpi-card` grid |
| audit.html | Timeline entries → `.card`; field badges → `.badge-sky`; export button → `.pill` sky style |
| weekly.html | Section cards (New M9, M8 Started, Newly Blocked, Resolved) → `.card` with `.s-table` inside |
| compare.html | Theatre columns → `.card`; stats → smaller `.kpi-card`; theatre label → `.card-head` with `.badge-gray` |

**Step 4: Verify + commit**:
```bash
open http://localhost:8200/<page>
git add Solstice/static/<page>.html
git commit -m "feat(Solstice): redesign /<page> page — light SaaS v2"
```

---

## Task 11: Final Verification + Corp Network Check

- [ ] **Step 1: Google Fonts corp network check**

```bash
curl -s --max-time 3 "https://fonts.googleapis.com" > /dev/null && echo "REACHABLE" || echo "BLOCKED"
```

If BLOCKED: download Plus Jakarta Sans + JetBrains Mono woff2 files, place in `Solstice/static/fonts/`, add `@font-face` rules to top of `solstice.css`, update font link in all 8 HTML files to `<link rel="stylesheet" href="/static/fonts/fonts.css">`.

- [ ] **Step 2: All 8 pages return 200**

```bash
for path in ops blockers forecast daily audit cse weekly compare; do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8200/$path)
  echo "$path: $code"
done
```
Expected: all 200.

- [ ] **Step 3: Run tests**

```bash
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest Solstice/tests/ -q
```
Expected: all pass.

- [ ] **Step 4: Final push**

```bash
git push
```
