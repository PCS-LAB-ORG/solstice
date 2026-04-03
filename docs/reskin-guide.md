# Solstice Design System — Full Re-skin Guide

> Copy-paste ready. Every component has the CSS and HTML you need.
> Built for data-heavy ops dashboards. Adapt the tokens for your brand.

---

## 1. Design Decisions (Make These First)

Before touching code, answer these 3 questions. Every CSS decision flows from them.

### 1.1 Direction

| Direction | Background | Cards | Nav | Best for |
|---|---|---|---|---|
| **Light SaaS** ← we used this | `#f8fafc` | `#ffffff` | Dark navy | B2B ops tools |
| Dark Terminal | `#0a0e1a` | `#0f1729` | Same dark | Dev tools |
| Enterprise | `#f1f5f9` | `#ffffff` | White + border | Leadership dashboards |

### 1.2 Font Pair

Always exactly two fonts:

```
UI font    → everything human readable (labels, headings, body)
Mono font  → everything from a database (numbers, IDs, timestamps, code)
```

| UI Font | Character | Used by |
|---|---|---|
| **Plus Jakarta Sans** ← our pick | Modern, rounded, readable | Retool, Liveblocks |
| Inter | Neutral, clean | Linear, Vercel, Notion |
| DM Sans | Slightly playful | Various SaaS |
| System UI | Native OS feel | Zero load time |

| Mono Font | Character |
|---|---|
| **JetBrains Mono** ← our pick | Technical, clear |
| Fira Mono | Classic dev |
| IBM Plex Mono | Corporate |

### 1.3 Accent Color

One accent. Your brand color. Everything interactive uses it.

```
accent         → buttons, links, active states, focus rings
accent-light   → 10% tint → active pill backgrounds, subtle highlights  
accent-border  → 30% tint → borders on active elements
```

Generate tints at **uicolors.app** — paste your hex, copy the 100 and 200 shades.

| Accent | Hex | Light (`/10`) | Border (`/30`) |
|---|---|---|---|
| Sky blue ← our pick | `#0ea5e9` | `#e0f2fe` | `#bae6fd` |
| Indigo | `#6366f1` | `#eef2ff` | `#c7d2fe` |
| Violet | `#8b5cf6` | `#f5f3ff` | `#ddd6fe` |
| Emerald | `#10b981` | `#d1fae5` | `#a7f3d0` |
| Rose | `#f43f5e` | `#fff1f2` | `#fecdd3` |

---

## 2. Token File — Complete

Create `design-system.css` (or whatever you call your shared CSS). Link it on every page. **Nothing in your HTML should ever have a hardcoded color or size.**

```css
/* ─────────────────────────────────────────────────────
   Design System Tokens
   How to customise:
   - Brand color → change --sky, --sky-light, --sky-border
   - Nav color   → change --nav-bg
   - That's it. Everything else updates automatically.
───────────────────────────────────────────────────── */

:root {
  /* ── Backgrounds ───────────────────────────── */
  --bg:          #f8fafc;   /* page canvas — very light cool grey */
  --surface:     #ffffff;   /* cards, dropdowns, modals */
  --surface-2:   #f1f5f9;   /* table row hover, secondary panels */
  --surface-3:   #e2e8f0;   /* tertiary — dividers, pressed states */

  /* ── Navigation ────────────────────────────── */
  --nav-bg:      #0c4a6e;   /* dark navy — your brand dark */
  --nav-height:  44px;

  /* ── Borders ───────────────────────────────── */
  --border:      #e2e8f0;   /* standard border */
  --border-soft: #f1f5f9;   /* subtle — inside cards */

  /* ── Text ──────────────────────────────────── */
  --text:        #0f172a;   /* headings, important labels — near black */
  --text-2:      #374151;   /* body copy, table cell content */
  --muted:       #94a3b8;   /* secondary info, timestamps, icons */
  --placeholder: #cbd5e1;   /* input placeholder text */

  /* ── Accent (YOUR BRAND COLOR) ─────────────── */
  --sky:         #0ea5e9;   /* ← swap to your accent */
  --sky-light:   #e0f2fe;   /* 10% tint — backgrounds */
  --sky-border:  #bae6fd;   /* 30% tint — borders */
  --sky-dark:    #0284c7;   /* 70% shade — text on light bg */
  --accent:      var(--sky);/* alias — use var(--accent) in your own code */

  /* ── Semantic Colors ───────────────────────── */
  /* Success */
  --green:         #10b981;
  --green-light:   #d1fae5;
  --green-dark:    #059669;
  /* Warning */
  --amber:         #f59e0b;
  --amber-light:   #fef3c7;
  --amber-dark:    #d97706;
  /* Danger */
  --red:           #ef4444;
  --red-light:     #fee2e2;
  --red-dark:      #dc2626;
  /* Churn / critical */
  --crimson:       #dc2626;
  --crimson-light: #fee2e2;

  /* ── Typography ────────────────────────────── */
  --font:     'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
  --mono:     'JetBrains Mono', 'Fira Mono', 'Courier New', monospace;

  /* ── Type Scale ────────────────────────────── */
  --text-xs:   9px;
  --text-sm:   10px;
  --text-base: 11px;
  --text-md:   12px;
  --text-lg:   14px;
  --text-xl:   16px;
  --text-2xl:  20px;
  --text-3xl:  28px;

  /* ── Spacing Scale (8px base) ──────────────── */
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-5:  20px;
  --space-6:  24px;
  --space-8:  32px;
  --space-10: 40px;

  /* ── Shadows ───────────────────────────────── */
  --shadow-sm: 0 1px 3px rgba(0,0,0,.07), 0 1px 2px rgba(0,0,0,.04);
  --shadow-md: 0 4px 6px rgba(0,0,0,.07), 0 2px 4px rgba(0,0,0,.04);
  --shadow-lg: 0 10px 15px rgba(0,0,0,.07), 0 4px 6px rgba(0,0,0,.05);
  --shadow-xl: 0 20px 25px rgba(0,0,0,.08), 0 8px 10px rgba(0,0,0,.04);

  /* ── Border Radius ─────────────────────────── */
  --radius-sm:  6px;   /* buttons, inputs, small elements */
  --radius:    10px;   /* cards, panels */
  --radius-lg: 14px;   /* modals, large panels */
  --radius-xl: 20px;   /* pills, badges */

  /* ── Transitions ───────────────────────────── */
  --t-fast:   100ms ease-out;
  --t-base:   150ms ease-out;
  --t-slow:   250ms ease-out;
}
```

---

## 3. Reset + Base

```css
/* Reset */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

/* Base */
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  font-size: var(--text-lg);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

a { color: var(--sky); text-decoration: none; }
a:hover { text-decoration: underline; }

/* Make numbers always mono */
.mono, [data-mono], td.number, .kpi-number {
  font-family: var(--mono);
}
```

---

## 4. Typography Classes

```css
/* Page title */
.page-title {
  font-size: var(--text-3xl);
  font-weight: 800;
  color: var(--text);
  letter-spacing: -.4px;
  line-height: 1.1;
}

/* Page subtitle */
.page-subtitle {
  font-size: var(--text-lg);
  color: var(--muted);
  font-weight: 500;
  margin-top: 2px;
}

/* Section label / eyebrow — appears above headings */
.label {
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 1.5px;
}

/* Body text */
.text-body  { font-size: var(--text-lg);   color: var(--text-2); }
.text-sm    { font-size: var(--text-base); color: var(--text-2); }
.text-xs    { font-size: var(--text-sm);   color: var(--muted);  }
.text-muted { color: var(--muted); }
.fw-500     { font-weight: 500; }
.fw-600     { font-weight: 600; }
.fw-700     { font-weight: 700; }
.fw-800     { font-weight: 800; }
.text-link  {
  color: var(--sky);
  font-size: var(--text-sm);
  font-weight: 600;
  text-decoration: none;
}
.text-link:hover { text-decoration: underline; }
```

---

## 5. Navigation

### CSS

```css
/* Nav bar */
.s-nav {
  background: var(--nav-bg);
  height: var(--nav-height);
  padding: 0 var(--space-6);
  display: flex;
  align-items: center;
  gap: 0;
  border-bottom: 1px solid rgba(255,255,255,.08);
  position: sticky;
  top: 0;
  z-index: 100;
}

/* Brand / logo area */
.nav-brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding-right: var(--space-5);
  margin-right: var(--space-2);
  border-right: 1px solid rgba(255,255,255,.1);
  flex-shrink: 0;
}

.nav-logo {
  width: 22px;
  height: 22px;
  background: var(--sky);
  border-radius: 5px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.nav-name {
  font-family: var(--font);
  font-size: 13px;
  font-weight: 700;
  color: white;
  letter-spacing: -.2px;
}

/* Nav links */
.nav-link {
  font-family: var(--font);
  font-size: 12px;
  font-weight: 500;
  color: rgba(255,255,255,.45);
  text-decoration: none;
  height: var(--nav-height);
  display: flex;
  align-items: center;
  padding: 0 var(--space-3);
  border-bottom: 2px solid transparent;
  transition: color var(--t-base);
}

.nav-link:hover { color: rgba(255,255,255,.8); text-decoration: none; }

/* Active state */
.nav-link.active {
  color: white;
  font-weight: 600;
  border-bottom-color: var(--sky);
}

/* Nav search (right side) */
.nav-search {
  background: rgba(255,255,255,.08);
  border: 1px solid rgba(255,255,255,.12);
  border-radius: var(--radius-sm);
  color: white;
  font-family: var(--font);
  font-size: 10px;
  padding: 4px 10px;
  outline: none;
  width: 150px;
  transition: width var(--t-slow);
}
.nav-search::placeholder { color: rgba(255,255,255,.35); }
.nav-search:focus { width: 210px; }
```

### HTML

```html
<nav class="s-nav">
  <!-- Brand -->
  <div class="nav-brand">
    <div class="nav-logo">☀</div>
    <span class="nav-name">YourApp</span>
  </div>

  <!-- Links -->
  <a href="/dashboard" class="nav-link active">Dashboard</a>
  <a href="/reports"   class="nav-link">Reports</a>
  <a href="/settings"  class="nav-link">Settings</a>

  <!-- Spacer -->
  <div style="flex:1"></div>

  <!-- Search -->
  <input class="nav-search" type="text" placeholder="⌕ Search...">
</nav>
```

---

## 6. Layout

```css
/* Page wrapper — center + max-width */
.s-main {
  max-width: 1280px;
  margin: 0 auto;
  padding: var(--space-6);
}

/* Page header row */
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: var(--space-5);
}

/* Common grid layouts */
.grid-2 { display: grid; grid-template-columns: 1fr 1fr;       gap: var(--space-3); }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr;   gap: var(--space-3); }
.grid-4 { display: grid; grid-template-columns: repeat(4,1fr); gap: var(--space-3); }

/* Responsive: collapse to 1 column on small screens */
@media (max-width: 768px) {
  .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr; }
}
```

```html
<div class="s-main">
  <div class="page-header">
    <div>
      <div class="page-title">Dashboard</div>
      <div class="page-subtitle">Your subtitle here</div>
    </div>
    <div><!-- actions --></div>
  </div>

  <!-- 3-column KPI row -->
  <div class="grid-3" style="margin-bottom: var(--space-5)">
    <!-- kpi cards here -->
  </div>

  <!-- 2-column cards -->
  <div class="grid-2">
    <!-- cards here -->
  </div>
</div>
```

---

## 7. Cards

The foundation of every section.

```css
/* Base card */
.card {
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

/* Card header */
.card-head {
  padding: 12px var(--space-4);
  border-bottom: 1px solid var(--border-soft);
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 44px;
}

.card-title  { font-size: var(--text-md); font-weight: 700; color: var(--text); }
.card-body   { padding: var(--space-4); }
.card-footer {
  padding: 10px var(--space-4);
  border-top: 1px solid var(--border-soft);
  background: var(--surface-2);
  font-size: var(--text-sm);
  color: var(--muted);
}

/* Accent-bordered card (for alerts, important info) */
.card.accent-left { border-left: 3px solid var(--sky); }
.card.danger-left { border-left: 3px solid var(--red); }
.card.warn-left   { border-left: 3px solid var(--amber); }
```

```html
<!-- Standard card -->
<div class="card" style="margin-bottom: var(--space-4)">
  <div class="card-head">
    <span class="card-title">Section Title</span>
    <a href="#" class="text-link">View all →</a>
  </div>
  <div class="card-body">
    <!-- content -->
  </div>
  <div class="card-footer">Updated 4 minutes ago</div>
</div>
```

---

## 8. KPI Cards

For headline metrics. The left border color signals status at a glance.

```css
.kpi-card {
  background: var(--surface);
  border-radius: var(--radius);
  padding: var(--space-4);
  box-shadow: var(--shadow-sm);
  border-left: 3px solid transparent;
}

/* Color variants — pick the one that matches your metric's status */
.kpi-card.sky    { border-left-color: var(--sky);   }
.kpi-card.green  { border-left-color: var(--green); }
.kpi-card.amber  { border-left-color: var(--amber); }
.kpi-card.red    { border-left-color: var(--red);   }

/* Typography inside KPI cards */
.kpi-label {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: var(--space-1) + 2px;
}

.kpi-number {
  font-family: var(--mono);
  font-size: 32px;
  font-weight: 700;
  color: var(--text);
  line-height: 1;
}

.kpi-delta { font-size: 11px; font-weight: 600; margin-top: var(--space-1) + 2px; }
.delta-up  { color: var(--green); }
.delta-down{ color: var(--red);   }
.delta-neu { color: var(--muted); }
```

```html
<div class="grid-3" style="margin-bottom: 20px">

  <div class="kpi-card sky">
    <div class="kpi-label">Total Users</div>
    <div class="kpi-number">24,701</div>
    <div class="kpi-delta delta-up">▲ 12% this week</div>
  </div>

  <div class="kpi-card amber">
    <div class="kpi-label">At Risk</div>
    <div class="kpi-number">43</div>
    <div class="kpi-delta delta-down">▼ 3 new today</div>
  </div>

  <div class="kpi-card red">
    <div class="kpi-label">Blocked</div>
    <div class="kpi-number">12</div>
    <div class="kpi-delta delta-neu">— unchanged</div>
  </div>

</div>
```

---

## 9. Badges

Small status indicators. Always use them — they make tables scannable.

```css
.badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: var(--text-sm);
  font-weight: 600;
  padding: 2px 7px;
  border-radius: var(--radius-xl);
  white-space: nowrap;
  line-height: 1.4;
}

/* Semantic variants */
.badge-red    { background: var(--red-light);    color: var(--red-dark);    }
.badge-amber  { background: var(--amber-light);  color: var(--amber-dark);  }
.badge-green  { background: var(--green-light);  color: var(--green-dark);  }
.badge-sky    { background: var(--sky-light);    color: var(--sky-dark);    }
.badge-gray   { background: var(--surface-2);    color: #64748b;            }
.badge-purple { background: #f5f3ff;             color: #7c3aed;            }

/* Size modifier */
.badge.sm { font-size: 8px; padding: 1px 5px; }
.badge.lg { font-size: 11px; padding: 3px 9px; }
```

```html
<!-- Status badges -->
<span class="badge badge-green">Active</span>
<span class="badge badge-amber">At Risk</span>
<span class="badge badge-red">Blocked</span>
<span class="badge badge-sky">In Progress</span>
<span class="badge badge-gray">EMEA</span>

<!-- With dot indicator -->
<span class="badge badge-green">
  <span style="width:5px;height:5px;border-radius:50%;background:var(--green);flex-shrink:0"></span>
  Online
</span>

<!-- Small badge (inside table cells) -->
<span class="badge badge-red sm">+14d</span>
```

---

## 10. Filter Pills

For tabs, toggles, and filter groups.

```css
.pill-row { display: flex; gap: var(--space-1) + 2px; flex-wrap: wrap; align-items: center; }

.pill {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: var(--radius-xl);
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--surface);
  color: #64748b;
  transition: all var(--t-base);
  user-select: none;
  white-space: nowrap;
}

.pill:hover:not(.active):not(:disabled) {
  border-color: #cbd5e1;
  color: var(--text);
}

.pill.active {
  background: var(--sky-light);
  color: var(--sky-dark);
  border-color: var(--sky-border);
}

.pill:disabled {
  opacity: .45;
  cursor: not-allowed;
}

/* Button-style pill (for actions) */
.pill.action {
  border-color: var(--sky-border);
  color: var(--sky);
  background: var(--sky-light);
}
.pill.action:hover { background: #bae6fd; }
```

```html
<div class="pill-row" style="margin-bottom: 20px">
  <button class="pill active" onclick="filter('all')">All</button>
  <button class="pill" onclick="filter('emea')">EMEA</button>
  <button class="pill" onclick="filter('amer')">AMER</button>
  <button class="pill" onclick="filter('japac')">JAPAC</button>
  <div style="width:1px;height:18px;background:var(--border);margin:0 4px"></div>
  <button class="pill action" onclick="refresh()">↻ Refresh</button>
</div>
```

---

## 11. Tables

The most used component in any data app.

```css
/* Table container (for scroll on mobile) */
.table-wrap { overflow-x: auto; }

/* Table */
.s-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-base);
}

/* Header */
.s-table thead tr {
  background: var(--surface-2);
  border-bottom: 1px solid var(--border-soft);
}

.s-table th {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 1px;
  white-space: nowrap;
}

.s-table th.right,
.s-table td.right { text-align: right; }

/* Rows */
.s-table td {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border-soft);
  color: var(--text-2);
  vertical-align: middle;
}

.s-table tr:last-child td { border-bottom: none; }

.s-table tbody tr {
  transition: background var(--t-fast);
  cursor: default;
}

.s-table tbody tr:hover td { background: var(--surface-2); }

/* Clickable rows */
.s-table tbody tr.clickable { cursor: pointer; }

/* Primary cell content */
.s-table td.primary { font-weight: 600; color: var(--text); }

/* Empty state */
.s-table .empty-row td {
  text-align: center;
  padding: 32px;
  color: var(--muted);
  font-size: var(--text-lg);
}
```

```html
<div class="card">
  <div class="card-head">
    <span class="card-title">Users</span>
    <span class="badge badge-sky">247 total</span>
  </div>
  <div class="table-wrap">
    <table class="s-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Region</th>
          <th>Status</th>
          <th class="right">Last Active</th>
        </tr>
      </thead>
      <tbody>
        <tr class="clickable" onclick="openDetail('123')">
          <td class="primary">Acme Corporation</td>
          <td><span class="badge badge-gray">EMEA</span></td>
          <td><span class="badge badge-green">Active</span></td>
          <td class="right mono text-muted">2h ago</td>
        </tr>
        <tr class="clickable" onclick="openDetail('124')">
          <td class="primary">TechStart GmbH</td>
          <td><span class="badge badge-gray">EMEA</span></td>
          <td><span class="badge badge-amber">At Risk</span></td>
          <td class="right mono text-muted">3d ago</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
```

---

## 12. Buttons

```css
/* Base */
.btn {
  font-family: var(--font);
  font-size: var(--text-md);
  font-weight: 600;
  padding: 7px 16px;
  border-radius: var(--radius-sm);
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: var(--space-1) + 2px;
  transition: all var(--t-base);
  text-decoration: none;
  white-space: nowrap;
}

.btn:focus-visible { outline: 2px solid var(--sky); outline-offset: 2px; }
.btn:disabled      { opacity: .45; cursor: not-allowed; }

/* Primary */
.btn-primary {
  background: var(--sky);
  color: white;
}
.btn-primary:hover:not(:disabled) { background: var(--sky-dark); }
.btn-primary:active { transform: scale(.98); }

/* Secondary */
.btn-secondary {
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
}
.btn-secondary:hover:not(:disabled) { border-color: #cbd5e1; background: var(--surface-2); }

/* Ghost (text only) */
.btn-ghost {
  background: transparent;
  color: var(--muted);
}
.btn-ghost:hover:not(:disabled) { color: var(--text); background: var(--surface-2); }

/* Danger */
.btn-danger {
  background: var(--red);
  color: white;
}
.btn-danger:hover:not(:disabled) { background: var(--red-dark); }

/* Sizes */
.btn.sm { font-size: 10px; padding: 4px 10px; }
.btn.lg { font-size: 14px; padding: 10px 20px; }
```

```html
<button class="btn btn-primary">Save changes</button>
<button class="btn btn-secondary">Cancel</button>
<button class="btn btn-danger">Delete</button>
<button class="btn btn-ghost sm">← Back</button>
```

---

## 13. Form Inputs

```css
.input {
  font-family: var(--font);
  font-size: var(--text-lg);
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 6px 10px;
  outline: none;
  width: 100%;
  transition: border-color var(--t-base);
}

.input::placeholder { color: var(--placeholder); }
.input:focus        { border-color: var(--sky); box-shadow: 0 0 0 2px var(--sky-light); }
.input:disabled     { background: var(--surface-2); opacity: .65; cursor: not-allowed; }

/* Select */
.select {
  font-family: var(--font);
  font-size: var(--text-base);
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 5px 8px;
  outline: none;
  cursor: pointer;
}
.select:focus { border-color: var(--sky); }

/* Label */
.form-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text);
  margin-bottom: var(--space-1);
  display: block;
}
```

```html
<div style="margin-bottom: 12px">
  <label class="form-label">Search</label>
  <input class="input" type="text" placeholder="Account name...">
</div>

<div style="margin-bottom: 12px">
  <label class="form-label">Region</label>
  <select class="select">
    <option value="">All Regions</option>
    <option>EMEA</option>
    <option>AMER</option>
  </select>
</div>
```

---

## 14. Progress / Funnel Bars

Great for showing pipeline stages or completion rates.

```css
.funnel-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.funnel-label {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--muted);
  width: 80px;
  flex-shrink: 0;
  font-family: var(--mono);
}

.funnel-track {
  flex: 1;
  height: 8px;
  background: var(--surface-2);
  border-radius: 4px;
  overflow: hidden;
}

.funnel-bar {
  height: 100%;
  border-radius: 4px;
  transition: width .4s ease-out;
}

/* Color variants */
.funnel-bar.sky   { background: var(--sky);   }
.funnel-bar.green { background: var(--green); }
.funnel-bar.amber { background: var(--amber); }
.funnel-bar.red   { background: var(--red);   }

.funnel-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.funnel-pct   { font-size: var(--text-sm);  font-weight: 700; font-family: var(--mono); width: 36px; text-align: right; }
.funnel-count { font-size: var(--text-sm);  color: var(--muted); font-family: var(--mono); width: 50px; text-align: right; }
```

```html
<div class="card">
  <div class="card-head"><span class="card-title">Pipeline Stages</span></div>
  <div class="card-body">

    <div class="funnel-row">
      <div class="funnel-label">Stage 1</div>
      <div class="funnel-track">
        <div class="funnel-bar sky" style="width:92%"></div>
      </div>
      <div class="funnel-meta">
        <span class="funnel-pct" style="color:var(--sky)">92%</span>
        <span class="funnel-count">1,840</span>
      </div>
    </div>

    <div class="funnel-row">
      <div class="funnel-label">Stage 2</div>
      <div class="funnel-track">
        <div class="funnel-bar amber" style="width:61%"></div>
      </div>
      <div class="funnel-meta">
        <span class="funnel-pct" style="color:var(--amber)">61%</span>
        <span class="funnel-count">1,220</span>
      </div>
    </div>

    <div class="funnel-row">
      <div class="funnel-label">Stage 3</div>
      <div class="funnel-track">
        <div class="funnel-bar green" style="width:14%"></div>
      </div>
      <div class="funnel-meta">
        <span class="funnel-pct" style="color:var(--green)">14%</span>
        <span class="funnel-count">280</span>
      </div>
    </div>

  </div>
</div>
```

---

## 15. Loading States

```css
/* Spinning hourglass / loader */
@keyframes spin { to { transform: rotate(360deg); } }
.spin { animation: spin 1.2s linear infinite; display: inline-block; }

/* Skeleton loader */
@keyframes shimmer {
  from { background-position: -200% 0; }
  to   { background-position: 200% 0; }
}
.skeleton {
  background: linear-gradient(90deg, var(--surface-2) 25%, var(--border) 50%, var(--surface-2) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: var(--radius-sm);
}

/* Empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px var(--space-6);
  color: var(--muted);
  text-align: center;
}
.empty-state .empty-icon { font-size: 32px; margin-bottom: var(--space-3); }
.empty-state .empty-text { font-size: var(--text-lg); font-weight: 500; }
.empty-state .empty-hint { font-size: var(--text-base); margin-top: var(--space-1); }
```

```html
<!-- Loading section header -->
<div class="shdr-icon spin">⌛</div>
<span style="color:var(--muted);font-size:10px;font-style:italic">Loading...</span>

<!-- Skeleton placeholder -->
<div class="skeleton" style="height:20px;width:60%;margin-bottom:8px"></div>
<div class="skeleton" style="height:14px;width:80%"></div>

<!-- Empty state -->
<div class="empty-state">
  <div class="empty-icon">✅</div>
  <div class="empty-text">All clear</div>
  <div class="empty-hint">No items match your filters</div>
</div>
```

---

## 16. The 5 Rules That Make It Look Good

**1. All colors through variables. No exceptions.**
Never write `color: #0ea5e9` in HTML. Write `color: var(--sky)`. This is what lets you rebrand in 3 lines.

**2. Numbers are always monospace.**
Any value from a database — counts, percentages, currency, IDs, timestamps — gets `font-family: var(--mono)`. Makes data scannable instantly.

**3. Left border on KPI cards = status.**
Sky → neutral/positive. Amber → warning. Red → bad. Green → good. Your eye reads it before your brain does.

**4. Surface hierarchy: bg → surface → surface-2.**
Page background (`--bg`) → cards (`--surface`) → table headers/hover (`--surface-2`). Three levels, no more. Depth through lightness, not shadows.

**5. Uppercase labels everywhere.**
Card titles, table headers, KPI labels. `text-transform: uppercase; letter-spacing: 1px`. Caps + tracking = professional ops dashboard. Without it = random webpage.

---

## 17. To Rebrand for Your Friend

Change only these 4 lines in `:root`:

```css
--sky:         #YOUR_ACCENT;    /* e.g. #6366f1 for indigo */
--sky-light:   #YOUR_LIGHT;     /* 10% tint from uicolors.app */
--sky-border:  #YOUR_BORDER;    /* 30% tint from uicolors.app */
--nav-bg:      #YOUR_DARK;      /* dark version of your brand */
```

Everything — buttons, active pills, KPI borders, links, badges, focus rings — updates automatically.

---

*Built by Marius + Claude Code — April 2026. Based on the Solstice ops dashboard redesign.*
*Full implementation at: [shpapy/solstice](https://github.com/shpapy/solstice)*
