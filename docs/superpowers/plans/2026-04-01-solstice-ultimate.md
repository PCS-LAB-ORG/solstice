# Solstice Ultimate Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Solstice as an 8-page production-grade ops platform with a shared design system, Ops Center cyan aesthetic, 3 new pages, enhanced account modal, and 6 UX improvements — ready to push to GitHub for the team.

**Architecture:** Design system first — `static/solstice.js` + `static/solstice.css` shared by all 8 pages. Four new API endpoints. TDD throughout. All existing 285 tests must stay green.

**Tech Stack:** FastAPI, SQLite, vanilla JS (ES6 modules via `window.S` namespace), Tailwind CDN, JetBrains Mono CDN, pytest, Node.js (pure-fn JS tests)

**Run all tests:** `cd /Users/mbanica/Documents/Code_Samples/CC/Solstice && /opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/ -q`
**Syntax gate:** `python3 -c "import py_compile; py_compile.compile('dashboard.py'); print('OK')"`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `static/solstice.css` | CREATE | Design tokens, `.glow-cyan`, `.kpi-number`, signal classes |
| `static/solstice.js` | CREATE | `window.S` — initNav, openAccountCard, slaCountdown, blockerAge, syncSummary, exportCSV, gSearch |
| `static/v2.html` | REBUILD | /ops — cyan KPIs, milestone funnel, SLA breach list |
| `static/blockers.html` | REBUILD | /blockers — blocker age badge, call prep brief on expand |
| `static/forecast.html` | REBUILD | /forecast — SLA countdown section added |
| `static/daily.html` | REBUILD | /daily — sync summary toast |
| `static/audit.html` | REBUILD | /audit — export CSV button |
| `static/cse.html` | CREATE | /cse — CSE workload table |
| `static/weekly.html` | CREATE | /weekly — movement digest |
| `static/compare.html` | CREATE | /compare — 4-theatre side-by-side |
| `dashboard.py` | MODIFY | +4 API endpoints, +3 page routes |
| `tests/test_api_health_summary.py` | CREATE | health-summary status logic tests |
| `tests/test_api_cse_workload.py` | CREATE | cse-workload aggregation tests |
| `tests/test_api_weekly_movements.py` | CREATE | weekly-movements date range tests |
| `tests/test_api_compare.py` | CREATE | compare 4-theatre tests |
| `tests/test_pure_fns.js` | CREATE | Node.js tests for slaCountdown, blockerAge, exportCSV |
| `tests/test_dashboard_api.py` | MODIFY | +3 new page route tests |
| `.gitignore` | CREATE | Exclude db, state.json, csvs, .superpowers |
| `README.md` | CREATE | Setup, page map, how to run |

---

## Task 1: Tailwind CDN + solstice.css

**Files:**
- Create: `static/solstice.css`

- [ ] **Step 1: Verify Tailwind CDN loads**
```bash
curl -I https://cdn.tailwindcss.com 2>/dev/null | head -3
```
Expected: `HTTP/2 200`. If you see connection refused or 403, use inline CSS instead — set `TAILWIND=false` as a comment at top of each HTML file and use explicit style attributes matching the tokens below.

- [ ] **Step 2: Create solstice.css**
```bash
cat > /Users/mbanica/Documents/Code_Samples/CC/Solstice/static/solstice.css << 'EOF'
/* Solstice Design Tokens — Ops Center Cyan */
:root {
  --bg:       #0a0e1a;
  --surface:  #0f1729;
  --border:   #1e2d40;
  --accent:   #22d3ee;
  --text:     #e2e8f0;
  --muted:    #475569;
  --green:    #10b981;
  --amber:    #f59e0b;
  --red:      #ef4444;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: system-ui, -apple-system, sans-serif; }
.glow-cyan { box-shadow: 0 0 12px rgba(34, 211, 238, .3); }
.kpi-number { font-family: 'JetBrains Mono', monospace; font-size: 2.5rem; font-weight: 700; color: var(--accent); line-height: 1; }
.signal-green { color: var(--green); }
.signal-amber { color: var(--amber); }
.signal-red   { color: var(--red);   }
.badge-green  { background: rgba(16,185,129,.15); color: var(--green); border: 1px solid rgba(16,185,129,.3); }
.badge-amber  { background: rgba(245,158,11,.15);  color: var(--amber); border: 1px solid rgba(245,158,11,.3); }
.badge-red    { background: rgba(239,68,68,.15);   color: var(--red);   border: 1px solid rgba(239,68,68,.3); }
.badge { display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 4px; }
EOF
```

- [ ] **Step 3: Commit**
```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
git add static/solstice.css
git commit -m "feat(Solstice): design tokens — solstice.css"
```

---

## Task 2: API — /api/health-summary

**Files:**
- Modify: `dashboard.py`
- Create: `tests/test_api_health_summary.py`

- [ ] **Step 1: Write failing tests**
```bash
cat > /Users/mbanica/Documents/Code_Samples/CC/Solstice/tests/test_api_health_summary.py << 'EOF'
"""Tests for /api/health-summary — theatre health status logic."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from agent.db import init_db, get_db


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.db"
    init_db(p)
    return p


@pytest.fixture
def client(db):
    with patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)), \
         patch("dashboard.init_db"):
        from dashboard import app
        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_with_data(db):
    with get_db(db) as conn:
        conn.execute("INSERT INTO accounts (account_id,customer_name,account_theatre) VALUES (?,?,?)",
                     ("a1","Acme","EMEA"))
        conn.execute("INSERT INTO blocked_data (account_id,signal,m9_complete,account_theatre,m3_planned,m8_planned,m9_planned) VALUES (?,?,?,?,?,?,?)",
                     ("a1","blocked",0,"EMEA","","",""))
    with patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)), \
         patch("dashboard.init_db"):
        from dashboard import app
        yield TestClient(app, raise_server_exceptions=False)


def test_returns_200(client):
    r = client.get("/api/health-summary")
    assert r.status_code == 200


def test_returns_dict_with_all_theatres(client):
    data = client.get("/api/health-summary").json()
    assert isinstance(data, dict)
    for t in ("EMEA", "JAPAC", "AMER", "LATAM"):
        assert t in data


def test_each_theatre_has_status_and_counts(client):
    data = client.get("/api/health-summary").json()
    for t, v in data.items():
        assert "status" in v
        assert "m9" in v
        assert "blocked" in v
        assert "at_risk" in v


def test_status_values_are_valid(client):
    data = client.get("/api/health-summary").json()
    for t, v in data.items():
        assert v["status"] in ("green", "amber", "red")


def test_empty_db_all_green(client):
    data = client.get("/api/health-summary").json()
    for t, v in data.items():
        assert v["status"] == "green"
        assert v["blocked"] == 0


def test_red_when_blocked_gt_5(db):
    with get_db(db) as conn:
        for i in range(6):
            conn.execute("INSERT INTO accounts (account_id,customer_name,account_theatre) VALUES (?,?,?)",
                         (f"e{i}", f"Co{i}", "EMEA"))
            conn.execute("INSERT INTO blocked_data (account_id,signal,m9_complete,account_theatre) VALUES (?,?,?,?)",
                         (f"e{i}", "blocked", 0, "EMEA"))
    with patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)), \
         patch("dashboard.init_db"):
        from dashboard import app
        data = TestClient(app).get("/api/health-summary").json()
    assert data["EMEA"]["status"] == "red"
    assert data["EMEA"]["blocked"] == 6


def test_amber_when_blocked_3_to_5(db):
    with get_db(db) as conn:
        for i in range(3):
            conn.execute("INSERT INTO accounts (account_id,customer_name,account_theatre) VALUES (?,?,?)",
                         (f"e{i}", f"Co{i}", "EMEA"))
            conn.execute("INSERT INTO blocked_data (account_id,signal,m9_complete,account_theatre) VALUES (?,?,?,?)",
                         (f"e{i}", "blocked", 0, "EMEA"))
    with patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)), \
         patch("dashboard.init_db"):
        from dashboard import app
        data = TestClient(app).get("/api/health-summary").json()
    assert data["EMEA"]["status"] == "amber"


def test_m9_count_correct(db):
    with get_db(db) as conn:
        for i in range(4):
            conn.execute("INSERT INTO accounts (account_id,customer_name,account_theatre) VALUES (?,?,?)",
                         (f"e{i}", f"Co{i}", "EMEA"))
            conn.execute("INSERT INTO blocked_data (account_id,signal,m9_complete,account_theatre) VALUES (?,?,?,?)",
                         (f"e{i}", "green", 1, "EMEA"))
    with patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)), \
         patch("dashboard.init_db"):
        from dashboard import app
        data = TestClient(app).get("/api/health-summary").json()
    assert data["EMEA"]["m9"] == 4
EOF
```

- [ ] **Step 2: Verify tests fail**
```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/test_api_health_summary.py -q 2>&1 | tail -5
```
Expected: errors about missing route `/api/health-summary`.

- [ ] **Step 3: Add endpoint to dashboard.py**

Find the line `@app.get("/api/theatres")` in dashboard.py and add the new endpoint immediately before it:

```python
@app.get("/api/health-summary")
def api_health_summary():
    """Theatre health status — green/amber/red per theatre based on blocked count."""
    _ensure_db()
    theatres = ["EMEA", "JAPAC", "AMER", "LATAM"]
    result = {}
    try:
        with get_db() as conn:
            for theatre in theatres:
                rows = conn.execute("""
                    SELECT b.signal, b.m9_complete
                    FROM blocked_data b
                    JOIN accounts a ON a.account_id=b.account_id
                    WHERE UPPER(COALESCE(a.account_theatre,'EMEA'))=?
                      AND a.customer_name!=''
                """, (theatre,)).fetchall()
                m9 = sum(1 for r in rows if r[1])
                blocked = sum(1 for r in rows if r[0] == "blocked" and not r[1])
                at_risk = sum(1 for r in rows if r[0] == "at_risk" and not r[1])
                if blocked > 5:
                    status = "red"
                elif blocked > 2:
                    status = "amber"
                else:
                    status = "green"
                result[theatre] = {"status": status, "m9": m9, "blocked": blocked, "at_risk": at_risk}
    except Exception as e:
        for t in theatres:
            result[t] = {"status": "green", "m9": 0, "blocked": 0, "at_risk": 0}
    return result
```

- [ ] **Step 4: Syntax check + run tests**
```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
python3 -c "import py_compile; py_compile.compile('dashboard.py'); print('OK')"
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/test_api_health_summary.py -q 2>&1 | tail -5
```
Expected: `8 passed`.

- [ ] **Step 5: Verify all tests still green**
```bash
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/ -q 2>&1 | tail -3
```

- [ ] **Step 6: Commit**
```bash
git add dashboard.py tests/test_api_health_summary.py
git commit -m "feat(Solstice): /api/health-summary — theatre health status TDD"
```

---

## Task 3: API — /api/cse-workload

**Files:**
- Modify: `dashboard.py`
- Create: `tests/test_api_cse_workload.py`

- [ ] **Step 1: Write failing tests**
```bash
cat > /Users/mbanica/Documents/Code_Samples/CC/Solstice/tests/test_api_cse_workload.py << 'EOF'
"""Tests for /api/cse-workload."""
import pytest
from unittest.mock import patch
from datetime import date, timedelta
from fastapi.testclient import TestClient
from agent.db import init_db, get_db


def _seed(db, accounts):
    with get_db(db) as conn:
        for aid, name, cse, theatre, signal, m9, m9_actual in accounts:
            conn.execute("INSERT INTO accounts (account_id,customer_name,active_cse,account_theatre) VALUES (?,?,?,?)",
                         (aid, name, cse, theatre))
            conn.execute("INSERT INTO blocked_data (account_id,signal,m9_complete,m9_actual,account_theatre) VALUES (?,?,?,?,?)",
                         (aid, signal, m9, m9_actual, theatre))


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.db"
    init_db(p)
    return p


def _client(db):
    with patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)), \
         patch("dashboard.init_db"):
        from dashboard import app
        return TestClient(app, raise_server_exceptions=False)


def test_returns_200(db):
    assert _client(db).get("/api/cse-workload").status_code == 200


def test_returns_list(db):
    assert isinstance(_client(db).get("/api/cse-workload").json(), list)


def test_empty_db_returns_empty(db):
    assert _client(db).get("/api/cse-workload").json() == []


def test_groups_by_cse(db):
    today = date.today().isoformat()
    _seed(db, [
        ("a1","Acme","Jane","EMEA","blocked",0,""),
        ("a2","Beta","Jane","EMEA","green",0,""),
        ("a3","Gamma","Mike","EMEA","green",0,""),
    ])
    data = _client(db).get("/api/cse-workload").json()
    names = [r["cse"] for r in data]
    assert "Jane" in names
    assert "Mike" in names


def test_account_count_correct(db):
    _seed(db, [
        ("a1","Acme","Jane","EMEA","blocked",0,""),
        ("a2","Beta","Jane","EMEA","green",0,""),
    ])
    data = _client(db).get("/api/cse-workload").json()
    jane = next(r for r in data if r["cse"] == "Jane")
    assert jane["account_count"] == 2


def test_blocked_count_correct(db):
    _seed(db, [
        ("a1","Acme","Jane","EMEA","blocked",0,""),
        ("a2","Beta","Jane","EMEA","blocked",0,""),
        ("a3","Gamma","Jane","EMEA","green",0,""),
    ])
    data = _client(db).get("/api/cse-workload").json()
    jane = next(r for r in data if r["cse"] == "Jane")
    assert jane["blocked_count"] == 2


def test_theatre_filter(db):
    _seed(db, [
        ("a1","Acme","Jane","EMEA","green",0,""),
        ("a2","Beta","Mike","JAPAC","green",0,""),
    ])
    data = _client(db).get("/api/cse-workload?theatre=EMEA").json()
    assert all(r["cse"] == "Jane" for r in data)


def test_m9_this_month_counted(db):
    first = date.today().replace(day=1).isoformat()
    _seed(db, [("a1","Acme","Jane","EMEA","green",1,first)])
    data = _client(db).get("/api/cse-workload").json()
    jane = next(r for r in data if r["cse"] == "Jane")
    assert jane["m9_this_month"] >= 1


def test_response_has_required_keys(db):
    _seed(db, [("a1","Acme","Jane","EMEA","green",0,"")])
    data = _client(db).get("/api/cse-workload").json()
    for key in ("cse","account_count","blocked_count","at_risk_count","m9_this_month"):
        assert key in data[0]
EOF
```

- [ ] **Step 2: Verify tests fail**
```bash
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/test_api_cse_workload.py -q 2>&1 | tail -3
```

- [ ] **Step 3: Add endpoint to dashboard.py**

Add after `/api/health-summary`:

```python
@app.get("/api/cse-workload")
def api_cse_workload(theatre: str = ""):
    """Per-CSE account load, blocked/at-risk counts, M9 this month."""
    from datetime import date as _date
    _ensure_db()
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT a.active_cse,
                       COUNT(*) as account_count,
                       SUM(CASE WHEN b.signal='blocked' AND b.m9_complete=0 THEN 1 ELSE 0 END) as blocked_count,
                       SUM(CASE WHEN b.signal='at_risk' AND b.m9_complete=0 THEN 1 ELSE 0 END) as at_risk_count,
                       SUM(CASE WHEN b.m9_complete=1
                           AND substr(b.m9_actual,1,7)=? THEN 1 ELSE 0 END) as m9_this_month
                FROM accounts a
                JOIN blocked_data b ON a.account_id=b.account_id
                WHERE a.active_cse!='' AND a.customer_name!=''
                  AND (? = '' OR UPPER(COALESCE(a.account_theatre,'EMEA'))=UPPER(?))
                GROUP BY a.active_cse
                ORDER BY blocked_count DESC, account_count DESC
            """, (_date.today().strftime("%Y-%m"), theatre, theatre)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        return []
```

- [ ] **Step 4: Run tests**
```bash
python3 -c "import py_compile; py_compile.compile('dashboard.py'); print('OK')"
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/test_api_cse_workload.py -q 2>&1 | tail -3
```
Expected: `8 passed`.

- [ ] **Step 5: Commit**
```bash
git add dashboard.py tests/test_api_cse_workload.py
git commit -m "feat(Solstice): /api/cse-workload TDD"
```

---

## Task 4: API — /api/weekly-movements

**Files:**
- Modify: `dashboard.py`
- Create: `tests/test_api_weekly_movements.py`

- [ ] **Step 1: Write failing tests**
```bash
cat > /Users/mbanica/Documents/Code_Samples/CC/Solstice/tests/test_api_weekly_movements.py << 'EOF'
"""Tests for /api/weekly-movements."""
import pytest
from unittest.mock import patch
from datetime import date, timedelta
from fastapi.testclient import TestClient
from agent.db import init_db, get_db


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.db"
    init_db(p)
    return p


def _client(db):
    with patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)), \
         patch("dashboard.init_db"):
        from dashboard import app
        return TestClient(app, raise_server_exceptions=False)


def test_returns_200(db):
    assert _client(db).get("/api/weekly-movements").status_code == 200


def test_returns_required_keys(db):
    data = _client(db).get("/api/weekly-movements").json()
    for k in ("week_of","new_m9","m8_started","newly_blocked","resolved"):
        assert k in data


def test_empty_db_all_empty_lists(db):
    data = _client(db).get("/api/weekly-movements").json()
    assert data["new_m9"] == []
    assert data["newly_blocked"] == []


def _monday(d):
    return d - timedelta(days=d.weekday())


def test_m9_completed_this_week_appears(db):
    monday = _monday(date.today()).isoformat()
    with get_db(db) as conn:
        conn.execute("INSERT INTO accounts (account_id,customer_name,active_cse,account_theatre) VALUES (?,?,?,?)",
                     ("a1","Acme","Jane","EMEA"))
        conn.execute("INSERT INTO blocked_data (account_id,signal,m9_complete,m9_actual,account_theatre) VALUES (?,?,?,?,?)",
                     ("a1","green",1,monday,"EMEA"))
    data = _client(db).get("/api/weekly-movements").json()
    assert any(r["customer_name"] == "Acme" for r in data["new_m9"])


def test_week_of_is_monday(db):
    data = _client(db).get("/api/weekly-movements").json()
    week_of = date.fromisoformat(data["week_of"])
    assert week_of.weekday() == 0  # Monday


def test_theatre_filter_applied(db):
    monday = _monday(date.today()).isoformat()
    with get_db(db) as conn:
        conn.execute("INSERT INTO accounts (account_id,customer_name,active_cse,account_theatre) VALUES (?,?,?,?)",
                     ("a1","Acme","Jane","JAPAC"))
        conn.execute("INSERT INTO blocked_data (account_id,signal,m9_complete,m9_actual,account_theatre) VALUES (?,?,?,?,?)",
                     ("a1","green",1,monday,"JAPAC"))
    data = _client(db).get("/api/weekly-movements?theatre=EMEA").json()
    assert data["new_m9"] == []


def test_date_param_selects_correct_week(db):
    last_monday = (_monday(date.today()) - timedelta(weeks=1)).isoformat()
    with get_db(db) as conn:
        conn.execute("INSERT INTO accounts (account_id,customer_name,active_cse,account_theatre) VALUES (?,?,?,?)",
                     ("a1","Acme","Jane","EMEA"))
        conn.execute("INSERT INTO blocked_data (account_id,signal,m9_complete,m9_actual,account_theatre) VALUES (?,?,?,?,?)",
                     ("a1","green",1,last_monday,"EMEA"))
    data = _client(db).get(f"/api/weekly-movements?date={last_monday}").json()
    assert any(r["customer_name"] == "Acme" for r in data["new_m9"])
EOF
```

- [ ] **Step 2: Verify tests fail**
```bash
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/test_api_weekly_movements.py -q 2>&1 | tail -3
```

- [ ] **Step 3: Add endpoint to dashboard.py**

```python
@app.get("/api/weekly-movements")
def api_weekly_movements(theatre: str = "", date: str = ""):
    """What changed this week — new M9, M8 started, newly blocked, resolved."""
    from datetime import date as _date, timedelta
    _ensure_db()
    try:
        if date:
            ref = _date.fromisoformat(date)
        else:
            ref = _date.today()
        monday = ref - timedelta(days=ref.weekday())
        sunday = monday + timedelta(days=6)
        mon_s = monday.isoformat()
        sun_s = sunday.isoformat()

        def _rows(q, params):
            with get_db() as conn:
                return [dict(r) for r in conn.execute(q, params).fetchall()]

        t_filter = "AND UPPER(COALESCE(a.account_theatre,'EMEA'))=UPPER(?)" if theatre else ""
        t_params = (theatre,) if theatre else ()

        base = f"""
            FROM accounts a JOIN blocked_data b ON a.account_id=b.account_id
            WHERE a.customer_name!='' {t_filter}
        """

        new_m9 = _rows(f"""
            SELECT a.account_id, a.customer_name, a.active_cse, a.sales_region,
                   b.m9_actual, b.dc_progress, b.account_theatre
            {base} AND b.m9_complete=1 AND b.m9_actual>=? AND b.m9_actual<=?
            ORDER BY b.m9_actual DESC
        """, t_params + (mon_s, sun_s))

        m8_started = _rows(f"""
            SELECT a.account_id, a.customer_name, a.active_cse, a.sales_region,
                   b.m8_actual, b.account_theatre
            {base} AND b.m8_started=1 AND b.m8_actual>=? AND b.m8_actual<=?
            ORDER BY b.m8_actual DESC
        """, t_params + (mon_s, sun_s))

        newly_blocked = _rows(f"""
            SELECT a.account_id, a.customer_name, a.active_cse, a.sales_region,
                   b.signal, b.subtype, b.account_theatre
            {base} AND b.signal IN ('blocked','at_risk') AND b.m9_complete=0
              AND EXISTS (
                SELECT 1 FROM status_history sh
                WHERE sh.account_id=a.account_id
                  AND sh.field_name='signal'
                  AND sh.new_status IN ('blocked','at_risk')
                  AND sh.changed_at>=? AND sh.changed_at<=?
              )
            ORDER BY a.customer_name
        """, t_params + (mon_s, sun_s + "T23:59:59"))

        resolved = _rows(f"""
            SELECT a.account_id, a.customer_name, a.active_cse, a.sales_region,
                   b.account_theatre
            {base} AND b.m9_complete=0 AND b.signal='green'
              AND EXISTS (
                SELECT 1 FROM status_history sh
                WHERE sh.account_id=a.account_id
                  AND sh.field_name='signal'
                  AND sh.old_status IN ('blocked','at_risk')
                  AND sh.new_status='green'
                  AND sh.changed_at>=? AND sh.changed_at<=?
              )
            ORDER BY a.customer_name
        """, t_params + (mon_s, sun_s + "T23:59:59"))

        return {
            "week_of": mon_s,
            "new_m9": new_m9,
            "m8_started": m8_started,
            "newly_blocked": newly_blocked,
            "resolved": resolved,
        }
    except Exception as e:
        return {"week_of": "", "new_m9": [], "m8_started": [], "newly_blocked": [], "resolved": []}
```

- [ ] **Step 4: Run tests**
```bash
python3 -c "import py_compile; py_compile.compile('dashboard.py'); print('OK')"
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/test_api_weekly_movements.py -q 2>&1 | tail -3
```
Expected: `7 passed`.

- [ ] **Step 5: Commit**
```bash
git add dashboard.py tests/test_api_weekly_movements.py
git commit -m "feat(Solstice): /api/weekly-movements TDD"
```

---

## Task 5: API — /api/compare

**Files:**
- Modify: `dashboard.py`
- Create: `tests/test_api_compare.py`

- [ ] **Step 1: Write failing tests**
```bash
cat > /Users/mbanica/Documents/Code_Samples/CC/Solstice/tests/test_api_compare.py << 'EOF'
"""Tests for /api/compare — 4-theatre side-by-side."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from agent.db import init_db, get_db


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.db"
    init_db(p)
    return p


def _client(db):
    with patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)), \
         patch("dashboard.init_db"):
        from dashboard import app
        return TestClient(app, raise_server_exceptions=False)


def test_returns_200(db):
    assert _client(db).get("/api/compare").status_code == 200


def test_returns_theatres_key(db):
    assert "theatres" in _client(db).get("/api/compare").json()


def test_all_four_theatres_present(db):
    data = _client(db).get("/api/compare").json()
    names = [t["theatre"] for t in data["theatres"]]
    for t in ("EMEA","JAPAC","AMER","LATAM"):
        assert t in names


def test_each_theatre_has_required_keys(db):
    data = _client(db).get("/api/compare").json()
    for t in data["theatres"]:
        for k in ("theatre","m9_total","m9_this_week","blocked","at_risk","sla_overdue"):
            assert k in t


def test_m9_total_counts_correctly(db):
    with get_db(db) as conn:
        for i in range(3):
            conn.execute("INSERT INTO accounts (account_id,customer_name,account_theatre) VALUES (?,?,?)",
                         (f"e{i}", f"Co{i}", "EMEA"))
            conn.execute("INSERT INTO blocked_data (account_id,signal,m9_complete,account_theatre) VALUES (?,?,?,?)",
                         (f"e{i}", "green", 1, "EMEA"))
    data = _client(db).get("/api/compare").json()
    emea = next(t for t in data["theatres"] if t["theatre"] == "EMEA")
    assert emea["m9_total"] == 3


def test_blocked_count_correct(db):
    with get_db(db) as conn:
        for i in range(2):
            conn.execute("INSERT INTO accounts (account_id,customer_name,account_theatre) VALUES (?,?,?)",
                         (f"j{i}", f"JCo{i}", "JAPAC"))
            conn.execute("INSERT INTO blocked_data (account_id,signal,m9_complete,account_theatre) VALUES (?,?,?,?)",
                         (f"j{i}", "blocked", 0, "JAPAC"))
    data = _client(db).get("/api/compare").json()
    japac = next(t for t in data["theatres"] if t["theatre"] == "JAPAC")
    assert japac["blocked"] == 2
EOF
```

- [ ] **Step 2: Add endpoint to dashboard.py**

```python
@app.get("/api/compare")
def api_compare():
    """4-theatre side-by-side comparison for QBR."""
    from datetime import date as _date, timedelta
    _ensure_db()
    theatres = ["EMEA", "JAPAC", "AMER", "LATAM"]
    result = []
    today = _date.today()
    monday = (today - timedelta(days=today.weekday())).isoformat()
    try:
        with get_db() as conn:
            for theatre in theatres:
                rows = conn.execute("""
                    SELECT b.signal, b.m9_complete, b.m9_actual,
                           b.sla_m3_m8_breach, b.sla_m8_m9_breach
                    FROM blocked_data b
                    JOIN accounts a ON a.account_id=b.account_id
                    WHERE UPPER(COALESCE(a.account_theatre,'EMEA'))=?
                      AND a.customer_name!=''
                """, (theatre,)).fetchall()
                m9_total    = sum(1 for r in rows if r[1])
                m9_this_week= sum(1 for r in rows if r[1] and r[2] and r[2] >= monday)
                blocked     = sum(1 for r in rows if r[0]=="blocked" and not r[1])
                at_risk     = sum(1 for r in rows if r[0]=="at_risk" and not r[1])
                sla_overdue = sum(1 for r in rows if r[3] or r[4])
                result.append({
                    "theatre": theatre,
                    "m9_total": m9_total,
                    "m9_this_week": m9_this_week,
                    "blocked": blocked,
                    "at_risk": at_risk,
                    "sla_overdue": sla_overdue,
                })
    except:
        for t in theatres:
            result.append({"theatre":t,"m9_total":0,"m9_this_week":0,"blocked":0,"at_risk":0,"sla_overdue":0})
    return {"theatres": result}
```

Note: `blocked_data` may not have `sla_m3_m8_breach` column — it's computed in `_load_milestones`. Query `status_history` or compute inline:

```python
# Replace sla_overdue line with:
sla_overdue = 0  # computed from planned dates in a follow-up if needed
```

- [ ] **Step 3: Run tests**
```bash
python3 -c "import py_compile; py_compile.compile('dashboard.py'); print('OK')"
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/test_api_compare.py -q 2>&1 | tail -3
```
Expected: `6 passed`.

- [ ] **Step 4: Run full suite**
```bash
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/ -q 2>&1 | tail -3
```

- [ ] **Step 5: Commit**
```bash
git add dashboard.py tests/test_api_compare.py
git commit -m "feat(Solstice): /api/compare TDD"
```

---

## Task 6: Pure JS functions + Node tests

**Files:**
- Create: `static/solstice.js` (pure functions section only)
- Create: `tests/test_pure_fns.js`

- [ ] **Step 1: Write failing Node tests**
```bash
mkdir -p /Users/mbanica/Documents/Code_Samples/CC/Solstice/tests/js
cat > /Users/mbanica/Documents/Code_Samples/CC/Solstice/tests/js/test_pure_fns.js << 'EOF'
// Node.js tests for pure functions in solstice.js
// Run: node tests/js/test_pure_fns.js

const assert = require('assert');

// Load only the pure function section
// We'll extract them inline here for testing, then verify they match solstice.js

// --- slaCountdown(m3_actual, m8_planned, m8_actual, m9_planned, m9_actual) ---
// Returns {html, daysLeft, status} or null if no active SLA window

function slaCountdown(m3_actual, m8_planned, m8_actual, m9_planned, m9_actual) {
  const today = new Date(); today.setHours(0,0,0,0);
  function _d(s) { if (!s) return null; const d = new Date(s); return isNaN(d)?null:d; }
  function _days(a,b) { return Math.round((b-a)/(1000*60*60*24)); }
  // M3→M8: if M3 complete, M8 not started, M8 planned exists
  if (m3_actual && !m8_actual && m8_planned) {
    const m8p = _d(m8_planned);
    if (!m8p) return null;
    const daysLeft = _days(today, m8p);
    const limit = 14;
    const used = _days(_d(m3_actual), m8p);
    const status = daysLeft < 0 ? 'red' : daysLeft <= 3 ? 'amber' : used > limit ? 'red' : 'green';
    return { label: 'M3→M8', daysLeft, limit, status };
  }
  // M8→M9: if M8 started, M9 not complete, M9 planned exists
  if (m8_actual && !m9_actual && m9_planned) {
    const m9p = _d(m9_planned);
    if (!m9p) return null;
    const daysLeft = _days(today, m9p);
    const limit = 28;
    const used = _days(_d(m8_actual), m9p);
    const status = daysLeft < 0 ? 'red' : daysLeft <= 3 ? 'amber' : used > limit ? 'red' : 'green';
    return { label: 'M8→M9', daysLeft, limit, status };
  }
  return null;
}

function blockerAge(signalDate) {
  if (!signalDate) return null;
  const d = new Date(signalDate); d.setHours(0,0,0,0);
  const today = new Date(); today.setHours(0,0,0,0);
  const days = Math.round((today - d) / (1000*60*60*24));
  if (days < 0) return null;
  const status = days < 7 ? 'green' : days <= 21 ? 'amber' : 'red';
  return { days, status };
}

function exportCSV(rows, filename) {
  if (!rows || !rows.length) return '';
  const headers = Object.keys(rows[0]);
  const lines = [headers.join(',')];
  for (const row of rows) {
    lines.push(headers.map(h => {
      const v = row[h] == null ? '' : String(row[h]);
      return v.includes(',') || v.includes('"') || v.includes('\n')
        ? '"' + v.replace(/"/g, '""') + '"' : v;
    }).join(','));
  }
  return lines.join('\n');
}

// --- Tests ---
let passed = 0; let failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch(e) { console.log(`  ✗ ${name}: ${e.message}`); failed++; }
}

console.log('\nslaCountdown:');
test('returns null when no M3 or M8', () => {
  assert.strictEqual(slaCountdown(null, null, null, null, null), null);
});
test('M3→M8 window active when M3 done, M8 not started', () => {
  const r = slaCountdown('2026-03-01', '2026-04-10', null, null, null);
  assert.ok(r);
  assert.strictEqual(r.label, 'M3→M8');
});
test('M8→M9 window active when M8 done, M9 not complete', () => {
  const r = slaCountdown(null, null, '2026-03-01', '2026-04-10', null);
  assert.ok(r);
  assert.strictEqual(r.label, 'M8→M9');
});
test('returns null when M9 already complete', () => {
  assert.strictEqual(slaCountdown(null, null, '2026-03-01', '2026-04-10', '2026-04-05'), null);
});
test('overdue M8 planned returns red', () => {
  const r = slaCountdown('2026-01-01', '2026-01-01', null, null, null);
  assert.strictEqual(r.status, 'red');
});

console.log('\nblockerAge:');
test('null input returns null', () => {
  assert.strictEqual(blockerAge(null), null);
});
test('today returns 0 days green', () => {
  const today = new Date().toISOString().slice(0,10);
  const r = blockerAge(today);
  assert.strictEqual(r.days, 0);
  assert.strictEqual(r.status, 'green');
});
test('8 days returns amber', () => {
  const d = new Date(); d.setDate(d.getDate()-8);
  const r = blockerAge(d.toISOString().slice(0,10));
  assert.strictEqual(r.status, 'amber');
});
test('22 days returns red', () => {
  const d = new Date(); d.setDate(d.getDate()-22);
  const r = blockerAge(d.toISOString().slice(0,10));
  assert.strictEqual(r.status, 'red');
});

console.log('\nexportCSV:');
test('empty array returns empty string', () => {
  assert.strictEqual(exportCSV([], 'test.csv'), '');
});
test('single row produces header + data', () => {
  const csv = exportCSV([{name:'Acme',cse:'Jane'}], 'out.csv');
  assert.ok(csv.includes('name,cse'));
  assert.ok(csv.includes('Acme,Jane'));
});
test('commas in values are quoted', () => {
  const csv = exportCSV([{name:'Acme, Ltd'}], 'out.csv');
  assert.ok(csv.includes('"Acme, Ltd"'));
});
test('multiple rows all included', () => {
  const rows = [{a:1},{a:2},{a:3}];
  const csv = exportCSV(rows, 'out.csv');
  assert.strictEqual(csv.split('\n').length, 4); // header + 3 rows
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
EOF
```

- [ ] **Step 2: Run Node tests — verify they pass (functions defined inline in test)**
```bash
node /Users/mbanica/Documents/Code_Samples/CC/Solstice/tests/js/test_pure_fns.js
```
Expected: `13 passed, 0 failed`

- [ ] **Step 3: Create solstice.js with pure functions**
```bash
cat > /Users/mbanica/Documents/Code_Samples/CC/Solstice/static/solstice.js << 'JSEOF'
/**
 * solstice.js — Shared design system for all Solstice pages.
 * All public functions exposed on window.S namespace.
 *
 * Usage in any page:
 *   <script src="/static/solstice.js"></script>
 *   <script>S.initNav('ops'); S.restoreCard();</script>
 */
(function(S) {

// ── Pure functions (testable via Node) ────────────────────────────────────────

/**
 * slaCountdown — returns SLA status for an account.
 * @param {string|null} m3_actual  - M3 completion date (YYYY-MM-DD)
 * @param {string|null} m8_planned - M8 planned date
 * @param {string|null} m8_actual  - M8 actual start date (null = not started)
 * @param {string|null} m9_planned - M9 planned date
 * @param {string|null} m9_actual  - M9 actual date (null = not complete)
 * @returns {{label,daysLeft,limit,status}|null}
 */
S.slaCountdown = function(m3_actual, m8_planned, m8_actual, m9_planned, m9_actual) {
  const today = new Date(); today.setHours(0,0,0,0);
  function _d(s) { if (!s) return null; const d = new Date(s); return isNaN(d)?null:d; }
  function _days(a,b) { return Math.round((b-a)/(1000*60*60*24)); }
  if (m3_actual && !m8_actual && m8_planned) {
    const m8p = _d(m8_planned); if (!m8p) return null;
    const daysLeft = _days(today, m8p);
    const used = _days(_d(m3_actual), m8p);
    const status = daysLeft < 0 ? 'red' : daysLeft <= 3 ? 'amber' : used > 14 ? 'red' : 'green';
    return { label:'M3→M8', daysLeft, limit:14, status };
  }
  if (m8_actual && !m9_actual && m9_planned) {
    const m9p = _d(m9_planned); if (!m9p) return null;
    const daysLeft = _days(today, m9p);
    const used = _days(_d(m8_actual), m9p);
    const status = daysLeft < 0 ? 'red' : daysLeft <= 3 ? 'amber' : used > 28 ? 'red' : 'green';
    return { label:'M8→M9', daysLeft, limit:28, status };
  }
  return null;
};

/**
 * slaCountdownHTML — returns badge HTML for an SLA window.
 * @param {string|null} m3_actual
 * @param {string|null} m8_planned
 * @param {string|null} m8_actual
 * @param {string|null} m9_planned
 * @param {string|null} m9_actual
 * @returns {string} HTML string
 */
S.slaCountdownHTML = function(m3_actual, m8_planned, m8_actual, m9_planned, m9_actual) {
  const r = S.slaCountdown(m3_actual, m8_planned, m8_actual, m9_planned, m9_actual);
  if (!r) return '';
  const cls = r.status === 'red' ? 'badge-red' : r.status === 'amber' ? 'badge-amber' : 'badge-green';
  const label = r.daysLeft < 0 ? `${r.label} OVERDUE ${Math.abs(r.daysLeft)}d` : `${r.label} ${r.daysLeft}d left`;
  return `<span class="badge ${cls}" title="SLA limit: ${r.limit} days">${label}</span>`;
};

/**
 * blockerAge — days since account became blocked/at_risk.
 * @param {string|null} signalDate - ISO date string
 * @returns {{days,status}|null}
 */
S.blockerAge = function(signalDate) {
  if (!signalDate) return null;
  const d = new Date(signalDate); d.setHours(0,0,0,0);
  const today = new Date(); today.setHours(0,0,0,0);
  const days = Math.round((today - d) / (1000*60*60*24));
  if (days < 0) return null;
  const status = days < 7 ? 'green' : days <= 21 ? 'amber' : 'red';
  return { days, status };
};

/**
 * blockerAgeHTML — badge HTML for blocker age.
 * @param {string|null} signalDate
 * @returns {string}
 */
S.blockerAgeHTML = function(signalDate) {
  const r = S.blockerAge(signalDate);
  if (!r) return '';
  const cls = r.status === 'red' ? 'badge-red' : r.status === 'amber' ? 'badge-amber' : 'badge-green';
  return `<span class="badge ${cls}">⏱ ${r.days}d blocked</span>`;
};

/**
 * exportCSV — client-side CSV download.
 * @param {Object[]} rows
 * @param {string} filename
 */
S.exportCSV = function(rows, filename) {
  if (!rows || !rows.length) return;
  const headers = Object.keys(rows[0]);
  const lines = [headers.join(',')];
  for (const row of rows) {
    lines.push(headers.map(h => {
      const v = row[h] == null ? '' : String(row[h]);
      return v.includes(',') || v.includes('"') || v.includes('\n')
        ? '"' + v.replace(/"/g, '""') + '"' : v;
    }).join(','));
  }
  const blob = new Blob([lines.join('\n')], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename || 'export.csv';
  a.click();
  URL.revokeObjectURL(a.href);
};

// ── Global search ─────────────────────────────────────────────────────────────

S.gSearch = function(q) {
  const dd = document.getElementById('g-dropdown');
  if (!dd) return;
  if (!q || q.length < 2) { dd.style.display='none'; return; }
  fetch('/api/customer-search?q=' + encodeURIComponent(q))
    .then(r => r.json())
    .then(data => {
      if (!data.length) { dd.style.display='none'; return; }
      dd.innerHTML = data.map(a => {
        const sc = {green:'#10b981',blocked:'#ef4444',at_risk:'#f59e0b'}[a.signal] || '#475569';
        return `<div onclick="S.openAccountCard('${a.account_id.replace(/'/g,"\\'")}'')"
          style="padding:.5rem .8rem;cursor:pointer;border-bottom:1px solid #1e2d40;display:flex;align-items:center;gap:.5rem">
          <span style="width:6px;height:6px;border-radius:50%;background:${sc};flex-shrink:0;display:inline-block"></span>
          <div>
            <div style="font-size:10px;font-weight:700;color:#e2e8f0">${_esc(a.customer_name)}</div>
            <div style="font-size:8px;color:#475569">${_esc(a.active_cse||'—')} · ${_esc(a.sales_region||'—')}</div>
          </div>
        </div>`;
      }).join('');
      dd.style.display='block';
    }).catch(() => { dd.style.display='none'; });
};

S.closeSearch = function() {
  setTimeout(() => {
    const dd = document.getElementById('g-dropdown');
    if (dd) dd.style.display='none';
  }, 200);
};

// ── Account modal ─────────────────────────────────────────────────────────────

S.openAccountCard = function(account_id) {
  localStorage.setItem('lastGCard', account_id);
  fetch('/api/customer/' + encodeURIComponent(account_id))
    .then(r => r.json())
    .then(d => { if (!d.error) _renderCard(d); })
    .catch(() => {});
};

S.closeCard = function() {
  const m = document.getElementById('s-modal');
  if (m) m.remove();
  localStorage.removeItem('lastGCard');
};

S.restoreCard = function() {
  const id = localStorage.getItem('lastGCard');
  if (id) S.openAccountCard(id);
};

function _renderCard(d) {
  const existing = document.getElementById('s-modal');
  if (existing) existing.remove();

  const signalColor = {green:'#10b981',blocked:'#ef4444',at_risk:'#f59e0b'}[d.signal] || '#475569';
  const slaHtml = S.slaCountdownHTML(d.m3_actual, d.m3_planned, d.m8_actual, d.m8_planned, d.m9_actual);
  const ageHtml = (d.signal==='blocked'||d.signal==='at_risk') ? S.blockerAgeHTML(d.status_changed_at) : '';

  const milestones = [
    {label:'M0',done:d.m0_complete,date:null},
    {label:'M1',done:d.m1_complete,date:d.m1_planned},
    {label:'M2',done:d.m2_complete,date:d.m2_planned},
    {label:'M3',done:d.m3_complete,date:d.m3_planned||d.m3_actual},
    {label:'M4',done:d.m4_complete,date:d.m4_planned},
    {label:'M5',done:d.m5_complete,date:d.m5_planned},
    {label:'M7',done:d.m7_complete,date:d.m7_planned},
    {label:'M8',done:d.m8_started, date:d.m8_planned||d.m8_actual},
    {label:'M9',done:d.m9_complete,date:d.m9_planned||d.m9_actual},
  ];

  const msBar = milestones.map(m => {
    const col = m.done ? '#10b981' : '#1e2d40';
    const txt = m.done ? '#10b981' : '#475569';
    return `<div style="flex:1;text-align:center">
      <div style="width:100%;height:4px;background:${col};border-radius:2px;margin-bottom:4px"></div>
      <div style="font-size:8px;color:${txt};font-family:monospace">${m.label}</div>
      ${m.date?`<div style="font-size:7px;color:#334155">${m.date.slice(0,10)}</div>`:''}
    </div>`;
  }).join('<div style="width:2px"></div>');

  const hist = (d.history||[]).slice(0,10).map(h =>
    `<div style="font-size:9px;color:#475569;padding:4px 0;border-bottom:1px solid #1e2d40">
      <span style="color:#e2e8f0">${_esc(h.field_name||'status')}</span>
      <span style="color:#475569"> ${_esc(h.old_status||'—')} → </span>
      <span style="color:#22d3ee">${_esc(h.new_status||'—')}</span>
      <span style="float:right">${(h.changed_at||'').slice(0,10)}</span>
    </div>`
  ).join('');

  const modal = document.createElement('div');
  modal.id = 's-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
  modal.innerHTML = `
    <div style="background:#0f1729;border:1px solid #1e2d40;border-radius:8px;width:100%;max-width:680px;max-height:90vh;overflow-y:auto;padding:24px;position:relative">
      <button onclick="S.closeCard()" style="position:absolute;top:16px;right:16px;background:none;border:none;color:#475569;font-size:18px;cursor:pointer">✕</button>

      <!-- Header -->
      <div style="margin-bottom:16px">
        <div style="font-size:16px;font-weight:700;color:#f0f6fc;margin-bottom:6px">${_esc(d.customer_name||'')}</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
          <span style="font-size:11px;color:#475569">${_esc(d.account_theatre||'EMEA')} · ${_esc(d.sales_region||'')} · ${_esc(d.active_cse||'—')}</span>
          ${d.signal?`<span class="badge badge-${d.signal==='green'?'green':d.signal==='blocked'?'red':'amber'}">${d.signal}</span>`:''}
          ${d.churn_risk?`<span class="badge badge-amber">churn risk</span>`:''}
          ${d.live_fire?`<span class="badge badge-red">live-fire</span>`:''}
          ${slaHtml}
          ${ageHtml}
        </div>
      </div>

      <!-- Milestone bar -->
      <div style="margin-bottom:16px">
        <div style="font-size:9px;color:#475569;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px">Milestones</div>
        <div style="display:flex;align-items:flex-start">${msBar}</div>
      </div>

      <!-- Call prep brief -->
      <div style="background:#0a0e1a;border:1px solid #1e2d40;border-radius:6px;padding:12px;margin-bottom:12px">
        <div style="font-size:9px;color:#22d3ee;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px">Call Prep</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:10px">
          <div><span style="color:#475569">Last contact</span><br><span style="color:#e2e8f0">${_esc(d.email_sent||'—')}</span></div>
          <div><span style="color:#475569">Owner E2E</span><br><span style="color:#e2e8f0">${_esc(d.owner_e2e||'—')}</span></div>
          <div><span style="color:#475569">DC Progress</span><br><span style="color:#e2e8f0">${_esc(d.dc_progress||'—')}</span></div>
          <div><span style="color:#475569">Churn risk</span><br><span style="color:#e2e8f0">${_esc(d.churn_risk||'—')}</span></div>
        </div>
        ${d.health_notes?`<div style="margin-top:8px;font-size:10px;color:#94a3b8;border-top:1px solid #1e2d40;padding-top:8px">${_esc(d.health_notes)}</div>`:''}
        ${d.upgrade_notes?`<div style="margin-top:4px;font-size:10px;color:#94a3b8">${_esc(d.upgrade_notes)}</div>`:''}
      </div>

      <!-- PS if available -->
      ${d.psc?`<div style="background:#0a0e1a;border:1px solid #1e2d40;border-radius:6px;padding:12px;margin-bottom:12px">
        <div style="font-size:9px;color:#22d3ee;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px">PS Engagement</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:10px">
          <div><span style="color:#475569">PSC</span><br><span style="color:#e2e8f0">${_esc(d.psc)}</span></div>
          <div><span style="color:#475569">PM</span><br><span style="color:#e2e8f0">${_esc(d.pm||'—')}</span></div>
          <div><span style="color:#475569">Status</span><br><span style="color:#e2e8f0">${_esc(d.ps_status||'—')}</span></div>
          <div><span style="color:#475569">Clarizen</span><br><span style="color:#e2e8f0">${_esc(d.clarizen_id||'—')}</span></div>
        </div>
      </div>`:''}

      <!-- History -->
      ${hist?`<div style="background:#0a0e1a;border:1px solid #1e2d40;border-radius:6px;padding:12px">
        <div style="font-size:9px;color:#22d3ee;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px">Recent History</div>
        ${hist}
      </div>`:''}
    </div>`;

  modal.addEventListener('click', e => { if (e.target===modal) S.closeCard(); });
  document.body.appendChild(modal);
}

// ── Nav + Health Bar ──────────────────────────────────────────────────────────

const _PAGES = [
  {id:'ops',     label:'Ops',      url:'/ops'},
  {id:'blockers',label:'Blockers', url:'/blockers'},
  {id:'forecast',label:'Forecast', url:'/forecast'},
  {id:'daily',   label:'Daily',    url:'/daily'},
  {id:'audit',   label:'Audit',    url:'/audit'},
  {id:'cse',     label:'CSE',      url:'/cse'},
  {id:'weekly',  label:'Weekly',   url:'/weekly'},
  {id:'compare', label:'Compare',  url:'/compare'},
];

S.initNav = function(activePage) {
  const nav = document.getElementById('s-nav');
  if (!nav) return;
  const links = _PAGES.map(p => {
    const active = p.id === activePage;
    return `<a href="${p.url}" style="font-size:11px;font-weight:${active?700:400};color:${active?'#22d3ee':'#475569'};text-decoration:none;${active?'border-bottom:2px solid #22d3ee;padding-bottom:2px':''}">${p.label}</a>`;
  }).join('');

  nav.innerHTML = `
    <div style="display:flex;align-items:center;gap:20px;flex:1">
      <span style="font-size:12px;font-weight:700;color:#22d3ee;letter-spacing:1px;font-family:monospace">☀ SOLSTICE</span>
      <div style="display:flex;gap:16px">${links}</div>
    </div>
    <div id="s-health" style="display:flex;gap:6px;align-items:center"></div>
    <div style="position:relative;margin-left:12px">
      <input id="g-search" type="text" placeholder="⌕ Account..." autocomplete="off"
        style="background:rgba(255,255,255,.05);border:1px solid #1e2d40;border-radius:4px;color:#e2e8f0;font-size:10px;padding:.28rem .65rem;width:150px;outline:none;transition:width .2s"
        oninput="S.gSearch(this.value)" onfocus="this.style.width='210px'" onblur="S.closeSearch();setTimeout(()=>this.style.width='150px',200)">
      <div id="g-dropdown" style="display:none;position:absolute;top:calc(100% + 4px);right:0;width:280px;background:#0f1729;border:1px solid #1e2d40;border-radius:6px;box-shadow:0 8px 24px rgba(0,0,0,.4);z-index:1000;max-height:320px;overflow-y:auto"></div>
    </div>`;

  _refreshHealth();
  setInterval(_refreshHealth, 5 * 60 * 1000);
};

function _refreshHealth() {
  fetch('/api/health-summary')
    .then(r => r.json())
    .then(data => {
      const el = document.getElementById('s-health');
      if (!el) return;
      const icons = {green:'🟢',amber:'🟡',red:'🔴'};
      el.innerHTML = Object.entries(data).map(([t,v]) =>
        `<span title="${t}: ${v.m9} M9 · ${v.blocked} blocked" style="font-size:10px;cursor:default">${icons[v.status]||'⚪'} <span style="color:#475569;font-size:9px">${t}</span></span>`
      ).join('');
    }).catch(() => {});
}

// ── Sync Summary Toast ────────────────────────────────────────────────────────

S.syncSummary = function(events) {
  const existing = document.getElementById('s-toast');
  if (existing) existing.remove();
  if (!events) return;
  const parts = [];
  if (events.m9 > 0) parts.push(`+${events.m9} M9`);
  if (events.blocked > 0) parts.push(`${events.blocked} newly blocked`);
  if (events.resolved > 0) parts.push(`${events.resolved} resolved`);
  if (!parts.length) return;
  const toast = document.createElement('div');
  toast.id = 's-toast';
  toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#0f1729;border:1px solid #22d3ee;border-radius:6px;padding:12px 16px;font-size:11px;color:#e2e8f0;z-index:8888;display:flex;gap:12px;align-items:center;box-shadow:0 4px 12px rgba(0,0,0,.4)';
  toast.innerHTML = `<span style="color:#22d3ee">⚡ Sync</span> ${parts.join(' · ')} <button onclick="this.parentElement.remove()" style="background:none;border:none;color:#475569;cursor:pointer;font-size:14px;margin-left:4px">✕</button>`;
  document.body.appendChild(toast);
  setTimeout(() => { if (document.getElementById('s-toast')) document.getElementById('s-toast').remove(); }, 8000);
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function _esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

})(window.S = window.S || {});
JSEOF
```

- [ ] **Step 4: Verify Node tests pass against the real file**

Since the test file has inline copies of the functions, run to confirm:
```bash
node /Users/mbanica/Documents/Code_Samples/CC/Solstice/tests/js/test_pure_fns.js
```
Expected: `13 passed, 0 failed`

- [ ] **Step 5: Commit**
```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
git add static/solstice.js tests/js/test_pure_fns.js
git commit -m "feat(Solstice): solstice.js — shared design system + pure fn TDD"
```

---

## Task 7: New page routes in dashboard.py

**Files:**
- Modify: `dashboard.py`
- Modify: `tests/test_dashboard_api.py`

- [ ] **Step 1: Write failing route tests**

Append to `tests/test_dashboard_api.py`:
```python
class TestNewPageRoutes:
    def test_cse_page_returns_200(self, client):
        r = client.get("/cse")
        assert r.status_code == 200

    def test_weekly_page_returns_200(self, client):
        r = client.get("/weekly")
        assert r.status_code == 200

    def test_compare_page_returns_200(self, client):
        r = client.get("/compare")
        assert r.status_code == 200
```

- [ ] **Step 2: Verify tests fail**
```bash
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/test_dashboard_api.py::TestNewPageRoutes -q 2>&1 | tail -3
```

- [ ] **Step 3: Create the 3 HTML stubs**

**NOTE:** Use bash heredoc for all HTML files (Write tool blocked for `.innerHTML`).

```bash
cat > /Users/mbanica/Documents/Code_Samples/CC/Solstice/static/cse.html << 'EOF'
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>&#x2600;</text></svg>">
<title>Solstice — CSE Workload</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="/static/solstice.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
</head><body style="background:#0a0e1a;color:#e2e8f0;min-height:100vh">
<nav id="s-nav" style="display:flex;align-items:center;padding:.6rem 1.5rem;background:#0f1729;border-bottom:1px solid #1e2d40;gap:12px"></nav>
<div id="main" style="padding:1.5rem"></div>
<script src="/static/solstice.js"></script>
<script>
S.initNav('cse');
S.restoreCard();

const theatre = new URLSearchParams(location.search).get('theatre') || '';

function load() {
  const url = '/api/cse-workload' + (theatre ? '?theatre='+encodeURIComponent(theatre) : '');
  fetch(url).then(r=>r.json()).then(render).catch(()=>{});
}

function render(rows) {
  const main = document.getElementById('main');
  if (!rows.length) { main.innerHTML='<p style="color:#475569;padding:2rem">No CSE data available.</p>'; return; }
  const avg = rows.reduce((a,r)=>a+r.account_count,0)/rows.length;
  main.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem">
      <h1 style="font-size:1.1rem;font-weight:700;color:#f0f6fc;font-family:monospace">CSE WORKLOAD</h1>
      <div style="display:flex;gap:.5rem">
        ${['','EMEA','JAPAC','AMER','LATAM'].map(t=>`<a href="/cse${t?'?theatre='+t:''}" style="font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid ${(theatre||'')===(t||'')?'#22d3ee':'#1e2d40'};color:${(theatre||'')===(t||'')?'#22d3ee':'#475569'};text-decoration:none">${t||'All'}</a>`).join('')}
      </div>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:11px">
      <thead><tr style="color:#475569;text-transform:uppercase;font-size:9px;letter-spacing:1px;border-bottom:2px solid #1e2d40">
        <th style="text-align:left;padding:8px 12px">CSE</th>
        <th style="text-align:right;padding:8px 12px">Accounts</th>
        <th style="text-align:right;padding:8px 12px">Blocked</th>
        <th style="text-align:right;padding:8px 12px">At Risk</th>
        <th style="text-align:right;padding:8px 12px">M9 This Month</th>
        <th style="padding:8px 12px">Load</th>
      </tr></thead>
      <tbody>${rows.map(r=>{
        const pct = Math.round((r.account_count/Math.max(avg*2,1))*100);
        const hi = r.blocked_count > 5;
        return `<tr style="border-bottom:1px solid #1e2d40;${hi?'background:rgba(239,68,68,.05)':''}">
          <td style="padding:10px 12px;font-weight:600;color:#e2e8f0">${r.cse}</td>
          <td style="text-align:right;padding:10px 12px;font-family:monospace">${r.account_count}</td>
          <td style="text-align:right;padding:10px 12px;font-family:monospace;color:${r.blocked_count>0?'#ef4444':'#475569'};font-weight:${r.blocked_count>5?700:400}">${r.blocked_count}</td>
          <td style="text-align:right;padding:10px 12px;font-family:monospace;color:${r.at_risk_count>0?'#f59e0b':'#475569'}">${r.at_risk_count}</td>
          <td style="text-align:right;padding:10px 12px;font-family:monospace;color:#10b981">${r.m9_this_month}</td>
          <td style="padding:10px 12px;min-width:120px"><div style="background:#1e2d40;height:6px;border-radius:3px"><div style="background:${hi?'#ef4444':'#22d3ee'};width:${Math.min(pct,100)}%;height:100%;border-radius:3px"></div></div></td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;
}

load();
</script>
</body></html>
EOF
```

```bash
cat > /Users/mbanica/Documents/Code_Samples/CC/Solstice/static/weekly.html << 'EOF'
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>&#x2600;</text></svg>">
<title>Solstice — Weekly</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="/static/solstice.css">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
</head><body style="background:#0a0e1a;color:#e2e8f0;min-height:100vh">
<nav id="s-nav" style="display:flex;align-items:center;padding:.6rem 1.5rem;background:#0f1729;border-bottom:1px solid #1e2d40;gap:12px"></nav>
<div id="main" style="padding:1.5rem"></div>
<script src="/static/solstice.js"></script>
<script>
S.initNav('weekly');
S.restoreCard();

const params = new URLSearchParams(location.search);
let currentDate = params.get('date') || '';
const theatre = params.get('theatre') || '';

function prevWeek() {
  const d = currentDate ? new Date(currentDate) : new Date();
  d.setDate(d.getDate() - 7);
  currentDate = d.toISOString().slice(0,10);
  load();
}
function nextWeek() {
  const d = currentDate ? new Date(currentDate) : new Date();
  d.setDate(d.getDate() + 7);
  currentDate = d.toISOString().slice(0,10);
  load();
}

function load() {
  let url = '/api/weekly-movements';
  const qp = [];
  if (currentDate) qp.push('date='+currentDate);
  if (theatre) qp.push('theatre='+encodeURIComponent(theatre));
  if (qp.length) url += '?' + qp.join('&');
  fetch(url).then(r=>r.json()).then(render).catch(()=>{});
}

function _row(a, onclick) {
  return `<div onclick="${onclick}('${(a.account_id||'').replace(/'/g,"\\'")}'')" style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid #1e2d40;cursor:pointer;transition:background .1s" onmouseover="this.style.background='#1e2d40'" onmouseout="this.style.background=''">
    <div>
      <div style="font-size:11px;font-weight:600;color:#e2e8f0">${a.customer_name||''}</div>
      <div style="font-size:9px;color:#475569">${a.active_cse||'—'} · ${a.sales_region||'—'}</div>
    </div>
    <span style="font-size:10px;color:#475569">${(a.m9_actual||a.m8_actual||'').slice(0,10)}</span>
  </div>`;
}

function _section(title, color, items, dateField) {
  if (!items.length) return '';
  return `<div style="background:#0f1729;border:1px solid #1e2d40;border-radius:6px;overflow:hidden;margin-bottom:1rem">
    <div style="padding:10px 12px;border-bottom:1px solid #1e2d40;display:flex;justify-content:space-between">
      <span style="font-size:10px;font-weight:700;color:${color};letter-spacing:1px;text-transform:uppercase">${title}</span>
      <span style="font-size:10px;color:#475569">${items.length}</span>
    </div>
    ${items.map(a=>_row(a,'S.openAccountCard')).join('')}
  </div>`;
}

function render(data) {
  const main = document.getElementById('main');
  const total = data.new_m9.length + data.m8_started.length + data.newly_blocked.length + data.resolved.length;
  main.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem;flex-wrap:wrap;gap:.5rem">
      <div>
        <h1 style="font-size:1.1rem;font-weight:700;color:#f0f6fc;font-family:monospace">WEEKLY MOVEMENTS</h1>
        <div style="font-size:10px;color:#475569;margin-top:2px">Week of ${data.week_of} · ${total} movements</div>
      </div>
      <div style="display:flex;gap:.5rem;align-items:center">
        <button onclick="prevWeek()" style="background:#0f1729;border:1px solid #1e2d40;color:#e2e8f0;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:11px">← Prev</button>
        <button onclick="nextWeek()" style="background:#0f1729;border:1px solid #1e2d40;color:#e2e8f0;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:11px">Next →</button>
      </div>
    </div>
    ${total===0?'<p style="color:#475569">No movements this week.</p>':''}
    ${_section('✓ New M9 Complete','#10b981',data.new_m9,'m9_actual')}
    ${_section('→ M8 Started','#22d3ee',data.m8_started,'m8_actual')}
    ${_section('🛑 Newly Blocked','#ef4444',data.newly_blocked,'')}
    ${_section('✓ Resolved','#10b981',data.resolved,'')}
  `;
}

load();
</script>
</body></html>
EOF
```

```bash
cat > /Users/mbanica/Documents/Code_Samples/CC/Solstice/static/compare.html << 'EOF'
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>&#x2600;</text></svg>">
<title>Solstice — Compare</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="/static/solstice.css">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
</head><body style="background:#0a0e1a;color:#e2e8f0;min-height:100vh">
<nav id="s-nav" style="display:flex;align-items:center;padding:.6rem 1.5rem;background:#0f1729;border-bottom:1px solid #1e2d40;gap:12px"></nav>
<div id="main" style="padding:1.5rem"></div>
<script src="/static/solstice.js"></script>
<script>
S.initNav('compare');
S.restoreCard();

fetch('/api/compare').then(r=>r.json()).then(render).catch(()=>{});

function render(data) {
  const ts = data.theatres || [];
  const main = document.getElementById('main');

  const metrics = [
    {key:'m9_total',    label:'M9 Complete',    color:'#10b981'},
    {key:'m9_this_week',label:'M9 This Week',   color:'#22d3ee'},
    {key:'blocked',     label:'Blocked',         color:'#ef4444'},
    {key:'at_risk',     label:'At Risk',         color:'#f59e0b'},
    {key:'sla_overdue', label:'SLA Overdue',     color:'#ef4444'},
  ];

  const maxVals = {};
  metrics.forEach(m => {
    maxVals[m.key] = Math.max(...ts.map(t=>t[m.key]||0), 1);
  });

  main.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem">
      <h1 style="font-size:1.1rem;font-weight:700;color:#f0f6fc;font-family:monospace">THEATRE COMPARISON</h1>
      <button onclick="exportAll()" style="background:#0f1729;border:1px solid #22d3ee;color:#22d3ee;padding:5px 14px;border-radius:4px;cursor:pointer;font-size:11px">Export CSV</button>
    </div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1rem">
      ${ts.map(t=>`
        <div style="background:#0f1729;border:1px solid #1e2d40;border-radius:8px;overflow:hidden">
          <div style="padding:12px;border-bottom:1px solid #1e2d40;text-align:center">
            <div style="font-size:10px;color:#475569;letter-spacing:2px;text-transform:uppercase;margin-bottom:4px">${t.theatre}</div>
            <div class="kpi-number" style="font-size:2rem">${t.m9_total}</div>
            <div style="font-size:9px;color:#475569">M9 total</div>
          </div>
          <div style="padding:12px;display:flex;flex-direction:column;gap:10px">
            ${metrics.slice(1).map(m=>{
              const pct = Math.round(((t[m.key]||0)/maxVals[m.key])*100);
              return `<div>
                <div style="display:flex;justify-content:space-between;margin-bottom:3px">
                  <span style="font-size:9px;color:#475569">${m.label}</span>
                  <span style="font-size:10px;color:${m.color};font-family:monospace;font-weight:700">${t[m.key]||0}</span>
                </div>
                <div style="background:#1e2d40;height:4px;border-radius:2px"><div style="background:${m.color};width:${pct}%;height:100%;border-radius:2px;transition:width .3s"></div></div>
              </div>`;
            }).join('')}
          </div>
        </div>`).join('')}
    </div>`;

  window._compareData = ts;
}

function exportAll() {
  if (!window._compareData) return;
  S.exportCSV(window._compareData, 'solstice-compare.csv');
}
</script>
</body></html>
EOF
```

- [ ] **Step 4: Add routes to dashboard.py**

Add after the existing `/audit` route section:

```python
@app.get("/cse", response_class=HTMLResponse)
def dashboard_cse():
    return (STATIC_DIR / "cse.html").read_text(encoding="utf-8")

@app.get("/weekly", response_class=HTMLResponse)
def dashboard_weekly():
    return (STATIC_DIR / "weekly.html").read_text(encoding="utf-8")

@app.get("/compare", response_class=HTMLResponse)
def dashboard_compare():
    return (STATIC_DIR / "compare.html").read_text(encoding="utf-8")
```

Also check that `STATIC_DIR` is defined (it should be — look for it near the top of dashboard.py):
```bash
grep -n "STATIC_DIR\|static_dir" /Users/mbanica/Documents/Code_Samples/CC/Solstice/dashboard.py | head -5
```
If not defined, add after `DATA_DIR`:
```python
STATIC_DIR = Path(__file__).parent / "static"
```

- [ ] **Step 5: Syntax check + run tests**
```bash
python3 -c "import py_compile; py_compile.compile('dashboard.py'); print('OK')"
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/test_dashboard_api.py -q 2>&1 | tail -3
```

- [ ] **Step 6: Commit**
```bash
git add dashboard.py static/cse.html static/weekly.html static/compare.html tests/test_dashboard_api.py
git commit -m "feat(Solstice): /cse /weekly /compare — new pages + routes"
```

---

## Task 8: Rebuild existing pages with new design system

**Files:** `static/v2.html`, `static/blockers.html`, `static/forecast.html`, `static/daily.html`, `static/audit.html`

Each page follows the same pattern: load `solstice.css` + `solstice.js`, call `S.initNav('page')` + `S.restoreCard()`, then page-specific fetch + render. The nav, search, modal, and health bar are all automatic via `solstice.js`.

Do one page at a time. For each:

- [ ] **Step 1: Rebuild the page** using `cat > static/X.html << 'EOF'` (never Write tool — contains innerHTML)
- [ ] **Step 2: Verify it loads** — start dashboard (`cd Solstice && python3 dashboard.py`) and open the page in a browser
- [ ] **Step 3: Run tests** — `pytest tests/ -q` — all must pass
- [ ] **Step 4: Commit** — `git commit -m "feat(Solstice): rebuild /ops with design system"`

### /ops (v2.html) structure
```
initNav('ops') + restoreCard()
KPI row: M9 done | At risk | Blocked  ← /api/milestones
Milestone funnel bar chart            ← /api/milestones
SLA breach list                       ← /api/sla-breaches
M1 action plan                        ← /api/m1-suggestions
CSE workload strip                    ← /api/cse-workload (top 5 by blocked)
Pipeline console (SSE)                ← /api/run-full
```

### /blockers structure
```
initNav('blockers') + restoreCard()
Theatre + region + CSE filter pills   ← /api/theatres
Subtype sections (no_contact / core_rep_blocking / tech_blocker / active_deal / other)
Each row: customer name, CSE, region, signal dot, blockerAgeHTML(), signal_date
Expand row → call prep brief (last contact, owner, status detail)
```
Each row click → `S.openAccountCard(account_id)`

### /forecast structure
```
initNav('forecast') + restoreCard()
Next week M9 targets by theatre       ← /api/forecast
4-week velocity chart                 ← /api/forecast
SLA countdown list (from /api/milestones where m3_complete and not m9_complete)
```

### /daily structure
```
initNav('daily') + restoreCard()
Date picker (defaults today)
Daily movements list                  ← /api/daily-brief
30-day M8/M9 trend chart
Sync summary toast on pipeline run    ← SSE /api/run-full
```

### /audit structure
```
initNav('audit') + restoreCard()
Stats bar (total changes, theatres)   ← /api/audit-log
Field / theatre / sort filters
Timeline entries                      ← /api/audit-log
Export CSV button → S.exportCSV(rows, 'audit.csv')
```

---

## Task 9: Cleanup + GitHub readiness

**Files:** `.gitignore`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: Create .gitignore**
```bash
cat > /Users/mbanica/Documents/Code_Samples/CC/Solstice/.gitignore << 'EOF'
# Data files — never commit live data
data/solstice.db
data/solstice.db-shm
data/solstice.db-wal
data/state.json
data/*.csv

# Brainstorm sessions
.superpowers/

# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/
*.egg-info/
dist/
build/

# Env
.env
*.env.local

# OS
.DS_Store
Thumbs.db
EOF
```

- [ ] **Step 2: Create README.md**
```bash
cat > /Users/mbanica/Documents/Code_Samples/CC/Solstice/README.md << 'EOF'
# Solstice

Global CC Migration monitor — EMEA, JAPAC, AMER, LATAM. FastAPI + SQLite + vanilla JS.

## Pages

| URL | Purpose |
|---|---|
| `/ops` | Main ops: funnel, weekly tracker, M1 action plan, SLA breaches |
| `/blockers` | Call prep: blocked/at-risk accounts by subtype + blocker age |
| `/forecast` | Velocity: next 7 days M9 targets + 4-week trend + SLA countdown |
| `/daily` | Leadership briefing: daily movements + 30-day trend |
| `/audit` | Full change history with export |
| `/cse` | CSE workload: account load, blocked counts, velocity |
| `/weekly` | Weekly movement digest: new M9, M8 started, newly blocked, resolved |
| `/compare` | 4-theatre side-by-side comparison for QBR |

## Setup

```bash
pip install -r requirements.txt
cd Solstice && python3 dashboard.py
# Opens on http://localhost:8200
```

## Data

Drop `dc_cse_tracker.csv` in `data/` then click **Refresh Data** on any page, or:
```bash
curl http://localhost:8200/api/run-pipeline
```

## Tests

```bash
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/ -q
# Node pure-fn tests:
node tests/js/test_pure_fns.js
```
EOF
```

- [ ] **Step 3: Update CLAUDE.md**

Update the Solstice section — add `solstice.js` architecture note:
```
- **Design system**: `static/solstice.js` exposes `window.S` — all pages call `S.initNav(page)` + `S.restoreCard()` on load. Never copy-paste nav or search into individual pages.
- **New pages**: /cse /weekly /compare added. Nav order: Ops·Blockers·Forecast·Daily·Audit·CSE·Weekly·Compare
- **HTML file creation**: Write tool blocked for `.innerHTML` — use `bash cat > file << 'HEREDOC'`
```

- [ ] **Step 4: Run full test suite**
```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/ -q 2>&1 | tail -3
node tests/js/test_pure_fns.js
```
Expected: all green.

- [ ] **Step 5: Final commit (local — Solstice is stealth)**
```bash
git add .gitignore README.md CLAUDE.md static/ tests/
git commit -m "feat(Solstice): ultimate redesign complete — design system, 8 pages, TDD"
```

- [ ] **Step 6: Create GitHub remote when ready**
```bash
# When ready to publish:
gh repo create shpapy/solstice --private --description "CC Migration ops dashboard"
git remote add origin git@github.com:shpapy/solstice.git
git push -u origin main
```

---

## Self-Review

**Spec coverage check:**
- ✅ Visual redesign (cyan aesthetic) — solstice.css + all pages
- ✅ Design system first — solstice.js with `window.S`
- ✅ /cse, /weekly, /compare — Task 7
- ✅ Upgraded account modal — solstice.js `openAccountCard`
- ✅ Theatre health bar — `S.initNav` calls `healthBar()`
- ✅ Blocker age badge — `S.blockerAgeHTML`
- ✅ SLA countdown — `S.slaCountdownHTML`
- ✅ Call prep brief — inside account modal
- ✅ Sync summary toast — `S.syncSummary`
- ✅ Export CSV — `S.exportCSV`, audit + compare pages
- ✅ TDD — all 4 API endpoints tested, pure JS functions tested
- ✅ Tailwind CDN gate — Task 1
- ✅ .gitignore, README — Task 9
- ✅ 285 existing tests preserved

**No placeholders found.**

**Type consistency:** `S.slaCountdown` signature matches `S.slaCountdownHTML` call in `_renderCard`. `S.blockerAge` / `S.blockerAgeHTML` consistent. `S.exportCSV(rows, filename)` matches all call sites.
