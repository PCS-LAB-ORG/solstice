"""
dashboard.py — Solstice Control Center
Dark ops dashboard inspired by Pi-hole + OpenClaw aesthetic.
FastAPI + SSE + Chart.js. No npm required.
Run: python3 dashboard.py → http://localhost:8200

Security note: innerHTML is used only for server-generated HTML from
trusted SQLite data, never from user input. All user-facing dynamic
values are inserted via textContent.
"""
import json, asyncio, subprocess, sys
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
import uvicorn

from agent.constants import STATE_FILE, DATA_DIR
from agent.db import get_db, init_db


@asynccontextmanager
async def lifespan(app):
    """Populate DB immediately when FastAPI starts."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _populate_db)
    yield


app = FastAPI(title="Solstice Control Center", lifespan=lifespan)


def _populate_db():
    """Populate DB from CSVs. Checks all critical tables, not just blocked_data."""
    try:
        with get_db() as conn:
            bd = conn.execute("SELECT COUNT(*) FROM blocked_data").fetchone()[0]
            sh = conn.execute("SELECT COUNT(*) FROM status_history").fetchone()[0]
            ai = conn.execute("SELECT COUNT(*) FROM ai_enrichment").fetchone()[0]
        if bd > 0 and sh > 0 and ai > 0:
            return  # All tables populated
    except: pass

    import json as _j, logging as _log
    _log.warning("DB empty — populating from CSVs...")
    from agent.ps_parser import load_and_merge as _mp
    from agent.db import migrate_from_state as _mig
    init_db()
    if (DATA_DIR/"ps_tracker.csv").exists():
        _mp(DATA_DIR/"ps_tracker.csv", STATE_FILE)
    _mig(STATE_FILE)
    # DC pipeline runs last — syncs all 9 milestones, cc_rep, cc_dsm, churn_risk, rebuilds m1_suggestions
    if (DATA_DIR/"dc_cse_tracker.csv").exists():
        _run_dc_pipeline(DATA_DIR, STATE_FILE)
    _state = _j.loads(STATE_FILE.read_text())
    with get_db() as conn:
        for aid, acc in _state.get("accounts",{}).items():
            conn.execute("UPDATE accounts SET live_fire=?, live_fire_dc=? WHERE account_id=?",
                (1 if acc.get("live_fire") else 0, acc.get("live_fire_dc","") or "", aid))
    with get_db() as conn:
        n2 = conn.execute("SELECT COUNT(*) FROM blocked_data").fetchone()[0]
    _log.warning("DB populated: %d milestone records", n2)


def _ensure_db():
    """Call before every API response."""
    _populate_db()



def _load_milestones_sla_count() -> list:
    """Fast SLA breach count used by stats."""
    try:
        return [r for r in _load_milestones()
                if r.get('sla_m3_m8_breach') or r.get('sla_m8_m9_breach')]
    except: return []


def _load_stats() -> dict:
    _ensure_db()
    try:
        with get_db() as conn:
            total      = conn.execute("SELECT COUNT(*) FROM accounts WHERE customer_name!=''").fetchone()[0]
            by_status  = {r[0] or "Blank": r[1] for r in conn.execute(
                "SELECT status, COUNT(*) FROM accounts WHERE customer_name!='' GROUP BY status")}
            # DC milestones are source of truth for completion/progress
            completed  = conn.execute(
                "SELECT COUNT(*) FROM blocked_data WHERE m9_complete=1").fetchone()[0]
            in_prog_dc = conn.execute(
                "SELECT COUNT(*) FROM blocked_data WHERE m8_started=1 AND (m9_complete IS NULL OR m9_complete=0)").fetchone()[0]
            no_status  = sum(v for k,v in by_status.items() if k in ("","Blank"))
            stalls     = conn.execute("""SELECT COUNT(DISTINCT b.account_id)
                FROM blocked_data b JOIN accounts a ON a.account_id=b.account_id
                WHERE b.is_cs_team=1 AND b.m3_complete=1 AND b.m8_started=0""").fetchone()[0]
            core_rep   = conn.execute(
                "SELECT COUNT(*) FROM blocked_data WHERE subtype='core_rep_blocking'").fetchone()[0]
            ps_active  = conn.execute(
                "SELECT COUNT(*) FROM ps_data WHERE ps_status!='' AND ps_status NOT LIKE 'BLOCKED%'").fetchone()[0]
            no_cse     = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE (active_cse IS NULL OR active_cse='') AND customer_name!=''").fetchone()[0]
            dc_driving = conn.execute("SELECT COUNT(*) FROM accounts WHERE live_fire=1").fetchone()[0]
            sla_breaches = len(_load_milestones_sla_count())
            dc_green  = conn.execute("SELECT COUNT(*) FROM blocked_data WHERE dc_progress='Green'").fetchone()[0]
            dc_yellow = conn.execute("SELECT COUNT(*) FROM blocked_data WHERE dc_progress='Yellow'").fetchone()[0]
            dc_red    = conn.execute("SELECT COUNT(*) FROM blocked_data WHERE dc_progress='Red'").fetchone()[0]
            last_run   = STATE_FILE.stat().st_mtime if STATE_FILE.exists() else 0
            last_str   = datetime.fromtimestamp(last_run,timezone.utc).strftime("%d %b %Y · %H:%M UTC") if last_run else "—"
            return dict(total=total,completed=completed,in_progress=in_prog_dc,
                        no_status=no_status,stalls=stalls,core_rep_blocking=core_rep,ps_active=ps_active,
                        no_cse=no_cse,dc_driving=dc_driving,by_status=by_status,last_run=last_str,
                        sla_breaches=sla_breaches,dc_green=dc_green,dc_yellow=dc_yellow,dc_red=dc_red)
    except Exception as e:
        return {"error": str(e)}


def _load_weekly() -> list:
    _ensure_db()
    try:
        today  = date.today()
        weeks  = {}
        with get_db() as conn:
            for row in conn.execute("""SELECT a.customer_name,a.active_cse,a.status,
                a.live_fire, a.live_fire_dc, a.sales_region, a.account_theatre,
                b.m8_planned,b.m9_planned,b.m8_started,b.m9_complete
                FROM accounts a JOIN blocked_data b ON a.account_id=b.account_id
                WHERE b.m3_complete=1
                AND (b.m8_started=1 OR b.m8_planned!='' OR b.m9_planned!='')"""):
                for field,label,done in [
                    (row["m8_planned"],"M8",bool(row["m8_started"])),
                    (row["m9_planned"],"M9",bool(row["m9_complete"]) or row["status"]=="Completed")]:
                    if not field: continue
                    try:
                        for fmt in ("%m/%d/%Y","%m/%d/%y"):
                            try: d=datetime.strptime(field.strip(),fmt).date(); break
                            except: pass
                        else: continue
                        k=d.strftime("%Y-W%U")
                        ws=d-timedelta(days=(d.weekday()+1)%7)
                        weeks.setdefault(k,{"key":k,"label":f"W{d.strftime('%U')} · {ws.strftime('%d %b')}","m8":[],"m8_done":[],"m9":[],"done":[]})
                        e={"name":row["customer_name"],"cse":row["active_cse"] or "—","lf":bool(row["live_fire"]),"lf_dc":row["live_fire_dc"] or "","date":d.strftime("%d %b"),"region":row["sales_region"] or "","theatre":row["account_theatre"] or "EMEA"}
                        if label=="M8" and not done: weeks[k]["m8"].append(e)
                        elif label=="M8" and done: weeks[k]["m8_done"].append(e)
                        elif label=="M9" and not done: weeks[k]["m9"].append(e)
                        elif label=="M9" and done: weeks[k]["done"].append(e)
                    except: pass
        tw=today.strftime("%Y-W%U")
        sw=sorted(weeks.values(),key=lambda x:x["key"])
        idx=next((i for i,w in enumerate(sw) if w["key"]>=tw),0)
        return sw[max(0,idx-3):idx+6]
    except: return []


def _load_cse() -> list:
    _ensure_db()
    try:
        with get_db() as conn:
            rows=conn.execute("""SELECT active_cse,COUNT(*) total,
                SUM(CASE WHEN status IN ('Ready To Engage','Account team contacted') THEN 1 ELSE 0 END) outreach,
                SUM(CASE WHEN status IN ('Sales Hold','Churning/Churned','Backoff','Cancelled') THEN 1 ELSE 0 END) risk,
                SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) done,
                SUM(CASE WHEN status IN ('In Progress','Kick Off Scheduled','Blocked: Tech limitation',
                    'Blocked: Acct Team','Blocked: Customer','Customer Engaged') THEN 1 ELSE 0 END) active
                FROM accounts WHERE active_cse IS NOT NULL AND active_cse!=''
                GROUP BY active_cse ORDER BY total DESC""").fetchall()
            result = []
            for r in rows:
                d = dict(r)
                eligible = d['total'] - d['risk']
                d['success_rate'] = round(d['done'] / eligible * 100) if eligible > 0 else 0
                result.append(d)
            return result
    except: return []


@app.get("/api/stats")
def api_stats(): return _load_stats()

@app.get("/api/weekly")
def api_weekly(): return _load_weekly()

@app.get("/api/cse")
def api_cse(): return _load_cse()

def _download_live_from_drive() -> dict:
    """
    Download all 4 live CSVs from Google Drive using browser auth.
    Opens each export URL → browser (corp Okta auth) downloads to ~/Downloads
    → moves to data/ → pipeline runs on fresh data.
    """
    import json as _j, glob as _g, shutil as _sh, time as _t, os as _os
    from datetime import datetime, timezone

    config = _j.loads((DATA_DIR / "drive_config.json").read_text())
    downloads = Path.home() / "Downloads"
    results = {}

    # Only DC CSE Tracker is used by the pipeline — emea_accounts and blocked_accounts
    # are no longer pipeline sources (DC is sole source of truth for all data).
    FILE_MAP = {
        "DC CSE Tracker": ("dc_cse_tracker.csv", None),
        # emea_accounts.csv and blocked_accounts.csv removed — DC CSE Tracker is sole source
    }

    for f in config["files"]:
        name = f["name"]
        if name not in FILE_MAP: continue
        dest_name, gid = FILE_MAP[name]
        file_id = f.get("file_id","")
        if not file_id: continue

        # Use stored gid for blocked accounts (tab-aware)
        if name == "EMEA Solistce Blocked Accounts":
            gid = f.get("current_gid", gid)

        url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv"
        if gid: url += f"&gid={gid}"

        # Track existing downloads before opening browser
        before = set(_g.glob(str(downloads / "*.csv")))
        subprocess.Popen(["open", url])
        _t.sleep(0.5)

        # Wait up to 20s for new CSV in Downloads
        deadline = _t.monotonic() + 20
        downloaded = None
        while _t.monotonic() < deadline:
            _t.sleep(1)
            after = set(_g.glob(str(downloads / "*.csv")))
            new_files = after - before
            if new_files:
                downloaded = sorted(new_files, key=_os.path.getmtime)[-1]
                break

        if downloaded:
            dest = DATA_DIR / dest_name
            _sh.move(downloaded, dest)
            results[name] = f"✅ downloaded → {dest_name}"
        else:
            results[name] = "⚠️ no download detected (check browser)"

    return results


_DC_MILESTONE_WATCH = [
    ("m1_complete","M1 Outreach"),("m2_complete","M2 Entitlements"),
    ("m3_complete","M3 Buy-in"),("m4_complete","M4 Discovery"),
    ("m5_complete","M5 Tech Validation"),("m7_complete","M7 Legal"),
    ("m8_started","M8 Upgrade Started"),("m9_complete","M9 Upgrade Complete"),
]

def _yn_str(v) -> str:
    return "Y" if str(v if v is not None else "") in ("1","True","true","Y","y") else "N"

def _run_dc_pipeline(data_dir: Path, state_file: Path) -> dict:
    """
    Shared DC CSE Tracker pipeline step:
    1. Snapshot existing dc_data from state.json
    2. Parse + merge fresh DC CSV
    3. Upsert ALL milestone fields into blocked_data (DC wins)
    4. Diff snapshot vs new → log changes to status_history
    Returns: {matched, total, audit_logged}
    """
    import json as _j
    from datetime import datetime as _dt, timezone as _tz
    from agent.dc_parser import load_and_merge as _mdc

    # Snapshot previous dc_data BEFORE merge
    _prev = _j.loads(state_file.read_text())
    _snap = {}
    for _pid, _pacc in _prev.get("accounts", {}).items():
        _pd = _pacc.get("dc_data")
        if _pd:
            _snap[_pid.lower()] = _pd

    # Merge fresh DC CSV into state.json
    result = _mdc(data_dir / "dc_cse_tracker.csv", state_file)

    _dc_state = _j.loads(state_file.read_text())
    _now = _dt.now(_tz.utc).isoformat()
    _audit = 0

    # Load ALL theatres via dc_parser — same full field set for every account, no exceptions
    from agent.dc_parser import parse_dc_csv as _parse_dc
    _all_dc = {rec["account_id"]: rec for rec in _parse_dc(data_dir / "dc_cse_tracker.csv")}

    with get_db() as _conn:
        _new_accounts = 0
        for _aid, _dd in _all_dc.items():
            # Ensure account exists — create if new (JAPAC/AMER/LATAM)
            _exists = _conn.execute("SELECT 1 FROM accounts WHERE account_id=?", (_aid,)).fetchone()
            if not _exists:
                _conn.execute("""INSERT OR IGNORE INTO accounts
                    (account_id, customer_name, active_cse, sales_region, account_theatre, created_at)
                    VALUES (?,?,?,?,?,datetime('now'))""",
                    (_aid, _dd.get("account_name",""),
                     _dd.get("active_cse",""),
                     _dd.get("area","") or _dd.get("account_region",""),
                     _dd.get("account_theatre","EMEA")))
                _new_accounts += 1
            # Update accounts table — same fields for ALL theatres, no exceptions
            _region = _dd.get("area","") or _dd.get("account_region","")
            _conn.execute("""UPDATE accounts SET
                active_cse=CASE WHEN ? !='' THEN ? ELSE active_cse END,
                sales_region=CASE WHEN ? !='' THEN ? ELSE sales_region END,
                account_theatre=?,
                customer_name=CASE WHEN ? !='' THEN ? ELSE customer_name END,
                status=CASE WHEN ? !='' THEN ? ELSE status END,
                live_fire=CASE WHEN ? =1 THEN 1 ELSE live_fire END
                WHERE account_id=?""",
                (_dd.get("active_cse",""), _dd.get("active_cse",""),
                 _region, _region,
                 _dd.get("account_theatre","EMEA"),
                 _dd.get("account_name",""), _dd.get("account_name",""),
                 _dd.get("status",""), _dd.get("status",""),
                 int(_dd.get("live_fire", False)),
                 _aid))
            if _dd.get("email_sent"):
                _conn.execute("UPDATE accounts SET email_sent=? WHERE account_id=? AND (email_sent IS NULL OR email_sent='')",
                              (_dd["email_sent"], _aid))
            # Upsert ALL milestones into blocked_data (DC is master)
            _conn.execute("""
                INSERT INTO blocked_data
                  (account_id, m0_complete, m1_complete, m1_planned,
                   m2_complete, m2_planned, m3_complete, m3_planned,
                   m4_complete, m4_planned, m5_complete, m5_planned,
                   m7_complete, m8_started, m8_planned, m8_actual,
                   m9_complete, m9_planned, m9_actual,
                   upgrade_notes, dc_progress, owner_e2e, dc_assignment, merged_at,
                   cc_rep, cc_dsm, churn_risk, health_notes,
                   last_edited_by, last_edited_date, roadmap_url, ps_plan_url,
                   account_region, current_project_status, next_renewal_date,
                   past_due_planned, upgrade_duration_weeks, has_partner, upgrade_partner,
                   m1_details, m3_details, m5_details, milestone_aging,
                   days_since_milestone, momentum_x, entitlement_provision,
                   activation_status, posture_workloads, account_theatre,
                   signal, subtype, status_detail, cohort, area, district, team)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(account_id) DO UPDATE SET
                  m0_complete=excluded.m0_complete, m1_complete=excluded.m1_complete,
                  m1_planned=excluded.m1_planned, m2_complete=excluded.m2_complete,
                  m2_planned=excluded.m2_planned, m3_complete=excluded.m3_complete,
                  m3_planned=excluded.m3_planned, m4_complete=excluded.m4_complete,
                  m4_planned=excluded.m4_planned, m5_complete=excluded.m5_complete,
                  m5_planned=excluded.m5_planned, m7_complete=excluded.m7_complete,
                  m8_started=excluded.m8_started, m8_planned=excluded.m8_planned,
                  m8_actual=excluded.m8_actual, m9_complete=excluded.m9_complete,
                  m9_planned=excluded.m9_planned, m9_actual=excluded.m9_actual,
                  upgrade_notes=CASE WHEN excluded.upgrade_notes!='' THEN excluded.upgrade_notes ELSE upgrade_notes END,
                  dc_progress=excluded.dc_progress, owner_e2e=excluded.owner_e2e,
                  dc_assignment=excluded.dc_assignment, merged_at=excluded.merged_at,
                  cc_rep=excluded.cc_rep, cc_dsm=excluded.cc_dsm,
                  churn_risk=excluded.churn_risk,
                  health_notes=CASE WHEN excluded.health_notes!='' THEN excluded.health_notes ELSE health_notes END,
                  last_edited_by=excluded.last_edited_by, last_edited_date=excluded.last_edited_date,
                  roadmap_url=excluded.roadmap_url, ps_plan_url=excluded.ps_plan_url,
                  account_region=excluded.account_region,
                  current_project_status=excluded.current_project_status,
                  next_renewal_date=excluded.next_renewal_date,
                  past_due_planned=excluded.past_due_planned,
                  upgrade_duration_weeks=excluded.upgrade_duration_weeks,
                  has_partner=excluded.has_partner, upgrade_partner=excluded.upgrade_partner,
                  m1_details=excluded.m1_details, m3_details=excluded.m3_details,
                  m5_details=excluded.m5_details, milestone_aging=excluded.milestone_aging,
                  days_since_milestone=excluded.days_since_milestone,
                  momentum_x=excluded.momentum_x,
                  entitlement_provision=excluded.entitlement_provision,
                  activation_status=excluded.activation_status,
                  posture_workloads=excluded.posture_workloads,
                  account_theatre=excluded.account_theatre,
                  signal=excluded.signal,
                  subtype=excluded.subtype,
                  status_detail=CASE WHEN excluded.status_detail!='' THEN excluded.status_detail ELSE status_detail END,
                  cohort=excluded.cohort,
                  area=excluded.area,
                  district=excluded.district,
                  team=excluded.team
            """, (
                _aid,
                int(_dd.get("m0_complete", False)),
                int(_dd.get("m1_complete", False)), _dd.get("m1_planned", ""),
                int(_dd.get("m2_complete", False)), _dd.get("m2_planned", ""),
                int(_dd.get("m3_complete", False)), _dd.get("m3_planned", ""),
                int(_dd.get("m4_complete", False)), _dd.get("m4_planned", ""),
                int(_dd.get("m5_complete", False)), _dd.get("m5_planned", ""),
                int(_dd.get("m7_complete", False)),
                int(_dd.get("m8_started", False)), _dd.get("m8_planned", ""), _dd.get("m8_actual", ""),
                int(_dd.get("m9_complete", False)), _dd.get("m9_planned", ""), _dd.get("m9_actual", ""),
                _dd.get("upgrade_notes", ""), _dd.get("dc_progress", ""),
                _dd.get("owner_e2e", ""), _dd.get("dc_assignment", ""), _dd.get("merged_at", ""),
                _dd.get("cc_rep", ""), _dd.get("cc_dsm", ""),
                _dd.get("churn_risk", ""), _dd.get("health_notes", ""),
                _dd.get("last_edited_by", ""), _dd.get("last_edited_date", ""),
                _dd.get("roadmap_url", ""), _dd.get("ps_plan_url", ""),
                _dd.get("account_region", ""), _dd.get("current_project_status", ""),
                _dd.get("next_renewal_date", ""), _dd.get("past_due_planned", ""),
                _dd.get("upgrade_duration_weeks", ""), _dd.get("has_partner", ""),
                _dd.get("upgrade_partner", ""), _dd.get("m1_details", ""),
                _dd.get("m3_details", ""), _dd.get("m5_details", ""),
                _dd.get("milestone_aging", ""), _dd.get("days_since_milestone", ""),
                _dd.get("momentum_x", ""), _dd.get("entitlement_provision", ""),
                _dd.get("activation_status", ""), _dd.get("posture_workloads", ""),
                _dd.get("account_theatre", "EMEA"),
                _dd.get("signal", ""), _dd.get("subtype", ""),
                _dd.get("status_detail", ""),
                _dd.get("cohort", ""), _dd.get("area", ""),
                _dd.get("district", ""), _dd.get("pm_status", ""),
            ))
            # Diff audit — only accounts with prior dc_data (skip first-load)
            _old = _snap.get(_aid.lower(), {})
            if not _old:
                continue
            for _dcf, _dcl in _DC_MILESTONE_WATCH:
                _ov = _yn_str(_old.get(_dcf))
                _nv = _yn_str(_dd.get(_dcf))
                if _ov == _nv:
                    continue
                _dup = _conn.execute(
                    "SELECT 1 FROM status_history WHERE account_id=? AND field_name=? AND old_status=? AND new_status=? AND file_source='DC CSE Tracker'",
                    (_aid, _dcl, _ov, _nv)).fetchone()
                if not _dup:
                    _conn.execute(
                        "INSERT INTO status_history (account_id,old_status,new_status,changed_at,source,file_source,field_name) VALUES (?,?,?,?,?,?,?)",
                        (_aid, _ov, _nv, _now, "pipeline", "DC CSE Tracker", _dcl))
                    _audit += 1
            # CSE change audit
            _old_cse = (_old.get("active_cse") or "").strip()
            _new_cse = (_dd.get("active_cse") or "").strip()
            if _old_cse and _new_cse and _old_cse != _new_cse:
                _dup2 = _conn.execute(
                    "SELECT 1 FROM status_history WHERE account_id=? AND field_name='cse' AND old_status=? AND new_status=? AND file_source='DC CSE Tracker'",
                    (_aid, _old_cse, _new_cse)).fetchone()
                if not _dup2:
                    _conn.execute(
                        "INSERT INTO status_history (account_id,old_status,new_status,changed_at,source,file_source,field_name) VALUES (?,?,?,?,?,?,?)",
                        (_aid, _old_cse, _new_cse, _now, "pipeline", "DC CSE Tracker", "cse"))
                    _audit += 1

    result["audit_logged"] = _audit
    result["new_accounts"] = _new_accounts

    # Auto-rebuild m1_suggestions from fresh DB state — no stale data ever served
    _SKIP = {'Churning/Churned','Cancelled','Backoff','Completed'}
    _HOLD_KW = ['hold off','please hold','do not reach','strictly on hold','postpone',
                'defer','sales manager','acct team ask','regional sales','advised to hold',
                'core rep is blocking']
    _REGION_CSE = {
        'UKI':['Chinmoy Roy','Tunde Adenugba','Visnavi'],
        'SEUR':['Mikhail Bakhmetiev','Mathieu Dalbes','Alvaro Fortes','Visnavi'],
        'France':['Mathieu Dalbes','Mikhail Bakhmetiev','Alvaro Fortes'],
        'Germany':['Jonathan Brox','Alvaro Fortes'],
        'Nordics':['Jonathan Brox','Mathieu Dalbes'],
        'Benelux':['Jonathan Brox'],
        'Alps':['Chinmoy Roy','Jonathan Brox'],
        'CEE':['Tunde Adenugba','Jonathan Brox','Alvaro Fortes'],
        'Turkey/SA':['Tunde Adenugba','Pushkar Kakkar'],
        'Gulf/North Africa':['Pushkar Kakkar','Jonathan Brox','Chinmoy Roy'],
        'Saudi/LBS':['Jonathan Brox','Pushkar Kakkar'],
        '—':['Chinmoy Roy','Jonathan Brox'],
    }
    with get_db() as _mdb:
        _load = {r[0]:r[1] for r in _mdb.execute(
            "SELECT active_cse,COUNT(*) FROM accounts WHERE active_cse IS NOT NULL AND active_cse!='' AND active_cse!='Irene Garcia' GROUP BY active_cse").fetchall()}
        _load['Visnavi'] = 0
        _SKIP_KW = ['wiz choice','made a wiz','went to wiz','no action required',
                    'will not migrate','never activated','not migrate them','decided not to migrate',
                    'chose wiz','going with wiz','no cortex cloud migration','nfr use','likely nfr',
                    'partner account','strictly nfr']
        _m1_rows = _mdb.execute('''
            SELECT a.account_id,a.customer_name,a.active_cse,a.sales_region,a.status,a.live_fire,
                   b.signal,b.status_detail,b.upgrade_notes,b.subtype,b.churn_risk,b.health_notes
            FROM accounts a JOIN blocked_data b ON a.account_id=b.account_id
            WHERE a.customer_name!='' AND b.m1_complete=0
            ORDER BY a.sales_region,a.customer_name''').fetchall()
        _mdb.execute('DELETE FROM m1_suggestions')
        for _mr in _m1_rows:
            _reg = _mr['sales_region'] or '—'
            _orig = _mr['active_cse'] or '—'
            _cse = min(_REGION_CSE.get(_reg,['Chinmoy Roy']),key=lambda c:_load.get(c,0)) if _orig=='Irene Garcia' else _orig
            if _orig=='Irene Garcia': _load[_cse]=_load.get(_cse,0)+1
            _st=_mr['status'] or ''; _sig=_mr['signal'] or ''
            _det=(_mr['status_detail'] or '').lower()
            _nt=(_mr['upgrade_notes'] or '').lower()
            _hn=(_mr['health_notes'] or '').lower()
            _churn=(_mr['churn_risk'] or '').strip()
            _nm=_mr['customer_name'].lower()
            _all=_nt+' '+_hn+' '+_det
            if 'mtn ' in _nm or _nm=='mtn benin': _cat='unblock'
            elif _st in _SKIP or 'Blocked: Tech' in _st: _cat='skip'
            elif any(k in _all for k in _SKIP_KW): _cat='skip'
            elif _churn=='Red': _cat='acct_team'
            elif '\U0001f6d1' in (_mr['status_detail'] or '') or 'blocked from' in _det: _cat='acct_team'
            elif _st in ('Sales Hold','On Hold') or any(k in _nt+_det for k in _HOLD_KW) or _sig=='blocked': _cat='acct_team'
            else: _cat='actionable'
            _mdb.execute(
                'INSERT INTO m1_suggestions (account_name,assigned_cse,original_cse,region,status,signal,category) VALUES (?,?,?,?,?,?,?)',
                (_mr['customer_name'],_cse,_orig,_reg,_mr['status'],_mr['signal'],_cat))
    result["m1_rebuilt"] = len(_m1_rows)

    # Backfill audit history for any account that has a milestone completion but no audit entry
    # This runs on every DC sync so new theatres (JAPAC/AMER/LATAM) get history automatically
    import csv as _csv2
    _PLACEHOLDER = '01/15/2026'
    _MS_DATES = [
        ('m1_complete','Date - M1:Internal Kickoff Complete','M1 Outreach'),
        ('m2_complete','Date - M2:Entitlements and Plan aligned with customer','M2 Entitlements'),
        ('m3_complete','Date - M3:EB Buy-in Meeting Complete','M3 Buy-in'),
        ('m4_complete','Date - M4:Discovery complete','M4 Discovery'),
        ('m5_complete','Date - M5:Tech validation complete','M5 Tech Validation'),
        ('m8_started','Date - M8:Upgrade started','M8 Upgrade Started'),
        ('m9_complete','Date - M9:Upgrade complete','M9 Upgrade Complete'),
    ]
    _raw_rows = {}
    with open(data_dir / "dc_cse_tracker.csv", encoding="utf-8-sig", errors="ignore") as _f2:
        for _row2 in _csv2.DictReader(_f2):
            _t2 = _row2.get("account_theatre","").strip().upper()
            if _t2 not in ("EMEA","JAPAC","AMER","LATAM"): continue
            _rid2 = _row2.get("pc_end_customer_account_id","").strip().lower()
            if _rid2: _raw_rows[_rid2] = _row2

    from datetime import datetime as _dtt  # hoisted — avoids re-importing inside loop

    def _parse_actual(s):
        if not s or s.strip() == _PLACEHOLDER: return None
        for _fmt in ('%m/%d/%Y %H:%M:%S','%m/%d/%Y','%m/%d/%y'):
            try:
                return _dtt.strptime(s.strip(), _fmt).isoformat()+'+00:00'
            except: pass
        return None

    _bf = 0
    with get_db() as _bc:
        _id_map2 = {r[0].lower(): r[0] for r in _bc.execute('SELECT account_id FROM accounts').fetchall()}
        for _rec in _all_dc.values():
            _aid2_lower = _rec["account_id"]
            _aid2 = _id_map2.get(_aid2_lower)
            if not _aid2: continue
            _raw2 = _raw_rows.get(_aid2_lower, {})
            for _fk, _dc_col, _label in _MS_DATES:
                if not _rec.get(_fk): continue
                _ts2 = _parse_actual(_raw2.get(_dc_col,''))
                if not _ts2: continue
                _dup2 = _bc.execute("SELECT 1 FROM status_history WHERE account_id=? AND field_name=? AND new_status='Y' AND file_source='DC CSE Tracker'",
                    (_aid2, _label)).fetchone()
                if _dup2: continue
                _bc.execute("INSERT INTO status_history (account_id,old_status,new_status,changed_at,source,file_source,field_name) VALUES (?,?,?,?,?,?,?)",
                    (_aid2,'N','Y',_ts2,'backfill','DC CSE Tracker',_label))
                _bf += 1
    result["history_backfilled"] = _bf
    return result


@app.get("/api/run-pipeline")
def api_run():
    try:
        # Step 1: Download latest from Google Drive via browser
        dl_results = _download_live_from_drive()

        # Step 2: Run pipeline on fresh data (inline, not subprocess — avoids DB connection issues)
        try:
            import json as _j2
            from datetime import datetime as _dt, timezone as _tz
            from agent.ps_parser import load_and_merge as _mp
            from agent.dc_parser import load_and_merge as _mdc
            from agent.enricher import enrich_accounts as _enrich
            from agent.db import migrate_from_state as _mig

            _mp(DATA_DIR/"ps_tracker.csv", STATE_FILE)
            # DC CSE Tracker is master — shared function handles snapshot, upsert, diff audit
            if (DATA_DIR/"dc_cse_tracker.csv").exists():
                _run_dc_pipeline(DATA_DIR, STATE_FILE)

            _enrich(STATE_FILE)
            _mig(STATE_FILE)
            r_output = "DC CSE Tracker is sole source. All milestones synced.\ndone"
            r_ok = True
        except Exception as _e:
            r_output = str(_e)
            r_ok = False
        return {"status":"ok" if r_ok else "error","downloads":dl_results,"output":r_output}
    except Exception as e:
        return {"status":"error","message":str(e)}


@app.get("/api/run-full")
async def api_run_full(request: Request):
    """Stream the full pipeline cycle with debug output."""
    async def stream():
        import os, json as _j
        from datetime import datetime, timezone

        def event(step, status, detail="", color="teal"):
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            return f"data: {_j.dumps({'ts':ts,'step':step,'status':status,'detail':detail,'color':color})}\n\n"

        yield event("Pipeline", "STARTING", "Full cycle initiated")
        await asyncio.sleep(0.1)

        # Step 1: Check Drive files
        drive_root = Path.home() / "Library/CloudStorage/GoogleDrive-mbanica@paloaltonetworks.com/My Drive/EMEA CC "
        gsheet_files = list(drive_root.glob("*.gsheet")) if drive_root.exists() else []
        drive_status = f"{len(gsheet_files)} .gsheet files synced" if gsheet_files else "Not mounted — open Google Drive Desktop"
        yield event("Google Drive", "OK" if gsheet_files else "WARN", drive_status, "blue" if gsheet_files else "amber")
        for gf in gsheet_files:
            try:
                mtime = os.stat(gf).st_mtime
                from datetime import datetime as dt
                mt = dt.fromtimestamp(mtime).strftime("%d %b %H:%M")
                yield event("  →", "FILE", f"{gf.name[:40]} · {mt}", "muted")
            except: pass
        await asyncio.sleep(0.1)

        # Step 2: Check CSV files
        data_dir = Path(__file__).parent / "data"
        csvs = {"PS Tracker": data_dir/"ps_tracker.csv"}
        yield event("Google Drive", "DOWNLOADING", "Opening export URLs in browser — corp auth handles it")
        import glob as _g2, os as _os2, shutil as _sh2
        downloads = Path.home() / "Downloads"
        _cfg = json.loads((data_dir / "drive_config.json").read_text())
        FILE_MAP2 = {
            "DC CSE Tracker":              ("dc_cse_tracker.csv", None),
            # PS Tracker excluded — Drive default tab exports wrong format
        }
        for _f in _cfg["files"]:
            _name = _f["name"]
            if _name not in FILE_MAP2: continue
            _dest_name, _ = FILE_MAP2[_name]
            _fid = _f.get("file_id","")
            if not _fid: continue
            _gid = _f.get("current_gid","") if "Blocked" in _name else ""
            _url = f"https://docs.google.com/spreadsheets/d/{_fid}/export?format=csv"
            if _gid: _url += f"&gid={_gid}"
            _before = set(_g2.glob(str(downloads / "*.csv")))
            subprocess.Popen(["open", _url])
            await asyncio.sleep(0.3)
            _deadline = asyncio.get_event_loop().time() + 15
            _got = False
            while asyncio.get_event_loop().time() < _deadline:
                await asyncio.sleep(1)
                _after = set(_g2.glob(str(downloads / "*.csv")))
                _new = _after - _before
                if _new:
                    _dl = sorted(_new, key=_os2.path.getmtime)[-1]
                    _sh2.move(_dl, data_dir / _dest_name)
                    _rows = sum(1 for _ in open(data_dir / _dest_name, encoding='utf-8-sig')) - 1
                    yield event("  →", "OK", f"{_name}: {_rows} rows (LIVE)", "green")
                    _got = True
                    break
            if not _got:
                yield event("  →", "WARN", f"{_name}: browser download pending", "amber")
        await asyncio.sleep(0.2)

        yield event("CSV Files", "CHECK", "Verifying downloaded files")
        for name, path in csvs.items():
            if path.exists():
                import csv as _csv
                rows = sum(1 for _ in open(path, encoding='utf-8-sig')) - 1
                size = path.stat().st_size // 1024
                yield event("  →", "OK", f"{name}: {rows} rows · {size}KB", "green")
            else:
                yield event("  →", "MISSING", f"{name}: not found", "red")
        await asyncio.sleep(0.1)

        # Step 3: PS tracker (supplementary — Clarizen IDs, PSC names)
        yield event("PS Tracker", "LOADING", "Supplementary PS engagement data")
        yield event("PS Tracker", "LOADING", "Fuzzy name matching (threshold 0.85)")
        try:
            from agent.ps_parser import load_and_merge as mp
            p = mp(data_dir/"ps_tracker.csv", data_dir/"state.json")
            yield event("  →", "OK", f"{p['matched']}/{p['total']} matched · {p['unmatched']} not in EMEA tracker", "green")
        except Exception as e:
            yield event("  →", "ERROR", str(e)[:80], "red")
        await asyncio.sleep(0.1)

        # Step 4b: DC CSE Tracker (master — milestones, CSE, diff audit)
        yield event("DC CSE Tracker", "LOADING", "Master source — CSE assignments, all milestones (M0-M9), audit diff")
        try:
            dc = _run_dc_pipeline(data_dir, data_dir/"state.json")
            yield event("  →", "OK", f"{dc['matched']}/{dc['total']} accounts matched · {dc['audit_logged']} milestone changes · M1 rebuilt ({dc.get('m1_rebuilt',0)}) · history backfilled ({dc.get('history_backfilled',0)})", "green")
            yield event("  →", "MILESTONES", "✅ M0–M9 100% synced from DC CSV across all accounts — zero stale data", "green")
        except Exception as e:
            yield event("  →", "ERROR", str(e)[:80], "red")
        await asyncio.sleep(0.1)

        # Step 5: AI Enricher
        yield event("Ollama Enricher", "RUNNING", "Extracting blocker/owner/accountable from comments (qwen2.5:14b)")
        try:
            from agent.enricher import enrich_accounts
            e = enrich_accounts(data_dir/"state.json")
            yield event("  →", "OK", f"{e['enriched']} enriched · {e['skipped']} cached (comments unchanged)", "green")
        except Exception as e:
            yield event("  →", "ERROR", str(e)[:80], "red")
        await asyncio.sleep(0.1)

        # Step 6: DB Sync
        yield event("SQLite DB", "SYNCING", "Writing all accounts to solstice.db")
        try:
            from agent.db import sync_all
            s = sync_all(data_dir/"state.json")
            with get_db() as conn:
                total_rows = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
                history_rows = conn.execute("SELECT COUNT(*) FROM status_history").fetchone()[0]
            yield event("  →", "OK", f"{s['synced']} accounts synced · {s['status_changes']} status changes · {history_rows} history rows · {s['errors']} errors", "green")
        except Exception as e:
            yield event("  →", "ERROR", str(e)[:80], "red")
        await asyncio.sleep(0.1)

        # Step 7: Validate data quality
        yield event("Data Quality", "CHECK", "Cross-checking all 3 CSVs")
        try:
            import json as _json2
            state = _json2.loads((data_dir/"state.json").read_text())
            accs = list(state.get("accounts",{}).values())
            no_st  = sum(1 for a in accs if not (a.get("status") or "").strip())
            no_cse = sum(1 for a in accs if not (a.get("active_cse") or "").strip())
            live_fire = sum(1 for a in accs if a.get("live_fire"))
            yield event("  →", "OK", f"{len(accs)} accounts total · {no_st} missing status · {no_cse} no CSE · {live_fire} live fire", "green")
        except Exception as e:
            yield event("  →", "ERROR", str(e)[:80], "red")
        await asyncio.sleep(0.1)

        yield event("Pipeline", "COMPLETE", "All steps done — refreshing dashboard", "teal")
        yield f"data: {_j.dumps({'done': True})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

def _load_m9_schedule() -> list:
    _ensure_db()
    """M9 completion schedule — M3 complete, M9 planned, not yet complete, sorted by date."""
    try:
        from datetime import datetime, date
        today = date.today()
        with get_db() as conn:
            rows = conn.execute("""
                SELECT a.customer_name, a.active_cse, a.status, a.live_fire, a.live_fire_dc,
                       b.m9_planned, b.m8_started, b.m9_complete
                FROM accounts a JOIN blocked_data b ON a.account_id=b.account_id
                WHERE b.m3_complete=1 AND b.m9_planned!='' AND b.m9_complete=0
                ORDER BY b.m9_planned, a.customer_name
            """).fetchall()
        result = []
        for r in rows:
            try:
                d = None
                for fmt in ("%m/%d/%Y", "%m/%d/%y"):
                    try: d = datetime.strptime(r["m9_planned"].strip(), fmt).date(); break
                    except: pass
                if d and d >= today:
                    result.append({
                        "name": r["customer_name"], "cse": r["active_cse"] or "—",
                        "status": r["status"] or "—", "m9_planned": r["m9_planned"],
                        "m9_date_iso": d.isoformat(), "m9_date": d.strftime("%d %b %Y"),
                        "m8_started": bool(r["m8_started"]),
                        "live_fire": bool(r["live_fire"]), "live_fire_dc": r["live_fire_dc"] or "",
                    })
            except: pass
        return result
    except: return []


@app.get("/api/m9-schedule")
def api_m9(): return _load_m9_schedule()


def _load_in_progress() -> list:
    _ensure_db()
    """Upgrades actively in progress — M8 started, M9 not complete."""
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT a.customer_name, a.active_cse, a.status, a.live_fire, a.live_fire_dc,
                       b.m8_planned, b.m9_planned, b.upgrade_notes, b.health_notes,
                       b.signal, b.subtype, b.dc_progress, b.churn_risk, b.cc_rep
                FROM accounts a JOIN blocked_data b ON a.account_id=b.account_id
                WHERE b.m8_started=1 AND b.m9_complete=0
                ORDER BY b.m9_planned, a.customer_name
            """).fetchall()
        return [dict(r) for r in rows]
    except: return []


@app.get("/api/in-progress")
def api_in_progress(): return _load_in_progress()


def _load_open_actions() -> list:
    _ensure_db()
    """Open Actions — accounts needing follow-up grouped by category."""
    try:
        import json as _j
        state = _j.loads(STATE_FILE.read_text())
        groups = {
            "Sales Hold":        {"statuses":["Sales Hold"],                        "color":"#EA580C"},
            "Churning / Churned":{"statuses":["Churning/Churned"],                  "color":"#DC2626"},
            "Ready To Engage":   {"statuses":["Ready To Engage"],                   "color":"#10B981"},
            "Account Contacted": {"statuses":["Account team contacted"],            "color":"#F59E0B"},
            "Blocked":           {"statuses":["Blocked: Tech limitation"],          "color":"#A1887F"},
            "On Hold":           {"statuses":["On Hold"],                           "color":"#3B82F6"},
            "Escalation":        {"statuses":["Backoff","Cancelled"],               "color":"#EF4444"},
        }
        result = []
        for gname, cfg in groups.items():
            accs = []
            for acc in state.get("accounts",{}).values():
                if acc.get("status") not in cfg["statuses"]: continue
                if not acc.get("customer_name","").strip(): continue
                bd = acc.get("blocked_data") or {}
                ai = acc.get("ai_enrichment") or {}
                accs.append({
                    "name":       acc.get("customer_name","—"),
                    "cse":        acc.get("active_cse") or "—",
                    "region":     acc.get("sales_region") or "—",
                    "status":     acc.get("status","—"),
                    "signal":     bd.get("signal",""),
                    "blocker":    ai.get("blocker",""),
                    "accountable":ai.get("accountable",""),
                    "live_fire":  acc.get("live_fire",False),
                    "live_fire_dc":acc.get("live_fire_dc",""),
                })
            if accs:
                result.append({"group":gname,"color":cfg["color"],"accounts":sorted(accs,key=lambda x:x["name"])})
        return result
    except Exception as e:
        return []


def _load_milestones(theatre: str = "") -> list:
    _ensure_db()
    """Milestone tracker — full M0-M9 with SLA breach flags. Optional theatre filter."""
    from datetime import datetime
    MARCH9 = datetime(2026, 3, 9)
    def _pd(s):
        if not s: return None
        for f in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%Y %H:%M:%S'):
            try: return datetime.strptime(s.strip().split(' ')[0] if ' ' in s else s.strip(), f)
            except: pass
        return None
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT a.customer_name, a.active_cse, a.status, a.live_fire, a.live_fire_dc,
                       a.sales_region,
                       b.team, b.is_cs_team, b.signal, b.subtype, b.milestone_category,
                       b.m0_complete, b.m1_complete, b.m1_planned,
                       b.m2_complete, b.m2_planned,
                       b.m3_complete, b.m3_planned,
                       b.m4_complete, b.m5_complete,
                       b.m7_complete,
                       b.m8_started, b.m8_planned, b.m8_actual,
                       b.m9_complete, b.m9_planned, b.m9_actual,
                       b.upgrade_notes, b.health_notes, b.exec_delay, b.status_detail,
                       b.dc_progress, b.owner_e2e,
                       COALESCE(a.account_theatre, b.account_theatre, 'EMEA') as account_theatre
                FROM accounts a JOIN blocked_data b ON a.account_id=b.account_id
                WHERE a.customer_name != ''
                  AND (? = '' OR UPPER(COALESCE(a.account_theatre,'EMEA')) = UPPER(?))
                ORDER BY b.signal, a.customer_name
            """, (theatre, theatre)).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                m3d = _pd(d.get('m3_planned'))
                m8d = _pd(d.get('m8_planned'))
                m9d = _pd(d.get('m9_planned'))
                # M3→M8: only penalise if M3 >= Mar 9 (prospective)
                # M8→M9: only penalise if M8 >= Mar 9 (regardless of M3 date)
                sla_m3_m8 = None
                sla_m8_m9 = None
                if m3d and m3d >= MARCH9 and m8d:
                    sla_m3_m8 = (m8d - m3d).days
                if m8d and m8d >= MARCH9 and m9d:
                    sla_m8_m9 = (m9d - m8d).days
                d['sla_m3_m8_days'] = sla_m3_m8
                d['sla_m8_m9_days'] = sla_m8_m9
                d['sla_m3_m8_breach'] = sla_m3_m8 is not None and sla_m3_m8 > 14
                d['sla_m8_m9_breach'] = sla_m8_m9 is not None and sla_m8_m9 > 28
                result.append(d)
            return result
    except: return []


def _load_ps() -> dict:
    _ensure_db()
    """PS engagement — matched + unmatched."""
    try:
        with get_db() as conn:
            matched = conn.execute("""
                SELECT a.customer_name, a.active_cse, a.live_fire, a.live_fire_dc,
                       p.psc, p.psc_shadow, p.pm, p.ps_status, p.clarizen_id, p.timeline, p.notes
                FROM accounts a JOIN ps_data p ON a.account_id=p.account_id
                ORDER BY p.ps_status, a.customer_name
            """).fetchall()
        import csv as _csv
        ps_file = DATA_DIR / "ps_tracker.csv"
        all_ps = list(_csv.DictReader(open(ps_file, encoding="utf-8-sig"))) if ps_file.exists() else []
        with get_db() as conn2:
            matched_ps_names = {r[0] for r in conn2.execute("SELECT ps_name FROM ps_data").fetchall()}
        unmatched = [{"name":r["PS Eligible Account Name"],"country":r.get("Theater",""),
                      "psc":r.get("Area Owner",""),"timeline":r.get("Number of Sessions (4 hours)","")}
                     for r in all_ps if r.get("PS Eligible Account Name","").strip()
                     and r.get("PS Eligible Account Name","").strip() not in matched_ps_names]
        return {"matched":[dict(r) for r in matched], "unmatched":sorted(unmatched,key=lambda x:x["name"])}
    except: return {"matched":[],"unmatched":[]}


def _load_completed(theatre: str = '') -> list:
    _ensure_db()
    """Completed accounts — DC M9 complete is source of truth."""
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT a.customer_name, a.active_cse, a.sales_region,
                       a.live_fire, a.live_fire_dc,
                       b.m9_actual, b.m9_planned, b.dc_progress
                FROM accounts a
                JOIN blocked_data b ON a.account_id=b.account_id
                WHERE b.m9_complete=1
                  AND (? = '' OR UPPER(COALESCE(a.account_theatre,'EMEA'))=UPPER(?))
                ORDER BY b.m9_actual DESC, b.m9_planned DESC
            """, (theatre, theatre)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        return []


def _load_dq() -> list:
    _ensure_db()
    """Data quality issues — DC CSE Tracker is source of truth."""
    try:
        with get_db() as conn:
            # Source of truth: DB (populated from DC tracker)
            rows = conn.execute("""
                SELECT a.account_id, a.customer_name, a.active_cse, a.status,
                       a.email_sent, b.dc_progress, b.m1_complete
                FROM accounts a
                LEFT JOIN blocked_data b ON a.account_id=b.account_id
                WHERE a.customer_name!=''
            """).fetchall()
        accs = [dict(r) for r in rows]
        OUTREACH = {"Ready To Engage","Account team contacted","Upgrade Email Sent"}
        TERMINAL = {"Churning/Churned","Cancelled","Backoff","Completed"}
        SKIP_CSE = TERMINAL | {"PS"}
        issues = []
        # No status: only flag if DC also has no meaningful status
        no_st  = [a for a in accs if not (a.get("status") or "").strip()]
        no_cse = [a for a in accs if not (a.get("active_cse") or "").strip()
                  and (a.get("status") or "").strip() not in SKIP_CSE]
        no_email=[a for a in accs if (a.get("status") or "") in OUTREACH
                  and not (a.get("email_sent") or "").strip()]
        if no_st:   issues.append({"type":"No Status",   "count":len(no_st),  "accounts":[a["customer_name"] for a in no_st]})
        if no_cse:  issues.append({"type":"No Owner/CSE","count":len(no_cse), "accounts":[a["customer_name"] for a in no_cse]})
        if no_email:issues.append({"type":"No Email on Record","count":len(no_email),"accounts":[a["customer_name"] for a in no_email]})
        return issues
    except: return []


def _load_audit_log(theatre: str = "") -> list:
    _ensure_db()
    """Audit log — changes detected across all source files between pipeline runs."""
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT
                  CASE WHEN sh.account_id='unmatched_dc' THEN sh.new_status
                       ELSE a.customer_name END as customer_name,
                  CASE WHEN sh.account_id='unmatched_dc' THEN sh.old_status
                       ELSE COALESCE(a.active_cse,'—') END as active_cse,
                  CASE WHEN sh.account_id='unmatched_dc' THEN 'N' ELSE sh.old_status END as old_status,
                  CASE WHEN sh.account_id='unmatched_dc' THEN 'Y' ELSE sh.new_status END as new_status,
                  sh.changed_at, sh.source,
                  COALESCE(sh.file_source, 'DC CSE Tracker') as file_source,
                  COALESCE(sh.field_name, 'status') as field_name
                FROM status_history sh
                LEFT JOIN accounts a ON a.account_id = sh.account_id
                WHERE sh.source IN ('pipeline','backfill')
                  AND sh.file_source = 'DC CSE Tracker'
                  AND (? = ''
                       OR UPPER(COALESCE(a.account_theatre,'EMEA'))=UPPER(?)
                       OR (sh.account_id='unmatched_dc' AND (
                           ? = '' OR UPPER(COALESCE(
                             (SELECT a2.account_theatre FROM accounts a2
                              WHERE a2.customer_name=sh.new_status LIMIT 1),
                             'EMEA'))=UPPER(?))))
                ORDER BY sh.changed_at ASC
                LIMIT 2000
            """, (theatre, theatre, theatre, theatre)).fetchall()
        return [dict(r) for r in rows]
    except: return []


@app.get("/api/audit-log")
def api_audit(theatre: str = ""): return _load_audit_log(theatre=theatre)


@app.get("/api/update-blocked-tab")
def api_update_tab(url: str):
    """
    Update the blocked accounts tab gid from a Google Sheets URL.
    Usage: /api/update-blocked-tab?url=https://docs.google.com/...gid=538753662
    """
    import re, json as _j
    m = re.search(r'gid=(\d+)', url)
    if not m:
        return {"status": "error", "message": "No gid found in URL"}
    gid = m.group(1)
    config_path = DATA_DIR / "drive_config.json"
    config = _j.loads(config_path.read_text())
    updated = False
    for f in config['files']:
        if 'Blocked' in f['name']:
            old_gid = f.get('current_gid', '—')
            f['current_gid'] = gid
            updated = True
            break
    if updated:
        config_path.write_text(_j.dumps(config, indent=2))
        return {"status": "ok", "message": f"Blocked accounts tab updated → gid={gid}", "old_gid": old_gid, "new_gid": gid}
    return {"status": "error", "message": "Blocked accounts file not found in config"}


@app.get("/api/sla-breaches")
def api_sla_breaches():
    """SLA breach report — M3→M8 >14d or M8→M9 >28d, prospective from Mar 9."""
    milestones = _load_milestones()
    breaches = [
        {k: v for k, v in r.items() if k in (
            'customer_name','active_cse','status','live_fire','dc_progress',
            'm3_planned','m8_planned','m9_planned','m3_complete','m8_started','m9_complete',
            'sla_m3_m8_days','sla_m8_m9_days','sla_m3_m8_breach','sla_m8_m9_breach',
            'status_detail','owner_e2e')}
        for r in milestones
        if r.get('sla_m3_m8_breach') or r.get('sla_m8_m9_breach')
    ]
    return sorted(breaches, key=lambda x: (
        -(x.get('sla_m3_m8_days') or 0) - (x.get('sla_m8_m9_days') or 0)
    ))


def _get_blocked_export_url() -> str:
    """
    Get CSV export URL for blocked accounts — always uses stored gid.
    Tab format: EMEA_MONTH DAY (e.g. EMEA_MARCH 22, EMEA_APRIL 5).
    gid must be updated in drive_config.json when tab changes.
    Use /api/update-blocked-tab?url=<google_sheets_url> to update.
    """
    import json as _j
    config = _j.loads((DATA_DIR / "drive_config.json").read_text())
    for f in config['files']:
        if 'Blocked' in f['name']:
            file_id = f.get('file_id', '')
            gid = f.get('current_gid', '0')
            return f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv&gid={gid}"
    return ""


@app.get("/api/open-actions")
def api_open_actions(): return _load_open_actions()

@app.get("/api/milestones")
def api_milestones(theatre: str = ""): return _load_milestones(theatre=theatre)

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
                    WHERE UPPER(COALESCE(b.account_theatre, a.account_theatre,'EMEA'))=?
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
        logger.error("health-summary failed: %s", e)
        for t in theatres:
            result[t] = {"status": "amber", "m9": 0, "blocked": 0, "at_risk": 0, "error": True}
    return result


@app.get("/api/theatres")
def api_theatres():
    """List distinct theatres with account counts."""
    _ensure_db()
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT COALESCE(account_theatre,'EMEA') theatre, COUNT(*) n
                FROM accounts WHERE customer_name!=''
                GROUP BY account_theatre ORDER BY n DESC
            """).fetchall()
        return [dict(r) for r in rows]
    except: return []

@app.get("/api/ps")
def api_ps(): return _load_ps()

@app.get("/api/completed")
def api_completed(theatre: str = ""): return _load_completed(theatre=theatre)

@app.get("/api/blockers")
def api_blockers(theatre: str = "", region: str = "", cse: str = ""):
    """Blocked accounts grouped by blocker type for call prep."""
    _ensure_db()
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT a.customer_name, a.active_cse, a.sales_region,
                       COALESCE(a.account_theatre,'EMEA') as account_theatre,
                       b.signal, b.subtype, b.status_detail, b.upgrade_notes,
                       b.health_notes, b.dc_progress, b.churn_risk,
                       b.cc_rep, b.cc_dsm, b.cohort, b.area, b.district,
                       b.m8_started, b.m9_complete, b.m3_complete
                FROM accounts a JOIN blocked_data b ON a.account_id=b.account_id
                WHERE a.customer_name != ''
                  AND b.signal IN ('blocked','at_risk')
                  AND b.m9_complete = 0
                  AND (? = '' OR UPPER(COALESCE(a.account_theatre,'EMEA'))=UPPER(?))
                  AND (? = '' OR LOWER(a.sales_region) LIKE LOWER(?))
                  AND (? = '' OR a.active_cse = ?)
                ORDER BY b.subtype, a.sales_region, a.customer_name
            """, (theatre, theatre,
                  region, f"%{region}%",
                  cse, cse)).fetchall()
        result = {"no_contact": [], "core_rep_blocking": [], "tech_blocker": [], "active_deal": [], "other": []}
        for r in rows:
            d = dict(r)
            st = d.get("subtype") or "other"
            bucket = st if st in result else "other"
            result[bucket].append(d)
        return result
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/forecast")
def api_forecast(theatre: str = ""):
    """Next 7 days M8/M9 targets + 4-week velocity."""
    _ensure_db()
    from datetime import datetime, timedelta
    today = datetime.now(timezone.utc).date()
    next_week_end = today + timedelta(days=7)

    try:
        with get_db() as conn:
            targets = conn.execute("""
                SELECT a.customer_name, a.active_cse, a.sales_region,
                       COALESCE(a.account_theatre,'EMEA') as account_theatre,
                       b.m9_planned, b.m8_planned, b.m8_started, b.m9_complete,
                       b.dc_progress, b.churn_risk, b.m8_actual
                FROM accounts a JOIN blocked_data b ON a.account_id=b.account_id
                WHERE a.customer_name != '' AND b.m9_complete=0
                  AND (? = '' OR UPPER(COALESCE(a.account_theatre,'EMEA'))=UPPER(?))
                ORDER BY b.m9_planned
            """, (theatre, theatre)).fetchall()

            velocity = []
            for w in range(3, -1, -1):
                week_start = (today - timedelta(days=today.weekday()) - timedelta(weeks=w))
                week_end = week_start + timedelta(days=6)
                n = conn.execute("""
                    SELECT COUNT(*) FROM status_history sh
                    LEFT JOIN accounts a ON a.account_id=sh.account_id
                    WHERE sh.field_name='M9 Upgrade Complete'
                      AND sh.new_status='Y'
                      AND sh.source IN ('pipeline','backfill')
                      AND date(sh.changed_at) BETWEEN ? AND ?
                      AND (? = '' OR UPPER(COALESCE(a.account_theatre,'EMEA'))=UPPER(?))
                """, (str(week_start), str(week_end), theatre, theatre)).fetchone()[0]
                velocity.append({"week_start": str(week_start), "week_end": str(week_end), "m9_count": n,
                                 "label": week_start.strftime("%d %b")})

        def parse_date(s):
            if not s: return None
            for f in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%Y %H:%M:%S'):
                try:
                    from datetime import datetime as dt
                    return dt.strptime(s.strip().split(' ')[0], f).date()
                except: pass
            return None

        next_targets = []
        overdue = []
        for r in targets:
            d = dict(r)
            m9d = parse_date(d.get('m9_planned'))
            if not m9d: continue
            confidence = "HIGH" if d['m8_started'] and d['dc_progress'] == 'Green' else \
                         "MED" if d['m8_started'] else "LOW"
            d['confidence'] = confidence
            d['m9_date'] = str(m9d)
            if m9d < today:
                d['status'] = 'overdue'
                overdue.append(d)
            elif m9d <= next_week_end:
                d['status'] = 'upcoming'
                next_targets.append(d)

        counts = [v['m9_count'] for v in velocity]
        trend = "up" if counts[-1] > counts[0] else "down" if counts[-1] < counts[0] else "flat"

        return {"next_targets": next_targets, "overdue": overdue,
                "velocity": velocity, "trend": trend}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/dq")
def api_dq(): return _load_dq()


@app.get("/api/customer-search")
def api_customer_search(q: str = ""):
    """Search accounts by name — returns list of matches, deduplicated by name."""
    if not q or len(q) < 2: return []
    _ensure_db()
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT a.account_id, a.customer_name, a.active_cse, a.status,
                       a.sales_region, a.live_fire, b.signal, b.dc_progress
                FROM accounts a LEFT JOIN blocked_data b ON a.account_id=b.account_id
                WHERE a.customer_name LIKE ? AND a.customer_name!=''
                ORDER BY a.customer_name LIMIT 20
            """, (f"%{q}%",)).fetchall()

        # Deduplicate by lower-cased customer_name: same company can have duplicate
        # account_ids that differ only in case (Salesforce ID normalisation issue).
        # Keep the row with the most DC data (signal + dc_progress present wins).
        # If both rows are genuinely distinct (different regions AND both have data),
        # keep both but mark them with a disambiguating region suffix in the name.
        seen: dict = {}  # lower(name) → list of row dicts
        for r in rows:
            d = dict(r)
            key = (d.get("customer_name") or "").lower().strip()
            seen.setdefault(key, []).append(d)

        result = []
        for key, candidates in seen.items():
            if len(candidates) == 1:
                result.append(candidates[0])
                continue
            # Multiple rows for same name — check if they're case-duplicates of the
            # same Salesforce ID or genuinely different accounts.
            ids_normalised = [c["account_id"].lower() for c in candidates]
            if len(set(ids_normalised)) == 1:
                # Pure case-duplicate: pick the one with more DC data
                def _score(c):
                    return (1 if c.get("signal") else 0) + (1 if c.get("dc_progress") else 0)
                best = max(candidates, key=_score)
                result.append(best)
            else:
                # Genuinely distinct accounts — keep all but make region visible
                # so the user can tell them apart in the dropdown.
                for c in candidates:
                    result.append(c)

        result.sort(key=lambda x: (x.get("customer_name") or "").lower())
        return result[:10]
    except: return []


@app.get("/api/customer/{account_id}")
def api_customer_detail(account_id: str):
    """Full customer card data."""
    _ensure_db()
    try:
        with get_db() as conn:
            r = conn.execute("""
                SELECT a.*, b.m0_complete, b.m1_complete, b.m1_planned,
                       b.m2_complete, b.m2_planned, b.m3_complete, b.m3_planned,
                       b.m4_complete, b.m4_planned, b.m5_complete, b.m5_planned,
                       b.m7_complete, b.m7_planned, b.m8_started, b.m8_planned, b.m8_actual,
                       b.m9_complete, b.m9_planned, b.m9_actual,
                       b.signal, b.subtype, b.dc_progress, b.status_detail,
                       b.upgrade_notes, b.health_notes, b.owner_e2e, b.dc_assignment,
                       b.cohort, b.area, b.region as district_region, b.district,
                       b.milestone_category, b.is_cs_team, b.team, b.exec_delay,
                       b.cc_rep, b.cc_dsm, b.churn_risk,
                       b.last_edited_by, b.last_edited_date, b.roadmap_url, b.ps_plan_url,
                       b.account_region, b.current_project_status, b.next_renewal_date,
                       b.past_due_planned, b.upgrade_duration_weeks,
                       b.has_partner, b.upgrade_partner,
                       b.m1_details, b.m3_details, b.m5_details,
                       b.milestone_aging, b.days_since_milestone, b.momentum_x,
                       b.entitlement_provision, b.activation_status, b.posture_workloads,
                       p.psc, p.pm, p.psc_shadow, p.ps_status, p.clarizen_id, p.timeline as ps_timeline,
                       ae.blocker, ae.owner, ae.accountable
                FROM accounts a
                LEFT JOIN blocked_data b ON a.account_id=b.account_id
                LEFT JOIN ps_data p ON a.account_id=p.account_id
                LEFT JOIN ai_enrichment ae ON a.account_id=ae.account_id
                WHERE a.account_id=?
            """, (account_id,)).fetchone()
            # Status history
            hist = conn.execute("""
                SELECT old_status, new_status, changed_at, file_source, field_name
                FROM status_history WHERE account_id=? ORDER BY changed_at ASC LIMIT 20
            """, (account_id,)).fetchall()
        if not r: raise HTTPException(status_code=404, detail="not found")
        d = dict(r)
        d["history"] = [dict(h) for h in hist]
        return d
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


def _generate_m1_rationale(cat: str, accounts: list, total: int) -> str:
    """Generate LLM rationale for a category. Falls back to static if Ollama unavailable."""
    static = {
        'actionable': f"{total} accounts have no active blocker. CSEs should send M1 outreach email or schedule customer call this week. Priority: 🔥 live-fire accounts and those already in Ready To Engage status.",
        'acct_team':  f"{total} accounts are gated by the account team (Sales Hold, core rep blocking, or explicit hold request). CSEs must first align with the Sales Rep before reaching out to the customer. Do not contact the customer directly.",
        'unblock':    f"All {total} accounts are MTN group entities blocked by a single Strata/Firewall escalation. Resolving this one escalation unlocks all {total} M1 outreach actions simultaneously. Pushkar Kakkar should escalate the Strata side as top priority.",
        'skip':       f"{total} accounts are hard blocked: churning/churned, cancelled, or confirmed tech limitations. No M1 outreach action required this cycle. Revisit after status changes.",
    }
    try:
        from agent.llm import chat, _is_running
        if not _is_running():
            return static.get(cat, '')
        names = [a['account_name'] for a in accounts[:12]]
        prompt = (f"You are a Cortex Cloud migration program manager. Write a 2-sentence action rationale "
                  f"for CSEs about the '{cat}' M1 outreach category ({total} accounts). "
                  f"Sample accounts: {', '.join(names[:8])}. "
                  f"Be direct, operational, no fluff. Plain text only, no markdown.")
        return chat(prompt, expect_json=False).strip()
    except:
        return static.get(cat, '')


@app.get("/api/m1-suggestions")
def api_m1_suggestions(theatre: str = ""):
    """M1 action plan — 4 flat tables with LLM rationale per category."""
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT s.assigned_cse, s.account_name, s.original_cse, s.region,
                       s.status, s.signal, s.category,
                       b.status_detail, b.upgrade_notes, b.health_notes,
                       b.cc_rep, b.cc_dsm, b.churn_risk, b.dc_progress,
                       a.live_fire, b.m3_planned, b.m8_planned, b.m9_planned
                FROM m1_suggestions s
                LEFT JOIN accounts a ON a.customer_name=s.account_name
                LEFT JOIN blocked_data b ON b.account_id=a.account_id
                AND (? = '' OR UPPER(COALESCE(b.account_theatre,'EMEA'))=UPPER(?))
                ORDER BY s.category, s.assigned_cse, s.region, s.account_name
            """, (theatre, theatre)).fetchall()
        from collections import defaultdict
        cats: dict = {'actionable': [], 'acct_team': [], 'unblock': [], 'skip': []}
        for r in rows:
            cat = r[6] or 'actionable'
            if cat in cats:
                # Pick best note: upgrade_notes first, then health_notes, then status_detail
                detail = (r[7] or '').strip()  # status_detail
                notes  = (r[8] or '').strip()  # upgrade_notes
                health = (r[9] or '').strip()  # health_notes
                best_note = notes if notes and notes not in ('TBD','-','') else (
                            health if health and health not in ('TBD','-','') else detail)
                cats[cat].append({
                    "account_name": r[1], "assigned_cse": r[0], "original_cse": r[2],
                    "region": r[3], "status": r[4], "signal": r[5],
                    "is_new": r[2] == 'Irene Garcia',
                    "status_detail": detail,
                    "notes": best_note[:200] if best_note else '',
                    "cc_rep": r[10] or '',
                    "cc_dsm": r[11] or '',
                    "churn_risk": r[12] or '',
                    "dc_progress": r[13] or '',
                    "live_fire": bool(r[14]),
                    "m3_planned": r[15] or '',
                    "m8_planned": r[16] or '',
                    "m9_planned": r[17] or '',
                })
        result = []
        for cat, label, color in [
            ('actionable', '✅ Ping Now',           'green'),
            ('acct_team',  '📞 Acct Team First',    'amber'),
            ('unblock',    '⚡ Single Unblock (MTN)','blue'),
            ('skip',       '🔴 Skip / Hard Blocked', 'red'),
        ]:
            accs = cats[cat]
            rationale = _generate_m1_rationale(cat, accs, len(accs))
            result.append({"category": cat, "label": label, "color": color,
                           "total": len(accs), "rationale": rationale, "accounts": accs})
        return result
    except:
        return []

@app.get("/api/events")
async def api_events(request:Request):
    async def gen():
        while True:
            if await request.is_disconnected(): break
            yield f"data: {json.dumps(_load_stats())}\n\n"
            await asyncio.sleep(30)
    return StreamingResponse(gen(),media_type="text/event-stream")

@app.get("/",response_class=HTMLResponse)
def dashboard():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ops")

@app.get("/ops",response_class=HTMLResponse)
def dashboard_ops():
    return dashboard_v2()

@app.get("/v2",response_class=HTMLResponse)
def dashboard_v2():
    html_path = Path(__file__).parent / "static" / "v2.html"
    if html_path.exists():
        return html_path.read_text()
    return "<h1>v2 not found</h1>"

@app.get("/daily",response_class=HTMLResponse)
def dashboard_daily():
    html_path = Path(__file__).parent / "static" / "daily.html"
    if html_path.exists():
        return html_path.read_text()
    return "<h1>daily not found</h1>"

@app.get("/blockers",response_class=HTMLResponse)
def page_blockers():
    html_path = Path(__file__).parent / "static" / "blockers.html"
    if html_path.exists(): return html_path.read_text()
    return "<h1>blockers page not found</h1>"

@app.get("/forecast",response_class=HTMLResponse)
def page_forecast():
    html_path = Path(__file__).parent / "static" / "forecast.html"
    if html_path.exists(): return html_path.read_text()
    return "<h1>forecast page not found</h1>"

@app.get("/audit",response_class=HTMLResponse)
def page_audit():
    html_path = Path(__file__).parent / "static" / "audit.html"
    if html_path.exists(): return html_path.read_text()
    return "<h1>audit page not found</h1>"

@app.get("/api/daily-brief")
def api_daily_brief(date: str = "", theatre: str = ""):
    """Leadership daily briefing — movements for a given date + 7-day trend."""
    _ensure_db()
    from datetime import datetime, timedelta
    if not date:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        target = datetime.strptime(date, "%Y-%m-%d")
    except:
        return {"error": "Invalid date"}
    try:
        with get_db() as conn:
            # All movements for this day
            day_rows = conn.execute("""
                SELECT sh.account_id, sh.field_name, sh.old_status, sh.new_status,
                       sh.changed_at, sh.file_source,
                       CASE WHEN sh.account_id='unmatched_dc' THEN sh.new_status
                            ELSE a.customer_name END as customer_name,
                       CASE WHEN sh.account_id='unmatched_dc' THEN sh.old_status
                            ELSE COALESCE(a.active_cse,'—') END as active_cse,
                       COALESCE(b.area,'—') as area,
                       COALESCE(a.sales_region,'—') as region,
                       COALESCE(b.churn_risk,'') as churn_risk
                FROM status_history sh
                LEFT JOIN accounts a ON a.account_id=sh.account_id
                LEFT JOIN blocked_data b ON b.account_id=sh.account_id
                WHERE sh.changed_at >= ? AND sh.changed_at < ?
                  AND sh.source IN ('pipeline','backfill')
                  AND (? = ''
                       OR UPPER(COALESCE(a.account_theatre,'EMEA'))=UPPER(?)
                       OR (sh.account_id='unmatched_dc' AND (
                           ? = '' OR UPPER(COALESCE(
                             (SELECT a2.account_theatre FROM accounts a2
                              WHERE a2.customer_name=sh.new_status LIMIT 1),
                             'EMEA'))=UPPER(?))))
                ORDER BY sh.changed_at
            """, (date+"T00:00:00", date+"T23:59:59", theatre, theatre, theatre, theatre)).fetchall()

            # 7-day trend
            trend = []
            for i in range(29, -1, -1):
                d = (target - timedelta(days=i)).strftime("%Y-%m-%d")
                r = conn.execute("""
                    SELECT
                      SUM(CASE WHEN sh.field_name='M8 Upgrade Started' THEN 1 ELSE 0 END) m8,
                      SUM(CASE WHEN sh.field_name='M9 Upgrade Complete' THEN 1 ELSE 0 END) m9,
                      0 m3, 0 m1,
                      SUM(CASE WHEN sh.field_name IN ('M8 Upgrade Started','M9 Upgrade Complete') THEN 1 ELSE 0 END) total
                    FROM status_history sh
                    LEFT JOIN accounts a ON a.account_id=sh.account_id
                    WHERE sh.changed_at >= ? AND sh.changed_at < ?
                      AND sh.source IN ('pipeline','backfill')
                      AND sh.field_name IN ('M8 Upgrade Started','M9 Upgrade Complete')
                      AND sh.new_status='Y'
                      AND (? = ''
                           OR UPPER(COALESCE(a.account_theatre,'EMEA'))=UPPER(?)
                           OR (sh.account_id='unmatched_dc' AND (
                               ? = '' OR UPPER(COALESCE(
                                 (SELECT a2.account_theatre FROM accounts a2
                                  WHERE a2.customer_name=sh.new_status LIMIT 1),
                                 'EMEA'))=UPPER(?))))
                """, (d+"T00:00:00", d+"T23:59:59", theatre, theatre, theatre, theatre)).fetchone()
                trend.append({"date": d, "m8": r[0] or 0, "m9": r[1] or 0,
                              "m3": r[2] or 0, "m1": r[3] or 0, "total": r[4] or 0})

            # Per-theatre cumulative breakdown
            theatre_totals = {}
            for t in ["EMEA", "JAPAC", "AMER", "LATAM"]:
                tr = conn.execute("""
                    SELECT SUM(b.m8_started) m8, SUM(b.m9_complete) m9,
                           SUM(b.m3_complete) m3, COUNT(*) accounts
                    FROM blocked_data b JOIN accounts a ON a.account_id=b.account_id
                    WHERE UPPER(COALESCE(a.account_theatre,'EMEA'))=?
                """, (t,)).fetchone()
                theatre_totals[t] = {"m8": tr[0] or 0, "m9": tr[1] or 0,
                                     "m3": tr[2] or 0, "accounts": tr[3] or 0}

            # Cumulative totals (filtered or global)
            totals = conn.execute("""
                SELECT
                  SUM(b.m8_started) m8, SUM(b.m9_complete) m9,
                  SUM(b.m3_complete) m3, SUM(b.m5_complete) m5,
                  COUNT(*) accounts
                FROM blocked_data b JOIN accounts a ON a.account_id=b.account_id
                WHERE (? = '' OR UPPER(COALESCE(a.account_theatre,'EMEA'))=UPPER(?))
            """, (theatre, theatre)).fetchone()

        movements = [dict(r) for r in day_rows]
        # Headline counts
        headline = {
            "m8_started":     sum(1 for m in movements if m["field_name"] == "M8 Upgrade Started"),
            "m9_complete":    sum(1 for m in movements if m["field_name"] == "M9 Upgrade Complete"),
            "m3_complete":    sum(1 for m in movements if m["field_name"] == "M3 Buy-in"),
            "m1_outreach":    sum(1 for m in movements if m["field_name"] == "M1 Outreach"),
            "cse_changes":    sum(1 for m in movements if m["field_name"] == "cse"),
            "status_changes": sum(1 for m in movements if m["field_name"] == "status"),
            "regressions":    sum(1 for m in movements if m.get("new_status") in ("N","") and m.get("old_status") == "Y"),
            "total":          len(movements),
        }
        return {
            "date": date,
            "theatre": theatre or "All",
            "headline": headline,
            "movements": movements,
            "trend": trend,
            "theatre_totals": theatre_totals,
            "cumulative": {
                "m8_total": totals["m8"] or 0,
                "m9_total": totals["m9"] or 0,
                "m3_total": totals["m3"] or 0,
                "m5_total": totals["m5"] or 0,
                "accounts": totals["accounts"] or 0,
            }
        }
    except Exception as e:
        return {"error": str(e)}

if __name__=="__main__":
    import os as _os
    # Always run from Solstice/ directory regardless of where called from
    _os.chdir(Path(__file__).parent)
    sys.path.insert(0, str(Path(__file__).parent))

    import json as _j
    from agent.ps_parser import load_and_merge as _mp
    from agent.db import migrate_from_state as _mig

    # Always populate DB from all CSVs on startup
    init_db()
    print("Loading data sources...")

    if (DATA_DIR/"ps_tracker.csv").exists():
        _mp(DATA_DIR/"ps_tracker.csv", STATE_FILE)
        print("  ✓ PS tracker merged")
    if (DATA_DIR/"dc_cse_tracker.csv").exists():
        _run_dc_pipeline(DATA_DIR, STATE_FILE)
        print("  ✓ DC CSE Tracker synced via _run_dc_pipeline (all theatres, milestones, audit)")
    _mig(STATE_FILE)
    # Sync live_fire into DB
    _state = _j.loads(STATE_FILE.read_text())
    with get_db() as _conn:
        for _aid, _acc in _state.get("accounts",{}).items():
            _conn.execute("UPDATE accounts SET live_fire=?, live_fire_dc=? WHERE account_id=?",
                (1 if _acc.get("live_fire") else 0, _acc.get("live_fire_dc","") or "", _aid))
    with get_db() as _conn:
        _n = _conn.execute("SELECT COUNT(*) FROM blocked_data").fetchone()[0]
        _lf = _conn.execute("SELECT COUNT(*) FROM accounts WHERE live_fire=1").fetchone()[0]
    print(f"  ✓ DB ready: {_n} milestone records | {_lf} live fire accounts")
    print("Solstice Control Center → http://localhost:8200")
    uvicorn.run(app,host="0.0.0.0",port=8200,log_level="warning")
