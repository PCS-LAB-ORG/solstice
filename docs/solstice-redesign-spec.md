# Solstice Redesign — Design Spec
**Date:** 2026-04-02
**Status:** Approved by Marius — ready for implementation

---

## Executive Summary

- Full redesign from dark ops-center aesthetic to clean light SaaS — same data density, dramatically more readable
- Design language: Plus Jakarta Sans + JetBrains Mono for data, sky blue (#0ea5e9) accent, top nav retained
- Roll-out: implement page by page starting with `/ops`, shared design system first

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Direction | Light SaaS (C) | Clean, modern, "1000 apps" feel — unanimous |
| Navigation | Top nav (current structure) | 8 pages fit, familiar to team |
| Body font | Plus Jakarta Sans | More character than Inter, stays professional |
| Data font | JetBrains Mono (keep) | Numbers, percentages, IDs — unchanged |
| Accent color | Sky Blue `#0ea5e9` | Cyan's calmer cousin, reads better on white |
| KPI borders | Left border stripe | Colour-coded signal without overwhelming |

---

## Design Tokens

```css
:root {
  /* Backgrounds */
  --bg:          #f8fafc;   /* page background */
  --surface:     #ffffff;   /* cards */
  --surface-2:   #f1f5f9;   /* table headers, hover states */

  /* Nav */
  --nav-bg:      #0c4a6e;   /* dark navy top bar */

  /* Borders */
  --border:      #e2e8f0;
  --border-soft: #f1f5f9;

  /* Text */
  --text:        #0f172a;   /* headings */
  --text-2:      #374151;   /* body */
  --text-muted:  #94a3b8;   /* labels, subtitles */

  /* Accent */
  --sky:         #0ea5e9;
  --sky-light:   #e0f2fe;
  --sky-border:  #bae6fd;

  /* Signals (unchanged semantics) */
  --green:       #10b981;
  --amber:       #f59e0b;
  --red:         #ef4444;
  --green-light: #d1fae5;
  --amber-light: #fef3c7;
  --red-light:   #fee2e2;

  /* Typography */
  --font-ui:     'Plus Jakarta Sans', system-ui, sans-serif;
  --font-mono:   'JetBrains Mono', monospace;

  /* Shadows */
  --shadow-sm:   0 1px 3px rgba(0,0,0,.07), 0 1px 2px rgba(0,0,0,.04);
  --shadow-md:   0 4px 6px rgba(0,0,0,.07), 0 2px 4px rgba(0,0,0,.04);

  /* Radius */
  --radius:      10px;
  --radius-sm:   6px;
}
```

---

## Component System

### Navigation Bar
- Background: `--nav-bg` (#0c4a6e dark navy)
- Height: 44px
- Logo: sky blue rounded square + "Solstice" wordmark
- Links: muted white, active = white + sky blue bottom border (2px)
- Font: Plus Jakarta Sans 12px 500 weight

### KPI Cards
- White card, `--shadow-sm`, `--radius`, left border stripe (3px, signal colour)
- Label: 10px uppercase 700 weight, `--text-muted`
- Value: 32px JetBrains Mono 700, `--text`
- Delta: 11px 600 weight, green/red/neutral

### Theatre Pills
- Active: `--sky-light` bg, `--sky` text, `--sky-border` border
- Inactive: white bg, `--text-muted`, `--border`
- Border radius: 20px (full pill)

### Milestone Funnel Bars
- Track: `#f1f5f9`, height 8px, border-radius 4px
- M0/M1/M3: sky gradient
- M8: amber
- M9: green
- Label + percentage in JetBrains Mono

### Data Tables
- Header: `--surface-2` bg, 9px uppercase 700, `--text-muted`
- Row: 11px `--text-2`, 8px 12px padding, border-bottom `--border-soft`
- Hover: `--surface-2` bg
- Account names: 600 weight

### Badges
- Pill shape (20px radius), 10px 600 weight
- Red: `#fee2e2` / `#dc2626`
- Amber: `#fef3c7` / `#d97706`
- Sky: `--sky-light` / `--sky`
- Green: `#d1fae5` / `#059669`
- Gray: `#f1f5f9` / `#64748b`

### Cards (general)
- White bg, `--shadow-sm`, `--radius`, `overflow:hidden`
- Header: 12px 700, padding 12px 16px, border-bottom `--border-soft`
- Body: 16px padding

---

## Page-by-Page Scope

All 8 pages redesigned. Roll-out order:

| Order | Page | URL | Key changes |
|---|---|---|---|
| 1 | **Ops** | `/ops` | KPI cards, funnel, SLA table, M1 plan |
| 2 | **Blockers** | `/blockers` | Blocker list by subtype, call brief panel |
| 3 | **Forecast** | `/forecast` | Velocity chart, next-week targets, SLA countdown |
| 4 | **Daily** | `/daily` | Leadership briefing, 30-day trend |
| 5 | **CSE** | `/cse` | Workload table, monthly velocity |
| 6 | **Audit** | `/audit` | Change timeline, export |
| 7 | **Weekly** | `/weekly` | Movement digest |
| 8 | **Compare** | `/compare` | 4-theatre side-by-side |

---

## Implementation Approach

### Step 1 — Redesign `solstice.css`
Replace all current tokens with new design system. Single file change cascades across all pages.

### Step 2 — Redesign `solstice.js`
Update `S.initNav()` to generate the new nav markup (dark navy, sky active state, Plus Jakarta Sans).

### Step 3 — Page by page HTML
Each `.html` file updated to use new component markup patterns. No inline style changes — all via CSS classes defined in Step 1.

### Font loading
Replace JetBrains Mono-only Google Fonts link with:
```html
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
```
⚠️ Corp network CDN risk — audit before demo (see prefs_and_rules.md).

---

## What Stays the Same
- All API endpoints unchanged
- JS logic unchanged — only markup and styles touched
- `solstice.js` shared design system (initNav, openAccountCard, etc.) — updated but not restructured
- Data density — same info, cleaner presentation
- Mobile responsiveness (inherit from current)

---

## What Changes
- `solstice.css` — full rewrite (26 lines → ~120 lines with full token system)
- Nav markup in `solstice.js` — dark navy instead of dark blue-gray
- Each `.html` — card class updates, badge class updates, table class updates
- Google Fonts link — add Plus Jakarta Sans
