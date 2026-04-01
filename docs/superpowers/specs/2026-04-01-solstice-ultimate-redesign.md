# Solstice — Ultimate Redesign Spec
**Date:** 2026-04-01  
**Status:** Approved  
**Author:** Marius + Claude

---

## Overview

Full redesign of Solstice from a 5-page vanilla dashboard into an 8-page production-grade ops platform. Shared design system (`solstice.js` + `solstice.css`), Ops Center cyan aesthetic, 3 new pages, enhanced account modal, and 6 UX improvements. Target: clean GitHub repo deployable by the CC team.

---

## Architecture

**Approach: Design System First (C)**

Extract all shared code into a single `static/solstice.js` module loaded by every page. Eliminates the copy-paste problem (currently ~200 lines duplicated across 5 files) that caused the `openGCard` quote-escaping bug and will cause more as pages grow.

```
static/
  solstice.js        ← shared module: nav, health bar, search, modal, badges
  solstice.css       ← design tokens + Tailwind CDN override vars
  v2.html            ← /ops   (rebuilt)
  blockers.html      ← /blockers (rebuilt)
  forecast.html      ← /forecast (rebuilt)
  daily.html         ← /daily (rebuilt)
  audit.html         ← /audit (rebuilt)
  cse.html           ← NEW /cse
  weekly.html        ← NEW /weekly
  compare.html       ← NEW /compare

dashboard.py         ← +4 new API endpoints, no breaking changes
```

**Tailwind CDN:** loaded via `<script src="https://cdn.tailwindcss.com">` on every page. Verify loads on corp laptop before building (simple curl test). Fallback: inline CSS if firewall blocks it.

---

## Design System

### Visual Tokens (Ops Center — Cyan Glow)

| Token | Value | Usage |
|---|---|---|
| Background | `#0a0e1a` | Page bg |
| Surface | `#0f1729` | Cards, panels |
| Border | `#1e2d40` | All borders |
| Accent | `#22d3ee` | KPIs, active nav, glows |
| Text primary | `#e2e8f0` | Body text |
| Text muted | `#475569` | Labels, meta |
| Signal green | `#10b981` | M9 complete, on track |
| Signal amber | `#f59e0b` | At risk, SLA warning |
| Signal red | `#ef4444` | Blocked, SLA overdue |
| Font data | JetBrains Mono (CDN) | Numbers, labels, KPIs |
| Font UI | system-ui | Nav, prose, buttons |

### `solstice.js` — Component API

| Function | Signature | Description |
|---|---|---|
| `initNav(page)` | `initNav('ops')` | Renders full top bar: logo, page links (active highlighted), theatre health pills, global search. Calls `/api/health-summary` on load. |
| `healthBar()` | internal | Fetches health summary, renders 🟢🟡🔴 pill per theatre in nav. Refreshes every 5 min. |
| `openAccountCard(id)` | `openAccountCard('acc001')` | Full account modal — see Account Modal section. Persists to `localStorage`. |
| `slaCountdown(m3, m8, m9)` | pure fn, returns HTML | Days remaining badge. Green (>7d) → Amber (≤7d) → Red (overdue). Uses M3→M8 ≤14d, M8→M9 ≤28d rules. |
| `blockerAge(signal_date)` | pure fn, returns HTML | "Blocked N days" badge. Green (<7d) → Amber (7–21d) → Red (>21d). |
| `syncSummary(events)` | `syncSummary({m9:5,blocked:2,resolved:1})` | Dismissible toast after pipeline run. "+5 M9 · 2 newly blocked · 1 resolved". |
| `exportCSV(rows, filename)` | pure fn | Client-side CSV export of any array of objects. |
| `gSearch(q)` | internal | Global search against `/api/customer-search`. Deduplicates by normalised customer_name. |
| `closeCard()` | `closeCard()` | Dismisses account modal. Clears `localStorage`. |

All functions are exported as properties of a single `window.S` namespace. Pages call `S.initNav('ops')` etc.

### `solstice.css`

Design tokens as CSS custom properties. Minimal — Tailwind handles utilities. Defines:
- `--accent`, `--surface`, `--border`, etc.
- `.glow-cyan` — `box-shadow: 0 0 12px rgba(34,211,238,.3)`
- `.kpi-number` — Mono, 2.5rem, accent colour
- `.signal-green/amber/red` — consistent signal colours

---

## Account Modal (Upgraded)

Replaces the current `openGCard` card. Triggered from global search, table rows on all pages, and deep-link URL.

**Sections:**
1. **Header** — customer name, theatre, CSE, signal chip, churn risk chip, live-fire chip
2. **Milestone bar** — M0→M9 with date and ✓/→/○ state. Compact horizontal timeline.
3. **Call prep brief** — Last contact date, next action owner, days since last milestone moved
4. **SLA countdown** — If M3 complete and M8 not started: M3→M8 remaining. If M8 started and M9 not complete: M8→M9 remaining.
5. **Blocker age badge** — If signal=blocked or at_risk: "Blocked N days"
6. **DC Progress** — dc_progress field, upgrade_notes, health_notes
7. **PS engagement** — psc, pm, ps_status, clarizen_id if available
8. **History** — Last 20 status changes from `status_history`
9. **Metadata grid** — region, cohort, cc_rep, cc_dsm, roadmap_url, ps_plan_url

`localStorage` key `lastGCard` — restored on page navigation.

---

## Pages

### Existing Pages (Redesigned)

| Page | URL | Key changes from current |
|---|---|---|
| **Ops** | `/ops` | Cyan KPI counters (M9/at-risk/blocked with glow), milestone funnel bars, CSE workload strip, M1 action plan, SLA breach list. Full `initNav`. |
| **Blockers** | `/blockers` | Blocker age badge on every row. Call prep brief on row expand. Subtype grouping unchanged. |
| **Forecast** | `/forecast` | Next-week targets + 4-week velocity. SLA countdown section added below velocity chart. |
| **Daily** | `/daily` | Leadership briefing + 30-day M8/M9 trend. Sync summary toast after refresh. |
| **Audit** | `/audit` | Change timeline unchanged. Export CSV button added to current filtered view. |

### New Pages

**`/cse`** — CSE Workload  
Fetches `/api/cse-workload?theatre=`. Table sorted by blocked_count desc. Columns: CSE name, account count, blocked count, at-risk count, avg blocker age (days), M9 this month. Load bar shows account count vs theatre average. Red highlight if blocked_count > 5.

**`/weekly`** — Movement Digest  
Fetches `/api/weekly-movements?theatre=&date=`. Sections: New M9 ✓ (green), M8 Started → (cyan), Newly Blocked 🛑 (red), Resolved ✓ (green). Date picker defaults to current week (Mon–Sun). Previous week button. Perfect for Monday standups.

**`/compare`** — Theatre Comparison  
Fetches `/api/compare`. 4-column layout: EMEA · JAPAC · AMER · LATAM. Rows: M9 total, M9 this week, In progress (M8 started), Blocked, At risk, SLA overdue, 4-week velocity. Export CSV button for QBR. Theatre filter pills hidden (shows all by design).

**Nav order:** Ops · Blockers · Forecast · Daily · Audit · CSE · Weekly · Compare

---

## API Endpoints (New)

### `GET /api/health-summary`
```json
{
  "EMEA":  {"status": "green", "m9": 43, "blocked": 7, "at_risk": 12},
  "JAPAC": {"status": "amber", "m9": 28, "blocked": 3, "at_risk": 5},
  "AMER":  {"status": "red",   "m9": 19, "blocked": 8, "at_risk": 4},
  "LATAM": {"status": "green", "m9": 11, "blocked": 1, "at_risk": 2}
}
```
Status logic: `red` if blocked>5 OR any SLA overdue; `amber` if blocked>2 OR any SLA within 3 days; else `green`.

### `GET /api/cse-workload?theatre=`
```json
[{"cse": "Jane Doe", "account_count": 9, "blocked_count": 2, "at_risk_count": 1,
  "avg_blocker_age_days": 14, "m9_this_month": 3}]
```

### `GET /api/weekly-movements?theatre=&date=YYYY-MM-DD`
```json
{
  "week_of": "2026-03-31",
  "new_m9":       [{"account_id": "...", "customer_name": "...", "cse": "...", "m9_actual": "..."}],
  "m8_started":   [...],
  "newly_blocked": [...],
  "resolved":     [...]
}
```
`date` param = any date within the target week. Defaults to current week.

### `GET /api/compare`
```json
{"theatres": [
  {"theatre": "EMEA", "m9_total": 43, "m9_this_week": 5, "blocked": 7,
   "at_risk": 12, "sla_overdue": 2, "velocity_4w": [3,5,4,5]}
]}
```

---

## UX Features

| Feature | Where | Implementation |
|---|---|---|
| **Theatre health bar** | Nav (all pages) | `healthBar()` in `initNav`. Fetches `/api/health-summary`. 🟢🟡🔴 pills. |
| **Blocker age badge** | Blockers, CSE, Weekly | `S.blockerAge(signal_date)` — pure fn, inline badge |
| **SLA countdown** | Account modal, Forecast, Ops | `S.slaCountdown(m3,m8,m9)` — pure fn, progress badge |
| **Call prep brief** | Account modal, Blockers expand | Fields: last contact, next action owner, days since milestone moved |
| **Sync summary toast** | Daily, Ops (after refresh) | `S.syncSummary(events)` — dismissible, auto-hides 8s |
| **Export CSV** | Audit, Compare | `S.exportCSV(rows, filename)` — pure fn, client-side |

---

## Testing Strategy

### TDD Order

1. **API endpoints** — 4 new endpoints, TestClient + temp DB (same pattern as `test_dashboard_api.py`)
2. **Pure JS functions** — `slaCountdown`, `blockerAge`, `exportCSV` via Node.js assert (zero browser)
3. **`solstice.js` components** — build against passing tests
4. **Pages** — build each page on top of verified components
5. **Integration** — run all 8 pages, verify nav/search/modal end-to-end

### Test Files

| File | What |
|---|---|
| `tests/test_api_health_summary.py` | Status logic, thresholds, SLA overdue detection |
| `tests/test_api_cse_workload.py` | Per-CSE aggregation, avg blocker age |
| `tests/test_api_weekly_movements.py` | Movement detection, date range, empty week |
| `tests/test_api_compare.py` | 4-theatre data, velocity calculation |
| `tests/test_dashboard_api.py` | Existing + new routes |
| `tests/js/test_pure_fns.js` | `slaCountdown`, `blockerAge`, `exportCSV` via Node |

All existing 285 tests must stay green throughout build.

### Tailwind CDN Verification
Before building any page: `curl -I https://cdn.tailwindcss.com` from the target machine. If blocked: fall back to inline CSS utility classes matching the design tokens. Decision is made once, applied everywhere.

---

## Build Sequence

1. Tailwind CDN test
2. `solstice.css` — tokens
3. API endpoints (TDD) — all 4 new + tests
4. `solstice.js` — components (TDD pure fns first)
5. Pages — in order: ops → blockers → forecast → daily → audit → cse → weekly → compare
6. Delete old brainstorm files, v1 references, dead code
7. Update `dashboard.py` routes for new pages
8. Update `CLAUDE.md` — new architecture, `solstice.js` API, 8-page structure
9. Commit + push to new GitHub remote

---

## GitHub Readiness

Before push:
- Clean `.gitignore` — exclude `data/solstice.db`, `data/state.json`, `data/*.csv`, `.superpowers/`
- `README.md` — setup instructions, page map, how to run
- `requirements.txt` — pinned versions
- All 285+ tests green
- No credentials, no personal data in repo
