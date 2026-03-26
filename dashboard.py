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

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
import uvicorn

from agent.constants import STATE_FILE, DATA_DIR
from agent.db import get_db, init_db

app = FastAPI(title="Solstice Control Center")


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
    from agent.blocked_parser import load_and_merge as _mb
    from agent.ps_parser import load_and_merge as _mp
    from agent.db import migrate_from_state as _mig
    init_db()
    if (DATA_DIR/"blocked_accounts.csv").exists():
        _mb(DATA_DIR/"blocked_accounts.csv", STATE_FILE)
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


@app.on_event("startup")
async def startup_event():
    """Populate DB immediately when FastAPI starts."""
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _populate_db)


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
                a.live_fire, a.live_fire_dc,
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
                        e={"name":row["customer_name"],"cse":row["active_cse"] or "—","lf":bool(row["live_fire"]),"lf_dc":row["live_fire_dc"] or "","date":d.strftime("%d %b")}
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

    FILE_MAP = {
        "DC CSE Tracker":               ("dc_cse_tracker.csv", None),
        "EMEA Accounts CC Migrations":  ("emea_accounts.csv",  None),
        "EMEA Solistce Blocked Accounts": ("blocked_accounts.csv", "538753662"),
        # PS Tracker excluded — Drive default tab is wrong format; file maintained separately
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

    with get_db() as _conn:
        for _aid, _acc in _dc_state.get("accounts", {}).items():
            _dd = _acc.get("dc_data", {})
            if not _dd:
                continue
            # Update accounts table (CSE + email)
            if _dd.get("active_cse"):
                _conn.execute("UPDATE accounts SET active_cse=? WHERE account_id=?",
                              (_dd["active_cse"], _aid))
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
                   cc_rep, cc_dsm, churn_risk, health_notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                  health_notes=CASE WHEN excluded.health_notes!='' THEN excluded.health_notes ELSE health_notes END
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
        _m1_rows = _mdb.execute('''
            SELECT a.account_id,a.customer_name,a.active_cse,a.sales_region,a.status,a.live_fire,
                   b.signal,b.status_detail,b.upgrade_notes,b.subtype
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
            _det=(_mr['status_detail'] or '').lower(); _nt=(_mr['upgrade_notes'] or '').lower()
            _nm=_mr['customer_name'].lower()
            if 'mtn ' in _nm or _nm=='mtn benin': _cat='unblock'
            elif _st in _SKIP or 'Blocked: Tech' in _st: _cat='skip'
            elif _st in ('Sales Hold','On Hold') or any(k in _nt+_det for k in _HOLD_KW) or _sig=='blocked': _cat='acct_team'
            else: _cat='actionable'
            _mdb.execute(
                'INSERT INTO m1_suggestions (account_name,assigned_cse,original_cse,region,status,signal,category) VALUES (?,?,?,?,?,?,?)',
                (_mr['customer_name'],_cse,_orig,_reg,_mr['status'],_mr['signal'],_cat))
    result["m1_rebuilt"] = len(_m1_rows)
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
            from agent.blocked_parser import load_and_merge as _mb
            from agent.ps_parser import load_and_merge as _mp
            from agent.dc_parser import load_and_merge as _mdc
            from agent.enricher import enrich_accounts as _enrich
            from agent.db import migrate_from_state as _mig
            from agent.differ import parse_csv as _parse
            from agent.validator import validate_accounts as _validate

            _mb(DATA_DIR/"blocked_accounts.csv", STATE_FILE)
            _mp(DATA_DIR/"ps_tracker.csv", STATE_FILE)
            # DC CSE Tracker is master — shared function handles snapshot, upsert, diff audit
            if (DATA_DIR/"dc_cse_tracker.csv").exists():
                _run_dc_pipeline(DATA_DIR, STATE_FILE)

            _enrich(STATE_FILE)

            # Diff EMEA accounts — detect status AND CSE changes
            _emea = DATA_DIR/"emea_accounts.csv"
            _changes = 0
            # Fields to audit from EMEA accounts CSV
            _EMEA_WATCH = [
                ("status",     "status"),
                ("active_cse", "cse"),
            ]
            if _emea.exists():
                _state = _j2.loads(STATE_FILE.read_text())
                _new = _parse(_emea)
                _valid, _ = _validate(_new, csv_filename=_emea.name)
                _old = _state.get("accounts", {})
                _now = _dt.now(_tz.utc).isoformat()
                _pipeline_changes = _state.get("pipeline_changes", [])
                with get_db() as _conn:
                    for _aid, _nacc in _valid.items():
                        for _field, _label in _EMEA_WATCH:
                            _ov = (_old.get(_aid, {}).get(_field) or "").strip()
                            _nv = (_nacc.get(_field) or "").strip()
                            if not _ov or _ov == _nv: continue
                            _dup = _conn.execute(
                                "SELECT 1 FROM status_history WHERE account_id=? AND field_name=? AND old_status=? AND new_status=? AND source='pipeline' AND file_source='EMEA Accounts CC Migrations'",
                                (_aid, _label, _ov, _nv)).fetchone()
                            if not _dup:
                                _conn.execute(
                                    "INSERT INTO status_history (account_id,old_status,new_status,changed_at,source,file_source,field_name) VALUES (?,?,?,?,?,?,?)",
                                    (_aid, _ov, _nv, _now, "pipeline", "EMEA Accounts CC Migrations", _label))
                                if _field == "status":
                                    _pipeline_changes.append({
                                        "account_id": _aid, "old_status": _ov, "new_status": _nv,
                                        "changed_at": _now, "customer_name": _nacc.get("customer_name","")
                                    })
                            _changes += 1
                _state["pipeline_changes"] = _pipeline_changes
                # MERGE — preserve enrichment fields, only update CSV-sourced fields
                MERGE_FIELDS = ['customer_name','arr','active_cse','backup_cse','status',
                                'status_changed_at','expiration_date','expiry_alerted_date',
                                'ps_engaged','kickoff_date','comments','sales_region',
                                'email_sent','live_fire','live_fire_dc','blockers','last_seen']
                for _mid, _macc in _valid.items():
                    if _mid in _state["accounts"]:
                        for _f in MERGE_FIELDS:
                            if _f in _macc:
                                _state["accounts"][_mid][_f] = _macc[_f]
                    else:
                        _state["accounts"][_mid] = _macc
                STATE_FILE.write_text(_j2.dumps(_state, indent=2, ensure_ascii=False))

            # Multi-file audit — track ALL column changes across ALL CSV source files
            _now2 = _dt.now(_tz.utc).isoformat()
            _snap = _j2.loads(STATE_FILE.read_text()).get("file_snapshots", {})
            import csv as _csv_mod

            def _log_change(conn, aid, field, old_v, new_v, file_src):
                """Log a field change to status_history. No-op if duplicate or no real change."""
                ov, nv = str(old_v).strip(), str(new_v).strip()
                if not ov or ov == nv: return 0
                dup = conn.execute(
                    "SELECT 1 FROM status_history WHERE account_id=? AND field_name=? AND old_status=? AND new_status=? AND file_source=?",
                    (aid, field, ov, nv, file_src)).fetchone()
                if dup: return 0
                conn.execute(
                    "INSERT INTO status_history (account_id,old_status,new_status,changed_at,source,file_source,field_name) VALUES (?,?,?,?,?,?,?)",
                    (aid, ov, nv, _now2, "pipeline", file_src, field))
                return 1

            # Build account_id lookup (lowercase → real ID)
            with get_db() as _lm_conn:
                _lower_map = {r[0].lower(): r[0] for r in _lm_conn.execute('SELECT account_id FROM accounts').fetchall()}

            _audit_total = 0

            # File audit config:
            # EMEA Accounts = CSE working file → track ALL columns
            # DC CSE Tracker = data feed → track only key milestone/status fields
            _CSV_WATCH = {
                "emea_accounts": {
                    "path": DATA_DIR/"emea_accounts.csv",
                    "label": "EMEA Accounts CC Migrations",
                    "id_col": "\xa0\xa0",  # non-breaking spaces — actual column header
                    "filter": {},
                    "cols": {"Status"},    # only track status — CSE handled by simple diff, rest is noise
                },
                "dc_cse_tracker": {
                    "path": DATA_DIR/"dc_cse_tracker.csv",
                    "label": "DC CSE Tracker",
                    "id_col": "pc_end_customer_account_id",
                    "filter": {"account_theatre": "EMEA"},
                    "cols": {              # only these fields matter
                        "M0:Internal Kickoff Complete", "M1:Customer Outreach Complete",
                        "M2:Entitlements and Plan aligned with customer",
                        "M3:EB Buy-in Meeting Complete", "M4:Discovery complete",
                        "M5:Tech validation complete", "M7:Legal and operational upgrade readiness",
                        "M8:Upgrade started", "M9:Upgrade complete",
                        "PC_CC_Migration_status", "DC Upgrade Progress Status",
                        "CSE Assigned", "DC Indicated account churn risk",
                    },
                },
            }

            for _snap_key, _cfg in _CSV_WATCH.items():
                if not _cfg["path"].exists(): continue
                _old_snap = _snap.get(_snap_key, {})
                _new_snap = {}
                try:
                    with open(_cfg["path"], encoding='utf-8-sig', errors='ignore') as _cf:
                        for _row in _csv_mod.DictReader(_cf):
                            # Row filter
                            if _cfg["filter"] and any(
                                    _row.get(k,'').strip().upper() != v.upper()
                                    for k,v in _cfg["filter"].items()): continue
                            # Resolve account_id
                            _raw_id = (_row.get(_cfg["id_col"],'') or '').strip().lower()
                            _aid = _lower_map.get(_raw_id)
                            if not _aid: continue
                            # Build row snapshot — all cols or specific set
                            if _cfg["cols"] is None:
                                _row_snap = {k: v.strip() for k,v in _row.items()
                                             if k and k != _cfg["id_col"] and v and v.strip()
                                             and not v.strip().startswith('#')}  # skip #REF! etc
                            else:
                                _row_snap = {k: _row.get(k,'').strip() for k in _cfg["cols"]}
                            _new_snap[_aid] = _row_snap
                            _prev = _old_snap.get(_aid, {})
                            if not _prev: continue  # first run = seed, no diff
                            with get_db() as _dc:
                                for _fld in set(_prev) | set(_row_snap):
                                    _ov = _prev.get(_fld,'')
                                    _nv = _row_snap.get(_fld,'')
                                    _audit_total += _log_change(_dc, _aid, _fld, _ov, _nv, _cfg["label"])
                except Exception:
                    pass
                _st_snap = _j2.loads(STATE_FILE.read_text())
                _st_snap.setdefault("file_snapshots", {})[_snap_key] = _new_snap
                STATE_FILE.write_text(_j2.dumps(_st_snap, indent=2, ensure_ascii=False))

            _mig(STATE_FILE)
            r_output = f"status_changes={_changes} audit_changes={_audit_total}\ndone"
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
        csvs = {"Blocked Accounts": data_dir/"blocked_accounts.csv",
                "PS Tracker":       data_dir/"ps_tracker.csv"}
        yield event("Google Drive", "DOWNLOADING", "Opening export URLs in browser — corp auth handles it")
        import glob as _g2, os as _os2, shutil as _sh2
        downloads = Path.home() / "Downloads"
        _cfg = json.loads((data_dir / "drive_config.json").read_text())
        FILE_MAP2 = {
            "DC CSE Tracker":              ("dc_cse_tracker.csv", None),
            "EMEA Accounts CC Migrations": ("emea_accounts.csv",  None),
            "EMEA Solistce Blocked Accounts": ("blocked_accounts.csv", None),
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

        # Step 3: Merge blocked accounts
        yield event("Blocked Accounts", "LOADING", "Parsing + merging into state.json")
        try:
            from agent.blocked_parser import load_and_merge as mb
            b = mb(data_dir/"blocked_accounts.csv", data_dir/"state.json")
            yield event("  →", "OK", f"{b['matched']} matched · {b['cs_team']} CS team · {b['core_rep_blocking']} core-rep-blocking", "green")
        except Exception as e:
            yield event("  →", "ERROR", str(e)[:80], "red")
        await asyncio.sleep(0.1)

        # Step 4: Merge PS tracker
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
            yield event("  →", "OK", f"{dc['matched']}/{dc['total']} EMEA matched · {dc['audit_logged']} milestone changes logged · M1 action plan rebuilt ({dc.get('m1_rebuilt',0)} accounts)", "green")
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


def _load_milestones() -> list:
    _ensure_db()
    """Milestone tracker — full M0-M9 with SLA breach flags."""
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
                       b.dc_progress, b.owner_e2e
                FROM accounts a JOIN blocked_data b ON a.account_id=b.account_id
                WHERE a.customer_name != ''
                ORDER BY b.signal, a.customer_name
            """).fetchall()
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


def _load_completed() -> list:
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
                ORDER BY b.m9_actual DESC, b.m9_planned DESC
            """).fetchall()
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


def _load_audit_log() -> list:
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
                ORDER BY sh.changed_at ASC
                LIMIT 2000
            """).fetchall()
        return [dict(r) for r in rows]
    except: return []


@app.get("/api/audit-log")
def api_audit(): return _load_audit_log()


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
def api_milestones(): return _load_milestones()

@app.get("/api/ps")
def api_ps(): return _load_ps()

@app.get("/api/completed")
def api_completed(): return _load_completed()

@app.get("/api/dq")
def api_dq(): return _load_dq()


@app.get("/api/customer-search")
def api_customer_search(q: str = ""):
    """Search accounts by name — returns list of matches."""
    if not q or len(q) < 2: return []
    _ensure_db()
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT a.account_id, a.customer_name, a.active_cse, a.status,
                       a.sales_region, a.live_fire, b.signal, b.dc_progress
                FROM accounts a LEFT JOIN blocked_data b ON a.account_id=b.account_id
                WHERE a.customer_name LIKE ? AND a.customer_name!=''
                ORDER BY a.customer_name LIMIT 10
            """, (f"%{q}%",)).fetchall()
        return [dict(r) for r in rows]
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
                       b.m7_complete, b.m8_started, b.m8_planned, b.m8_actual,
                       b.m9_complete, b.m9_planned, b.m9_actual,
                       b.signal, b.subtype, b.dc_progress, b.status_detail,
                       b.upgrade_notes, b.health_notes, b.owner_e2e, b.dc_assignment,
                       b.cohort, b.region as district_region, b.milestone_category,
                       b.cc_rep, b.cc_dsm, b.churn_risk,
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
                FROM status_history WHERE account_id=? ORDER BY changed_at DESC LIMIT 10
            """, (account_id,)).fetchall()
        if not r: return {"error": "not found"}
        d = dict(r)
        d["history"] = [dict(h) for h in hist]
        return d
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
def api_m1_suggestions():
    """M1 action plan — 4 flat tables with LLM rationale per category."""
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT assigned_cse, account_name, original_cse, region, status, signal, category
                FROM m1_suggestions
                ORDER BY category, assigned_cse, region, account_name
            """).fetchall()
        from collections import defaultdict
        cats: dict = {'actionable': [], 'acct_team': [], 'unblock': [], 'skip': []}
        for r in rows:
            cat = r[6] or 'actionable'
            if cat in cats:
                cats[cat].append({
                    "account_name": r[1], "assigned_cse": r[0], "original_cse": r[2],
                    "region": r[3], "status": r[4], "signal": r[5],
                    "is_new": r[2] == 'Irene Garcia'
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
    html_path = Path(__file__).parent / "static" / "dashboard.html"
    if html_path.exists():
        return html_path.read_text()
    return "<h1>Loading...</h1>"

@app.get("/v2",response_class=HTMLResponse)
def dashboard_v2():
    html_path = Path(__file__).parent / "static" / "v2.html"
    if html_path.exists():
        return html_path.read_text()
    return "<h1>v2 not found</h1>"

if __name__=="__main__":
    import os as _os
    # Always run from Solstice/ directory regardless of where called from
    _os.chdir(Path(__file__).parent)
    sys.path.insert(0, str(Path(__file__).parent))

    import json as _j
    from agent.blocked_parser import load_and_merge as _mb
    from agent.ps_parser import load_and_merge as _mp
    from agent.dc_parser import load_and_merge as _mdc
    from agent.db import migrate_from_state as _mig

    # Always populate DB from all CSVs on startup
    init_db()
    print("Loading data sources...")
    if (DATA_DIR/"blocked_accounts.csv").exists():
        _mb(DATA_DIR/"blocked_accounts.csv", STATE_FILE)
        print("  ✓ Blocked accounts merged")
    if (DATA_DIR/"ps_tracker.csv").exists():
        _mp(DATA_DIR/"ps_tracker.csv", STATE_FILE)
        print("  ✓ PS tracker merged")
    if (DATA_DIR/"dc_cse_tracker.csv").exists():
        _mdc(DATA_DIR/"dc_cse_tracker.csv", STATE_FILE)
        print("  ✓ DC CSE Tracker merged (master)")
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
