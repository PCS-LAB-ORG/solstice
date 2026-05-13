# Solstice Changelog

---

## v2.4.0 — Central Technical COE Tracker integration (2026-05-13)

### New
- **`coe_issues` table**: 816 rows from COE Tracker Sheet1 — feature requests and upgrade blockers per account (Issue ID, theatre, area, account name, technical issue, priority, module, status, timeline, outcome, Top 100 flag).
- **`coe_bugs` table**: 745 rows from COE Tracker Cortex Bugs tab — XSUP-linked bugs per account with SPO DC classification and engineering escalation status.
- **`_parse_and_store_coe()`**: parses both sheets from xlsx bytes, drops and repopulates both tables on every Refresh Data call.
- **`drive_config.json`**: Central Technical COE Tracker added (`file_id: 1o0uH_9KrerxzognhRnquucwkrEMl6lzY6nhX13HMG0U`, role: `coe`, sheets: `Sheet1` + `Cortex Bugs`).
- **`_download_live_from_drive()`**: COE Tracker download wired in alongside DC CSE + XSUP pulls — reports `✅ N issues + M bugs synced` or `⚠️` on failure.

---

## v2.3.0 — Parity Gaps DB, M1 Bust-Doors Plan, Data Refresh (2026-05-13)

### New DB Tables
- **`parity_gaps`**: 10 product parity gaps blocking CC upgrades — gap ID, title, description, roadmap ETA. ARR intentionally excluded.
- **`parity_gap_accounts`**: 32 rows linking each parity gap to matched accounts in the tracker — includes M8/M9 status and DC status per account.
- Gaps tracked: ServiceNow connector ($34M ARR blocked), custom rules query language, MSSP multi-tenant mgmt, agent/Defender parity, Azure excessive permissions, China cloud regions, VMware Tanzu, data security scanning, compliance framework linking, misconfiguration detection latency.
- SLB and Cox not found in tracker — flagged as unmatched.

### New Output
- **`outputs/m1_bust_doors_plan.xlsx`**: 14-tab Excel for leadership. Tab 1 = 35 actionable bust-doors accounts (priority, CSE, DC, Rep, DSM, M9 date, why actionable, next step). Tabs 2–14 = 180 excluded accounts grouped by reason (GCP China blocked, churning, do-not-engage, escalation risk, competitive, product gap, just deployed, no usage, timing, partner/MSSP, on hold, red no detail).

### Data Refresh
- `data/dc_cse_tracker.csv` refreshed (2026-05-13).
- `data/xsup_tracker.xlsx` added.
- Removed stale CSVs: `blocked_accounts.csv`, `emea_accounts.csv`, `ps_tracker.csv`.

---

## v2.2.0 — Wins, Scope, CSE M8 view, M0/M1 blockers, DB stability (2026-05-06)

- **New page `/wins`**: M9 complete + M8 active counts by theatre with rate bars. Uses Solstice design system (`kpi-card`, `wtbl`).
- **New page `/scope`**: Full account list with milestone status, theatre filter, signal badges.
- **Blockers page**: Added two new sections at top — *M0 Not Started* (kickoff never happened) and *M0→M1 Stuck* (kickoff done, no action plan yet). Fetches `/api/m0-needed` and `/api/m0-no-m1`.
- **CSE page**: Simplified to show only CSE name + M8 in-flight count, sorted by load. Removed blocked/at-risk/M9 columns. Added `m8_count` to `/api/cse-workload` response.
- **DB stability**: `agent/db.py` — switched `PRAGMA journal_mode` from `WAL` to `DELETE`. WAL mode is incompatible with Docker macOS volume mounts and caused `sqlite3.OperationalError: disk I/O error` on startup. Also added `busy_timeout=10000` and removed `synchronous=NORMAL`.
- **README**: Full operator runbook added — day-to-day workflow, role-based page guide, theatre filter deep-links, disk I/O error recovery, rebuild instructions, SLA threshold reference.

---

## v2.1.2 — Daily page fixes round 2 (2026-04-22)

- **30-Day Trend**: was collapsed by default with hidden body — trend bars never visible. Now open by default.
- **DB populate loop**: `_populate_db()` re-ran on every request (ai_enrichment always 0 after Ollama removal). Fixed to check only blocked_data + status_history.
- **Docker Desktop labels**: added container labels so port 8200 shows as clickable link in Docker Desktop board.

---

## v2.1.1 — DB populate loop fix (2026-04-22)

- **DB populate loop**: `_populate_db()` was re-running on every API request because `ai_enrichment` count was always 0 after Ollama removal. Check now only requires `blocked_data + status_history > 0`. DB populates once on startup, stops.

---

## v2.1.0 — Docker + Daily page fixes (2026-04-21)

7 commits since v2.0.0.

- **Docker**: `Dockerfile` + `docker-compose.yml` — `docker compose up -d` is now the only way to run. `data/` volume-mounted so DB and CSVs persist. ADC credentials mounted for Google Drive refresh.
- **Drive fallback**: `_download_from_drive()` falls back to `drive_config.json` MASTER entry when `.gsheet` file is not mounted (Docker environment). Refresh Data now works without Google Drive Desktop.
- **README**: full rewrite — Docker-first, step-by-step setup, all page URLs, architecture, design system reference.
- **Daily page — collapse bug**: `.sec-count` → `.shdr-cnt` mismatch after design refactor caused `querySelector` to return null → TypeError → "Error loading" in upgrades section. Fixed.
- **Daily page — font**: section headers were `font-family: var(--mono)` (JetBrains Mono) — switched to Plus Jakarta Sans 700 matching all other pages. Monospace was also causing right-column clipping on move cards.
- **Daily page — count badges**: section counts ("2", "24") were plain black text. Now sky-blue rounded pill badges matching KPI aesthetic. Regressions count stays red.

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
