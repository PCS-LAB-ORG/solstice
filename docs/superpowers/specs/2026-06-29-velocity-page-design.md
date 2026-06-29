# Velocity Page — Design Spec
**Date:** 2026-06-29
**Status:** Approved

---

## Problem

There is no single view that shows:
1. What milestone activity happened *this week* across all regions at a glance
2. How that velocity has trended over time

The existing `/weekly` page shows account-level movements (which specific accounts moved). The new `/velocity` page shows *counts by milestone type and region* — a digest view suited for exec reporting and weekly check-ins.

---

## Design

### URL and Nav

- Route: `/velocity`
- Static file: `static/velocity.html`
- Nav entry: added between "Weekly" and "Wins" in `S.initNav`

---

### Page Layout

```
[ Theatre pills: All | EMEA | JAPAC | AMER | LATAM ]
[ Time range pills: 4w | 12w | 26w | YTD ]          [ Refresh Now ↻ ]  Updated Jun 29 15:45

── This Week  (Jun 23 – Jun 29) ─────────────────────────────────────────
  Milestone            AMER   EMEA   JAPAC   LATAM
  M1 Outreach            1      1      1      —
  M2 Entitlements        1      2      6      —
  M3 Buy-in              1      3      6      —
  M4 Discovery           2      5      5      —
  M5 Tech Validation     2      4      —      —
  M8 Upgrade Started     3      4      —      —
  M9 Upgrade Complete    2      —      —      1

── Historical Velocity ──────────────────────────────────────────────────
  Milestone            Jun 23  Jun 16  Jun 9  Jun 2  ...
  M1 Outreach             3       5      4      2
  M2 Entitlements         9       8      7      6
  M8 Upgrade Started      7       9      6      8
  M9 Upgrade Complete     3       4      5      2
  (rows with all zeros hidden)
```

---

### Controls

**Theatre pills** — All / EMEA / JAPAC / AMER / LATAM
- Affects only the Historical Velocity table
- "This Week" grid always shows all 4 theatres side by side (comparison is the point)

**Time range pills** — 4w / 12w / 26w / YTD
- Default: 12w
- Controls how many week columns appear in the Historical table
- YTD = weeks since Jan 1 of the current year

**Refresh Now button**
- Top-right, styled as existing pill buttons
- Shows spinner while fetching
- Re-GETs `/api/velocity` with current params and re-renders both sections
- Updates timestamp label below button

---

### "This Week" Grid

- Columns: Milestone | AMER | EMEA | JAPAC | LATAM
- Rows: M1 Outreach, M2 Entitlements, M3 Buy-in, M4 Discovery, M5 Tech Validation, M8 Upgrade Started, M9 Upgrade Complete (M0/M6/M7 omitted)
- Cells: count, or `—` if zero
- M9 non-zero cells: sky-blue badge
- M8 non-zero cells: amber badge
- Other milestones: plain text count
- Subtitle: "Jun 23 – Jun 29" (current Mon–Sun)
- Zero state: "No milestone activity this week" if all cells are zero

---

### Historical Velocity Table

- Rows: milestone types (same 7 as above)
- Columns: week labels (most recent first), e.g. "Jun 23", "Jun 16", "Jun 9"
- Cells: count for that milestone in that week (theatre-filtered)
- Rows with all-zero counts across all weeks: hidden
- Column count: controlled by time range pill (4w = 4 columns, 12w = 12, 26w = 26, YTD = weeks since Jan 1)
- Zero state: "No data for this period" if history is empty

---

## API

### `GET /api/velocity`

**Parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `weeks` | int | 12 | How many weeks of history to return |
| `theatre` | str | "" | Theatre filter for history (empty = all) |

**Response:**

```json
{
  "this_week": {
    "range": "Jun 23 – Jun 29",
    "by_theatre": {
      "AMER":  {"M1 Outreach": 1, "M8 Upgrade Started": 3, "M9 Upgrade Complete": 2},
      "EMEA":  {"M4 Discovery": 5, "M8 Upgrade Started": 4},
      "JAPAC": {"M2 Entitlements": 6, "M3 Buy-in": 6},
      "LATAM": {"M9 Upgrade Complete": 1}
    }
  },
  "history": [
    {"week": "Jun 23", "M1 Outreach": 3, "M2 Entitlements": 9, "M8 Upgrade Started": 7, "M9 Upgrade Complete": 3},
    {"week": "Jun 16", "M1 Outreach": 2, "M2 Entitlements": 8, "M8 Upgrade Started": 9, "M9 Upgrade Complete": 4}
  ],
  "updated_at": "2026-06-29T15:45:00"
}
```

**Data source:** `status_history` JOIN `blocked_data` for `account_theatre`. Theatre filter applies to `history` only. `this_week` always returns all four theatres.

**Week boundary:** Mon 00:00 → Sun 23:59 UTC. Current week = this Monday to today.

---

## Implementation Files

| File | Change |
|---|---|
| `dashboard.py` | Add `GET /api/velocity` endpoint + `GET /velocity` HTML route |
| `static/velocity.html` | New page |
| `static/solstice.js` | Add "velocity" to nav page list |

No schema changes — all data comes from existing `status_history` table.

---

## Out of Scope

- Charting / sparklines (can be added later)
- Per-account drill-down from velocity table (blockers page handles this)
- Email/export of the weekly digest
- Automatic background polling (manual refresh only)
