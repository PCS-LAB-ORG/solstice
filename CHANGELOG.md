# Solstice Changelog

---

## v2.0.0 — Full Dashboard Overhaul (2026-04-21)

25 commits. Solstice v2 — production-ready ops dashboard.

### Design System
- **Centralized CSS**: `.bsec` / `.shdr` / `.sbody` / `.reg-hdr` / `.arow` / `.move` / `.expand-panel` all moved into `solstice.css` — single source of truth for all pages
- **`S.toggleSec`** shared helper in `solstice.js` — consistent collapse behavior across every page
- **Global search centered** in nav bar — pill shape, expands on focus
- All pages (ops, blockers, forecast, daily, weekly, cse, audit) now use the same design language

### Forecast Page
- **Churn toggle**: excludes 147 churned accounts with stale M9 dates by default — counter shows `131 active · 11 churned`
- **Revised confidence logic**: HIGH (M8+Green+not blocked) / MED (M8+Yellow or at_risk / M8 not started+Green+signal green) / LOW / CHURN (strikethrough grey)
- **Overdue section**: expandable, collapsed by default, grouped by theatre — same design as blockers
- **Dynamic counter** on M9 targets card — updates live on filter/toggle changes
- Two JS syntax bugs fixed (unescaped single quotes crashing script parse)

### Blockers Page
- **Expanded panel** gains: Last Edited (by + date, domain stripped), Project Status, M1/M3/M5 milestone details
- **Upgrade notes priority**: `upgrade_notes` → `health_notes` → `status_detail`, placeholder values (`tbd`, `n/a`, `—`) filtered
- All sections collapsed by default

### Audit / M0 Tracking
- **M0 Kickoff** added to `_DC_MILESTONE_WATCH` — future M0 changes now tracked in `status_history`
- **1620 M0 rows backfilled** into `status_history` using earliest known event per account as proxy timestamp

### M1 Action Plan
- **Ollama AI removed** — 4 round-trips per page load replaced with actual `upgrade_notes` from accounts
- Placeholder values (`tbd`, `n/a`) skipped; falls through to `health_notes` → `status_detail`

### Data / Parser
- **`self_hosted` subtype** now reads `PC_SAAS_vs_SH` column (not just status_detail keywords) — 4 SH Only accounts correctly classified (all currently churning, so churn takes priority)
- **`_derive_subtype`** excludes `core_rep_blocking`, `legal_blocker`, `active_deal` from SH Only override
- **`_EMPTY` sentinel** aligned: `"tbd."` added to both frontend and backend filter sets
- **Churn filter** in forecast API: `subtype`, `signal` fields added to response

### Code Quality (from code review)
- `_isChurn` dead `signal==='churn'` branch removed
- `setT()` only removes `act` from theatre pills `[data-t]` — churn toggle state preserved on switch
- Overdue toggle wired via `addEventListener` instead of unsafe inline onclick string
- Dead `toggleSec()` function removed from `daily.html`
- Duplicate shared CSS removed from `forecast.html`

---

## v1.0.0 — Initial Dashboard (2026-03-01 to 2026-04-20)

- FastAPI + SQLite + vanilla JS
- 8-page ops dashboard: Ops, Blockers, Forecast, Daily, Audit, CSE, Weekly, Compare
- DC CSE Tracker as single source of truth (ADC + Google Drive)
- M1–M9 milestone tracking, signal/subtype classification
- Global account search, account detail modal
- SLA framework (M3→M8 ≤14d, M8→M9 ≤28d)
- Theatre health bar, sync summary toast
