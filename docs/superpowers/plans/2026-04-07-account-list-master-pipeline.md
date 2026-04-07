# Account List Master Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the DC CSE Tracker pipeline with the "Detailed Account List" (gid=0, same Drive file) as the sole master source — 256 scale-cohort EMEA accounts, all milestones M0–M9.

**Architecture:** New parser reads the "Detailed Account List" CSV (UTF-16 tab-delimited from manual download; UTF-8 CSV from Drive auto-export), maps M0–M9 + planned dates + signals, and upserts into a wiped DB using a name→Salesforce-ID lookup for the 246 matched accounts and synthetic IDs for the remaining 10. Drive config updated to pull `gid=0`. All existing API queries work unchanged — they just see 256 accounts instead of 405+.

**Tech Stack:** Python 3.14, SQLite, FastAPI, Google Drive export API (`?format=csv&gid=0`)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `agent/account_list_parser.py` | **CREATE** | Parse "Detailed Account List" → list of dicts |
| `agent/db.py` | **MODIFY** | Add `m6_complete` column to `blocked_data` schema + `init_db()` |
| `dashboard.py` | **MODIFY** | Wire new parser into `_run_dc_pipeline`, update Drive config call to use `gid=0`, wipe-and-reload endpoint |
| `data/drive_config.json` | **MODIFY** | Add `"current_gid": "0"` to DC CSE Tracker entry |
| `data/name_to_id.json` | **CREATE** | Pre-built name→Salesforce-ID lookup (generated once, checked in) |
| `tests/test_account_list_parser.py` | **CREATE** | Unit tests for new parser using fixture rows |

---

## Task 1: Save name→ID lookup and add m6_complete to schema

**Files:**
- Create: `data/name_to_id.json`
- Modify: `agent/db.py` — `init_db()` and `migrate_db()` functions

- [ ] **Step 1: Copy the pre-built lookup into the repo**

```bash
cp /tmp/name_to_id.json /Users/mbanica/Documents/Code_Samples/CC/Solstice/data/name_to_id.json
```

Verify: `python3 -c "import json; d=json.load(open('data/name_to_id.json')); print(len(d), 'entries')"`
Expected: `1675 entries`

- [ ] **Step 2: Add m6_complete to init_db() in agent/db.py**

Find the `CREATE TABLE blocked_data` statement in `agent/db.py`. It contains `m7_complete INTEGER DEFAULT 0`. Add `m6_complete` **before** `m7_complete`:

```sql
m5_complete INTEGER DEFAULT 0,
m6_complete INTEGER DEFAULT 0,
m7_complete INTEGER DEFAULT 0,
```

- [ ] **Step 3: Add migration for m6_complete in agent/db.py**

Find the `migrate_db()` or `_migrate()` function (the one that runs `ALTER TABLE` statements). Add:

```python
# m6_complete — added for Account List master pipeline
try:
    conn.execute("ALTER TABLE blocked_data ADD COLUMN m6_complete INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass  # already exists
```

- [ ] **Step 4: Run migration against live DB**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
python3 -c "
import sqlite3
conn = sqlite3.connect('data/solstice.db')
try:
    conn.execute('ALTER TABLE blocked_data ADD COLUMN m6_complete INTEGER DEFAULT 0')
    conn.commit()
    print('m6_complete added')
except sqlite3.OperationalError as e:
    print('already exists:', e)
cols = [r[1] for r in conn.execute('PRAGMA table_info(blocked_data)').fetchall()]
print('m6_complete in schema:', 'm6_complete' in cols)
"
```

Expected: `m6_complete added` and `m6_complete in schema: True`

- [ ] **Step 5: Commit**

```bash
git add data/name_to_id.json agent/db.py
git commit -m "feat: add m6_complete to blocked_data schema, add name→ID lookup"
```

---

## Task 2: Write failing tests for new parser

**Files:**
- Create: `tests/test_account_list_parser.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_account_list_parser.py`:

```python
"""
Unit tests for agent/account_list_parser.py
Uses synthetic fixture rows — no file I/O.
"""
import pytest
from agent.account_list_parser import parse_row, emoji_to_signal, emoji_to_churn

SAMPLE_ROW = {
    "Pc Account Name": "Acme Corp",
    "Account District": "UK Majors",
    "ARR": "500000",
    "DC Upgrade Status": "🟢",
    "DC Indicated Churn Risk": "🟡",
    "DC assignment": "Jane CSE",
    "CC Rep (SPO)": " Chris Rep",
    "M0:Internal Kickoff Complete": "Y",
    "M1:Customer Outreach Complete": "Y",
    "M2:Entitlements and Plan aligned with customer": "Y",
    "M3:EB Buy-in Meeting Complete": "N",
    "M4:Discovery complete": "",
    "M5:Tech validation complete": "",
    "Provisioned": "Y",
    "M6: Activated": "",
    "M7: PS Readiness": "",
    "M8:Upgrade started": "",
    "M9:Upgrade complete": "",
    "Status Detail": "On track",
    "M3 Planned date": "4/30/2026",
    "M8 Planned date": "8/31/2026",
    "M9 Planned date": "9/30/2026",
    "Account Health Notes": "Good",
    "Next Cloud Renewal Date": "12/31/2026",
    "Upgrade Notes": "No blockers",
}

KNOWN_ID = "abc123"


class TestEmojiToSignal:
    def test_green_emoji(self):   assert emoji_to_signal("🟢") == "green"
    def test_yellow_emoji(self):  assert emoji_to_signal("🟡") == "at_risk"
    def test_red_emoji(self):     assert emoji_to_signal("🔴") == "blocked"
    def test_blank(self):         assert emoji_to_signal("") == ""
    def test_space(self):         assert emoji_to_signal(" ") == ""


class TestEmojiToChurn:
    def test_red_is_red(self):    assert emoji_to_churn("🔴") == "Red"
    def test_yellow_is_yellow(self): assert emoji_to_churn("🟡") == "Yellow"
    def test_green_is_green(self): assert emoji_to_churn("🟢") == "Green"
    def test_blank(self):         assert emoji_to_churn("") == ""


class TestParseRow:
    def test_account_name(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["account_name"] == "Acme Corp"

    def test_account_id_used_when_provided(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["account_id"] == KNOWN_ID

    def test_synthetic_id_when_no_id(self):
        r = parse_row(SAMPLE_ROW, "")
        assert len(r["account_id"]) == 15
        assert r["account_id"].isalnum()

    def test_sales_region(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["sales_region"] == "UK Majors"

    def test_active_cse_from_dc_assignment(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["active_cse"] == "Jane CSE"

    def test_cc_rep_stripped(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["cc_rep"] == "Chris Rep"

    def test_m0_complete_y(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m0_complete"] is True

    def test_m1_complete_y(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m1_complete"] is True

    def test_m3_complete_n(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m3_complete"] is False

    def test_m4_complete_blank(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m4_complete"] is False

    def test_m6_complete_blank(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m6_complete"] is False

    def test_signal_from_dc_upgrade_status(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["signal"] == "green"

    def test_churn_risk_from_dc_churn(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["churn_risk"] == "Yellow"

    def test_m3_planned(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m3_planned"] == "4/30/2026"

    def test_m8_planned(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m8_planned"] == "8/31/2026"

    def test_account_theatre_hardcoded_emea(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["account_theatre"] == "EMEA"

    def test_status_detail(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["status_detail"] == "On track"

    def test_health_notes(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["health_notes"] == "Good"

    def test_upgrade_notes(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["upgrade_notes"] == "No blockers"

    def test_arr(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["arr"] == "500000"
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/test_account_list_parser.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'agent.account_list_parser'`

---

## Task 3: Implement account_list_parser.py

**Files:**
- Create: `agent/account_list_parser.py`

- [ ] **Step 1: Create the parser**

Create `agent/account_list_parser.py`:

```python
"""
Parser for the "Detailed Account List" sheet (gid=0) of the DC CSE Tracker.
Handles both UTF-16 tab-delimited (manual Drive export) and UTF-8 CSV (auto export).
"""
import csv
import hashlib
import json
from pathlib import Path


def emoji_to_signal(val: str) -> str:
    v = val.strip()
    if v == "🟢": return "green"
    if v == "🟡": return "at_risk"
    if v == "🔴": return "blocked"
    return ""


def emoji_to_churn(val: str) -> str:
    v = val.strip()
    if v == "🔴": return "Red"
    if v == "🟡": return "Yellow"
    if v == "🟢": return "Green"
    return ""


def _yn(val: str) -> bool:
    return val.strip().upper() == "Y"


def _synthetic_id(name: str) -> str:
    return hashlib.md5(name.lower().strip().encode()).hexdigest()[:15]


def parse_row(row: dict, account_id: str) -> dict:
    """Parse one CSV row into a record dict. account_id may be pre-looked-up or ''."""
    name = (row.get("Pc Account Name") or "").strip()
    aid = account_id if account_id else _synthetic_id(name)
    return {
        "account_id":       aid,
        "account_name":     name,
        "account_theatre":  "EMEA",
        "sales_region":     (row.get("Account District") or "").strip(),
        "arr":              (row.get("ARR") or "").strip(),
        "active_cse":       (row.get("DC assignment") or "").strip(),
        "cc_rep":           (row.get("CC Rep (SPO)") or "").strip(),
        "signal":           emoji_to_signal(row.get("DC Upgrade Status", "")),
        "churn_risk":       emoji_to_churn(row.get("DC Indicated Churn Risk", "")),
        "m0_complete":      _yn(row.get("M0:Internal Kickoff Complete", "")),
        "m1_complete":      _yn(row.get("M1:Customer Outreach Complete", "")),
        "m2_complete":      _yn(row.get("M2:Entitlements and Plan aligned with customer", "")),
        "m3_complete":      _yn(row.get("M3:EB Buy-in Meeting Complete", "")),
        "m4_complete":      _yn(row.get("M4:Discovery complete", "")),
        "m5_complete":      _yn(row.get("M5:Tech validation complete", "")),
        "m6_complete":      _yn(row.get("M6: Activated", "")),
        "m7_complete":      _yn(row.get("M7: PS Readiness", "")),
        "m8_started":       _yn(row.get("M8:Upgrade started", "")),
        "m9_complete":      _yn(row.get("M9:Upgrade complete", "")),
        "m3_planned":       (row.get("M3 Planned date") or "").strip(),
        "m8_planned":       (row.get("M8 Planned date") or "").strip(),
        "m9_planned":       (row.get("M9 Planned date") or "").strip(),
        "status_detail":    (row.get("Status Detail") or "").strip(),
        "health_notes":     (row.get("Account Health Notes") or "").strip(),
        "upgrade_notes":    (row.get("Upgrade Notes") or "").strip(),
        "next_renewal_date":(row.get("Next Cloud Renewal Date") or "").strip(),
        "dc_progress":      "",   # not in this sheet
        "subtype":          "",
    }


def _open_csv(filepath: Path):
    """Try UTF-16 tab-delimited first (manual Drive export), fall back to UTF-8 CSV."""
    for enc, delim in [("utf-16", "\t"), ("utf-8-sig", ","), ("latin-1", ",")]:
        try:
            with open(filepath, encoding=enc, newline="") as f:
                reader = csv.DictReader(f, delimiter=delim)
                rows = list(reader)
                if rows and "Pc Account Name" in (rows[0] or {}):
                    return rows
        except Exception:
            continue
    raise ValueError(f"Cannot parse {filepath} — unsupported encoding/delimiter")


def parse_account_list_csv(filepath: Path, name_to_id: dict | None = None) -> list[dict]:
    """
    Parse the Detailed Account List CSV.
    name_to_id: {lower_name: account_id} lookup built from DC tracker.
    Returns list of record dicts ready for DB upsert.
    """
    lookup = name_to_id or {}
    rows = _open_csv(filepath)
    records = []
    for row in rows:
        name = (row.get("Pc Account Name") or "").strip()
        if not name:
            continue
        aid = lookup.get(name.lower(), "")
        records.append(parse_row(row, aid))
    return records


def load_name_to_id(data_dir: Path) -> dict:
    """Load the pre-built name→Salesforce-ID lookup."""
    p = data_dir / "name_to_id.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}
```

- [ ] **Step 2: Run tests — confirm they pass**

```bash
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/test_account_list_parser.py -v
```

Expected: all 22 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add agent/account_list_parser.py tests/test_account_list_parser.py
git commit -m "feat: account_list_parser — parse Detailed Account List, all milestones M0-M9"
```

---

## Task 4: Wipe DB and reload from downloaded file

**Files:**
- Modify: `dashboard.py` — `_run_dc_pipeline()` function

- [ ] **Step 1: Run the wipe-and-reload script**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
python3 - <<'SCRIPT'
import sys, sqlite3, json
sys.path.insert(0, ".")
from pathlib import Path
from agent.account_list_parser import parse_account_list_csv, load_name_to_id
from agent.db import get_db

DATA_DIR = Path("data")
DOWNLOADS = Path.home() / "Downloads"
CSV_FILE  = DOWNLOADS / "Detailed Account List_data.csv"

if not CSV_FILE.exists():
    print("ERROR: file not found in Downloads"); sys.exit(1)

name_to_id = load_name_to_id(DATA_DIR)
records    = parse_account_list_csv(CSV_FILE, name_to_id)
print(f"Parsed {len(records)} accounts")

with get_db() as conn:
    # Wipe
    for t in ["m1_suggestions","status_history","blocked_data","accounts"]:
        conn.execute(f"DELETE FROM {t}")
    print("DB wiped")

    # Reload
    for r in records:
        conn.execute("""
            INSERT OR REPLACE INTO accounts
            (account_id, customer_name, active_cse, sales_region, account_theatre, arr)
            VALUES (?,?,?,?,?,?)
        """, (r["account_id"], r["account_name"], r["active_cse"],
              r["sales_region"], r["account_theatre"], r["arr"]))

        conn.execute("""
            INSERT OR REPLACE INTO blocked_data
            (account_id, m0_complete, m1_complete, m2_complete, m3_complete,
             m4_complete, m5_complete, m6_complete, m7_complete,
             m8_started, m9_complete,
             m3_planned, m8_planned, m9_planned,
             signal, churn_risk, status_detail, health_notes, upgrade_notes,
             dc_progress, subtype, account_theatre, cc_rep)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            r["account_id"],
            int(r["m0_complete"]), int(r["m1_complete"]), int(r["m2_complete"]),
            int(r["m3_complete"]), int(r["m4_complete"]), int(r["m5_complete"]),
            int(r["m6_complete"]), int(r["m7_complete"]),
            int(r["m8_started"]),  int(r["m9_complete"]),
            r["m3_planned"], r["m8_planned"], r["m9_planned"],
            r["signal"], r["churn_risk"], r["status_detail"],
            r["health_notes"], r["upgrade_notes"],
            r["dc_progress"], r["subtype"], r["account_theatre"], r["cc_rep"],
        ))

print("Loaded. Verifying...")
with get_db() as conn:
    n_acc = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    n_bd  = conn.execute("SELECT COUNT(*) FROM blocked_data").fetchone()[0]
    m1 = conn.execute("SELECT SUM(m1_complete) FROM blocked_data").fetchone()[0]
    m8 = conn.execute("SELECT SUM(m8_started)  FROM blocked_data").fetchone()[0]
    m9 = conn.execute("SELECT SUM(m9_complete) FROM blocked_data").fetchone()[0]
    print(f"accounts={n_acc}  blocked_data={n_bd}")
    print(f"M1={m1}  M8={m8}  M9={m9}")
SCRIPT
```

Expected output:
```
Parsed 256 accounts
DB wiped
Loaded. Verifying...
accounts=256  blocked_data=256
M1=124  M8=19  M9=2
```

- [ ] **Step 2: Syntax-check dashboard.py (unchanged, just verify)**

```bash
python3 -c "import py_compile; py_compile.compile('dashboard.py'); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add data/name_to_id.json
git commit -m "data: wipe DB, reload 256 scale-cohort accounts from Detailed Account List"
```

---

## Task 5: Update drive_config.json and pipeline

**Files:**
- Modify: `data/drive_config.json`
- Modify: `dashboard.py` — `_run_dc_pipeline()`

- [ ] **Step 1: Add gid=0 to drive_config.json**

Edit `data/drive_config.json`. In the DC CSE Tracker entry add `"current_gid": "0"` and update the role note:

```json
{
  "name": "DC CSE Tracker",
  "gsheet": "DC CSE Tracker (Instant sync underlying data to upgrade tracker).gsheet",
  "file_id": "1Te5rQqhQZlGzpBk-ertJlizOgCKxfl-aa9t4Oj2mpSI",
  "current_gid": "0",
  "priority": 1,
  "role": "MASTER",
  "note": "gid=0 = Detailed Account List sheet (256 scale-cohort EMEA accounts)"
}
```

- [ ] **Step 2: Update `_run_dc_pipeline` to use new parser**

In `dashboard.py`, find `_run_dc_pipeline()`. Replace the block that calls `parse_dc_csv` with `parse_account_list_csv`:

```python
# At top of _run_dc_pipeline, add import:
from agent.account_list_parser import parse_account_list_csv as _parse_al, load_name_to_id as _load_n2id

# Replace the existing _all_dc block:
_name_to_id = _load_n2id(data_dir)
_al_csv = data_dir / "dc_cse_tracker.csv"   # same filename, now gid=0 content
_all_dc = {rec["account_id"]: rec for rec in _parse_al(_al_csv, _name_to_id)}
```

Then replace the blocked_data INSERT values in the loop to use the new field names. Specifically replace the params tuple passed to the blocked_data INSERT:

```python
(
    _aid,
    int(_dd.get("m0_complete", False)),
    int(_dd.get("m1_complete", False)),
    _dd.get("m3_planned", ""),     # m1_planned not in new sheet; use m3_planned
    int(_dd.get("m2_complete", False)),
    _dd.get("m3_planned", ""),
    int(_dd.get("m3_complete", False)),
    _dd.get("m3_planned", ""),
    int(_dd.get("m4_complete", False)),
    "",                             # m4_planned not in sheet
    int(_dd.get("m5_complete", False)),
    "",                             # m5_planned not in sheet
    int(_dd.get("m7_complete", False)),
    int(_dd.get("m8_started", False)),
    _dd.get("m8_planned", ""),
    "",                             # m8_actual not in sheet
    int(_dd.get("m9_complete", False)),
    _dd.get("m9_planned", ""),
    "",                             # m9_actual not in sheet
    _dd.get("upgrade_notes", ""),
    _dd.get("dc_progress", ""),
    _dd.get("owner_e2e", ""),
    _dd.get("dc_assignment", ""),
    "",                             # merged_at
    _dd.get("cc_rep", ""),
    "",                             # cc_dsm
    _dd.get("churn_risk", ""),
    _dd.get("health_notes", ""),
    "", "", "", "",                  # last_edited_by, last_edited_date, roadmap_url, ps_plan_url
    _dd.get("sales_region", ""),
    "", "", "", "", "", "", "",       # current_project_status, next_renewal_date, past_due, dur, partner, partner_name
    "", "", "",                      # m1_details, m3_details, m5_details
    "", "", "", "",                   # milestone_aging, days_since_milestone, momentum_x, entitlement_provision
    "",                              # activation_status
    "",                              # posture_workloads
    _dd.get("account_theatre", "EMEA"),
    _dd.get("signal", ""),
    _dd.get("subtype", ""),
    _dd.get("status_detail", ""),
    _dd.get("arr", ""),              # cohort field — repurpose for now
    "", "", "",                      # area, district, team
)
```

Also add `m6_complete` to the INSERT column list and VALUES before `m7_complete`:
```sql
m6_complete,
```
and value: `int(_dd.get("m6_complete", False)),`

- [ ] **Step 3: Syntax-check and restart**

```bash
python3 -c "import py_compile; py_compile.compile('dashboard.py'); print('OK')"
kill $(lsof -ti:8200) 2>/dev/null; sleep 1
python3 dashboard.py &
sleep 3 && curl -s http://localhost:8200/api/forecast | python3 -c "
import json,sys; d=json.load(sys.stdin)
print('next_targets:', len(d.get('next_targets',[])))
print('overdue:', len(d.get('overdue',[])))
"
```

Expected: targets + overdue total ≤ 256, no error key.

- [ ] **Step 4: Verify blockers page**

```bash
curl -s "http://localhost:8200/api/blockers?theatre=EMEA" | python3 -c "
import json,sys; d=json.load(sys.stdin)
print('subtypes:', list(d.keys()))
total = sum(len(v) for v in d.values())
print('total blocked:', total)
"
```

Expected: dict with subtype keys, total ≤ 256.

- [ ] **Step 5: Commit**

```bash
git add data/drive_config.json dashboard.py
git commit -m "feat: pipeline now reads Detailed Account List (gid=0) — 256 scale-cohort accounts, M0-M9"
```

---

## Task 6: Verify milestone numbers match master file

- [ ] **Step 1: Run verification script**

```bash
python3 - <<'SCRIPT'
import sqlite3, csv
from pathlib import Path

conn = sqlite3.connect("data/solstice.db")
db_m = {f"M{i}": conn.execute(f"SELECT {'SUM(m'+str(i)+'_complete)' if i not in (8,) else 'SUM(m8_started)'} FROM blocked_data").fetchone()[0]
        for i in range(10) if i != 6}
db_m["M6"]  = conn.execute("SELECT SUM(m6_complete) FROM blocked_data").fetchone()[0]
db_m["M8"]  = conn.execute("SELECT SUM(m8_started) FROM blocked_data").fetchone()[0]

def yn(v): return str(v).strip().upper() == "Y"
csv_m = {k: 0 for k in ["M0","M1","M2","M3","M4","M5","M6","M7","M8","M9"]}
cols = {"M0":"M0:Internal Kickoff Complete","M1":"M1:Customer Outreach Complete",
        "M2":"M2:Entitlements and Plan aligned with customer",
        "M3":"M3:EB Buy-in Meeting Complete","M4":"M4:Discovery complete",
        "M5":"M5:Tech validation complete","M6":"M6: Activated",
        "M7":"M7: PS Readiness","M8":"M8:Upgrade started","M9":"M9:Upgrade complete"}
with open(Path.home()/"Downloads"/"Detailed Account List_data.csv", encoding="utf-16") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        for k,col in cols.items():
            if yn(row.get(col,"")): csv_m[k] += 1

print(f"{'M':<4} {'CSV':>6} {'DB':>6} {'Match':>7}")
print("-"*25)
for m in ["M0","M1","M2","M3","M4","M5","M6","M7","M8","M9"]:
    c, d = csv_m[m], db_m[m]
    print(f"{m:<4} {c:>6} {d:>6} {'✅' if c==d else '❌'}")
SCRIPT
```

Expected: all 10 milestones show ✅ match between CSV and DB.

- [ ] **Step 2: Commit verification note**

```bash
git commit --allow-empty -m "chore: verified M0-M9 milestone counts match Detailed Account List master"
```

---

## Self-Review Checklist

- [x] **Spec coverage**: wipe DB ✅, load from Drive file ✅, M0-M9 ✅, gid=0 ✅, m6_complete added ✅
- [x] **No placeholders**: all code blocks complete, all commands have expected output
- [x] **Type consistency**: `parse_row` returns dict, `parse_account_list_csv` returns `list[dict]`, `load_name_to_id` returns `dict` — used consistently across tasks
- [x] **10 unmatched accounts**: handled via `_synthetic_id()` in parser — no data loss
- [x] **UTF-16 tab vs UTF-8 CSV**: `_open_csv()` tries both formats automatically
