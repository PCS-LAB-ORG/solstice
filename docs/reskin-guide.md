# How to Re-skin an Ops Dashboard — The Solstice Method

This is the exact process we used to take Solstice from a dark ops-center aesthetic to a clean light SaaS app. Follow it to re-skin any data dashboard.

---

## Step 1 — Make 3 Design Decisions First (before touching code)

Don't touch CSS until you've answered these. Every other decision follows from them.

### Decision 1: Direction
Pick one extreme and commit. Mediocrity is forgettable.

| Direction | Good for | Looks like |
|---|---|---|
| **Light SaaS** | Ops dashboards, B2B tools | Linear, Notion, Stripe |
| **Dark Terminal** | Dev tools, monitoring | Grafana, DataDog |
| **Enterprise Light** | Leadership briefings | Salesforce, Tableau |

We picked **Light SaaS** — white cards, light grey background, dark navy nav.

### Decision 2: Typography
Pick one UI font + one data font. Never more than two.

| Role | Our pick | Alternatives |
|---|---|---|
| UI / headings / body | **Plus Jakarta Sans** | Inter, DM Sans |
| Numbers / code / data | **JetBrains Mono** | Fira Mono, IBM Plex Mono |

Rule: everything that's a number, percentage, ID, or timestamp → monospace. Everything else → UI font.

### Decision 3: Accent Color
One accent. Everything interactive uses it.

| Color | Vibe | Hex |
|---|---|---|
| Sky blue | Clean, product | `#0ea5e9` ← we used this |
| Indigo | Enterprise | `#6366f1` |
| Cyan | Technical | `#22d3ee` |
| Emerald | Growth | `#10b981` |

---

## Step 2 — Build Your Token File

Create one CSS file with all your tokens. **Nothing in your HTML should use a hardcoded color or size.**

```css
/* paste this, swap the values for your brand */
:root {
  /* Backgrounds */
  --bg:          #f8fafc;   /* page background — very light grey */
  --surface:     #ffffff;   /* cards */
  --surface-2:   #f1f5f9;   /* table headers, hover states */

  /* Navigation */
  --nav-bg:      #0c4a6e;   /* dark navy — swap to your brand dark */

  /* Borders */
  --border:      #e2e8f0;
  --border-soft: #f1f5f9;

  /* Text */
  --text:        #0f172a;   /* headings — near black */
  --text-2:      #374151;   /* body copy */
  --muted:       #94a3b8;   /* labels, timestamps, secondary info */

  /* Your accent — ONE color */
  --sky:         #0ea5e9;   /* swap this to your accent */
  --sky-light:   #e0f2fe;   /* 10% tint of accent — for active states, backgrounds */
  --sky-border:  #bae6fd;   /* 30% tint — for borders on active elements */
  --accent:      var(--sky); /* alias — use --accent everywhere in your code */

  /* Semantic colors — don't change these */
  --green:       #10b981;
  --amber:       #f59e0b;
  --red:         #ef4444;
  --green-light: #d1fae5;
  --amber-light: #fef3c7;
  --red-light:   #fee2e2;

  /* Typography */
  --font:        'Plus Jakarta Sans', system-ui, sans-serif;
  --mono:        'JetBrains Mono', monospace;

  /* Shadows — don't change these */
  --shadow-sm:   0 1px 3px rgba(0,0,0,.07), 0 1px 2px rgba(0,0,0,.04);
  --shadow-md:   0 4px 6px rgba(0,0,0,.07), 0 2px 4px rgba(0,0,0,.04);

  /* Radius */
  --radius:      10px;   /* cards */
  --radius-sm:   6px;    /* buttons, inputs */
}
```

To change your brand color later: change 3 lines (`--sky`, `--sky-light`, `--sky-border`). Everything updates.

---

## Step 3 — Build Your Component Classes

Copy these exactly. They're the 80% of components every dashboard needs.

### Reset
```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: var(--font); }
```

### Navigation Bar
```css
.s-nav {
  background: var(--nav-bg);
  height: 44px;
  padding: 0 24px;
  display: flex;
  align-items: center;
  border-bottom: 1px solid rgba(255,255,255,.08);
}
```
Nav links inside: white text, `border-bottom: 2px solid var(--accent)` for active, `rgba(255,255,255,.45)` for inactive.

### Main Content Wrapper
```css
.s-main { max-width: 1280px; margin: 0 auto; padding: 24px; }
```

### Cards (the workhorse)
```css
.card { background: var(--surface); border-radius: var(--radius); box-shadow: var(--shadow-sm); overflow: hidden; }
.card-head { padding: 12px 16px; border-bottom: 1px solid var(--border-soft); display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 12px; font-weight: 700; color: var(--text); }
.card-body  { padding: 16px; }
```

### KPI Cards (metrics with colour-coded left border)
```css
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
```

Usage:
```html
<div class="kpi-card sky">
  <div class="kpi-label">TOTAL REVENUE</div>
  <div class="kpi-number">€247k</div>
  <div class="kpi-delta delta-up">▲ 12% this week</div>
</div>
```

### Badges (status pills)
```css
.badge { display: inline-flex; align-items: center; font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 20px; white-space: nowrap; }
.badge-red   { background: var(--red-light);   color: #dc2626; }
.badge-amber { background: var(--amber-light);  color: #d97706; }
.badge-green { background: var(--green-light);  color: #059669; }
.badge-sky   { background: var(--sky-light);    color: #0284c7; }
.badge-gray  { background: var(--surface-2);    color: #64748b; }
```

### Filter Pills (tab/toggle buttons)
```css
.pill { font-size: 11px; font-weight: 600; padding: 4px 12px; border-radius: 20px; cursor: pointer; border: 1px solid var(--border); background: var(--surface); color: #64748b; transition: all .15s; user-select: none; }
.pill.active { background: var(--sky-light); color: #0284c7; border-color: var(--sky-border); }
.pill:hover:not(.active) { border-color: #cbd5e1; color: var(--text); }
```

### Tables
```css
.s-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.s-table th { text-align: left; padding: 8px 12px; font-size: 9px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; background: var(--surface-2); border-bottom: 1px solid var(--border-soft); }
.s-table td { padding: 8px 12px; border-bottom: 1px solid var(--border-soft); color: var(--text-2); vertical-align: middle; }
.s-table tr:last-child td { border-bottom: none; }
.s-table tr:hover td { background: var(--surface-2); }
```

### Utility Classes
```css
.mono       { font-family: var(--mono); }
.text-link  { color: var(--sky); font-size: 10px; font-weight: 600; text-decoration: none; }
.text-link:hover { text-decoration: underline; }
.text-muted { color: var(--muted); }
.fw-600     { font-weight: 600; }
.fw-700     { font-weight: 700; }
```

---

## Step 4 — Font Setup

Add this to every page `<head>`:
```html
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
```

⚠️ **Corporate network warning:** Google Fonts CDN is blocked on some corp proxies. Test before a client demo. If blocked, self-host the woff2 files in your `/static/fonts/` folder and use `@font-face` instead.

---

## Step 5 — Apply to Your Pages

For each page, do these 4 things:

1. Replace `<body style="background:#000;color:#fff">` → `<body>`
2. Replace nav `style="..."` → `class="s-nav"`
3. Wrap main content in `<div class="s-main">`
4. Replace dark div wrappers with `.card` + `.card-head` + `.card-body`

**The rule:** if you see a hardcoded hex color like `#1e2d40` or `#0f1729` anywhere in your HTML, replace it with a CSS variable.

---

## Step 6 — The Typography Rule

| Content type | Class / treatment |
|---|---|
| Page title | `font-size: 22px; font-weight: 800; letter-spacing: -.4px` |
| Section heading | `.card-title` — 12px, 700 weight |
| Body text | Default — 14px, var(--font) |
| Labels / eyebrows | 10px, uppercase, 1px letter-spacing, var(--muted) |
| Numbers / data | `font-family: var(--mono)` always |
| Timestamps | `class="mono text-muted"` |

---

## Step 7 — The 3 Rules That Made Ours Look Good

**1. Only 2 fonts.** Plus Jakarta Sans for everything human-readable. JetBrains Mono for everything that came out of a database. Never cross the streams.

**2. No hardcoded colors in HTML.** Every color goes through a CSS variable. This makes theming one-line changes later.

**3. Commit to a direction.** We went 100% light. No "light mode with dark sidebar with grey cards." Pick light or dark. Then go all the way. Half-measures look amateur.

---

## Customising for Your Brand

To change the entire colour scheme, only change these 3 lines in `:root`:

```css
--sky:         #6366f1;   /* your brand accent */
--sky-light:   #eef2ff;   /* 10% tint — generate at uicolors.app */
--sky-border:  #c7d2fe;   /* 30% tint */
```

That's it. Every button, active pill, KPI border, link, and badge updates automatically.

---

## Full CSS File

See `Solstice/static/solstice.css` for the complete production file (135 lines total).

---

*Built by Marius + Claude Code, April 2026.*
