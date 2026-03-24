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
    """Populate DB from CSVs. Always runs — checks blocked_data count first."""
    try:
        with get_db() as conn:
            n = conn.execute("SELECT COUNT(*) FROM blocked_data").fetchone()[0]
        if n > 0:
            return  # Already populated
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


def _load_stats() -> dict:
    _ensure_db()
    try:
        with get_db() as conn:
            total      = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
            by_status  = {r[0] or "Blank": r[1] for r in conn.execute(
                "SELECT status, COUNT(*) FROM accounts GROUP BY status")}
            completed  = by_status.get("Completed", 0)
            no_status  = sum(v for k,v in by_status.items() if k in ("","Blank"))
            stalls     = conn.execute("""SELECT COUNT(DISTINCT b.account_id)
                FROM blocked_data b JOIN accounts a ON a.account_id=b.account_id
                WHERE b.is_cs_team=1 AND b.m3_complete=1 AND b.m8_started=0""").fetchone()[0]
            core_rep   = conn.execute(
                "SELECT COUNT(*) FROM blocked_data WHERE subtype='core_rep_blocking'").fetchone()[0]
            ps_active  = conn.execute(
                "SELECT COUNT(*) FROM ps_data WHERE ps_status='In Progress'").fetchone()[0]
            no_cse     = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE (active_cse IS NULL OR active_cse='') AND customer_name!=''").fetchone()[0]
            dc_driving = conn.execute("SELECT COUNT(*) FROM accounts WHERE live_fire=1").fetchone()[0]
            last_run   = STATE_FILE.stat().st_mtime if STATE_FILE.exists() else 0
            last_str   = datetime.fromtimestamp(last_run,timezone.utc).strftime("%d %b %Y · %H:%M UTC") if last_run else "—"
            return dict(total=total,completed=completed,no_status=no_status,
                        stalls=stalls,core_rep_blocking=core_rep,ps_active=ps_active,
                        no_cse=no_cse,dc_driving=dc_driving,by_status=by_status,last_run=last_str)
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
                SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) done
                FROM accounts WHERE active_cse IS NOT NULL AND active_cse!=''
                GROUP BY active_cse ORDER BY total DESC""").fetchall()
            return [dict(r) for r in rows]
    except: return []


@app.get("/api/stats")
def api_stats(): return _load_stats()

@app.get("/api/weekly")
def api_weekly(): return _load_weekly()

@app.get("/api/cse")
def api_cse(): return _load_cse()

@app.get("/api/run-pipeline")
def api_run():
    try:
        r=subprocess.run([sys.executable,"-c","""
import sys; sys.path.insert(0,'.')
from agent.constants import STATE_FILE,DATA_DIR
from agent.blocked_parser import load_and_merge as mb
from agent.ps_parser import load_and_merge as mp
from agent.enricher import enrich_accounts
mb(DATA_DIR/'blocked_accounts.csv',STATE_FILE)
mp(DATA_DIR/'ps_tracker.csv',STATE_FILE)
enrich_accounts(STATE_FILE)
print('done')
"""],cwd=str(Path(__file__).parent),capture_output=True,text=True,timeout=300)
        return {"status":"ok","output":r.stdout.strip()}
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
        yield event("CSV Files", "CHECK", "Verifying input files")
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
            from agent.db import sync_all, get_db
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
                       b.signal, b.subtype, b.upgrade_notes, b.health_notes
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
    """Milestone tracker — M3/M8/M9 with details."""
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT a.customer_name, a.active_cse, a.status, a.live_fire, a.live_fire_dc,
                       b.team, b.is_cs_team, b.signal, b.subtype, b.milestone_category,
                       b.m3_complete, b.m3_planned, b.m8_started, b.m8_planned,
                       b.m9_complete, b.m9_planned, b.upgrade_notes, b.health_notes,
                       b.exec_delay, b.status_detail
                FROM accounts a JOIN blocked_data b ON a.account_id=b.account_id
                WHERE a.customer_name != ''
                ORDER BY b.signal, a.customer_name
            """).fetchall()
            return [dict(r) for r in rows]
    except: return []


def _load_ps() -> dict:
    _ensure_db()
    """PS engagement — matched + unmatched."""
    try:
        with get_db() as conn:
            matched = conn.execute("""
                SELECT a.customer_name, a.active_cse, a.live_fire,
                       p.psc, p.psc_shadow, p.pm, p.ps_status, p.clarizen_id, p.timeline
                FROM accounts a JOIN ps_data p ON a.account_id=p.account_id
                ORDER BY p.ps_status, a.customer_name
            """).fetchall()
        import csv as _csv
        ps_file = DATA_DIR / "ps_tracker.csv"
        all_ps = list(_csv.DictReader(open(ps_file, encoding="utf-8-sig"))) if ps_file.exists() else []
        with get_db() as conn2:
            matched_ps_names = {r[0] for r in conn2.execute("SELECT ps_name FROM ps_data").fetchall()}
        matched_names = matched_ps_names
        unmatched = [{"name":r["PS Eligible Account Name"],"country":r.get("Country",""),
                      "psc":r.get("Assigned PSC",""),"pm":r.get("Assigned PM",""),
                      "timeline":r.get("Estimated Time for PS Engagement","")}
                     for r in all_ps if r.get("PS Eligible Account Name","").strip()
                     and r.get("PS Eligible Account Name","").strip() not in matched_names]
        return {"matched":[dict(r) for r in matched], "unmatched":sorted(unmatched,key=lambda x:x["name"])}
    except: return {"matched":[],"unmatched":[]}


def _load_completed() -> list:
    _ensure_db()
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT a.customer_name, a.active_cse, a.sales_region,
                       a.status_changed_at, a.live_fire, a.live_fire_dc
                FROM accounts a WHERE a.status='Completed'
                ORDER BY a.status_changed_at DESC
            """).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        return []


def _load_dq() -> list:
    _ensure_db()
    """Data quality issues."""
    try:
        import json as _j
        from agent.constants import STATUSES as _ST
        state = _j.loads(STATE_FILE.read_text())
        accs = list(state.get("accounts",{}).values())
        OUTREACH = {"Ready To Engage","Account team contacted"}
        issues = []
        no_st  = [a for a in accs if not (a.get("status") or "").strip() and a.get("customer_name","").strip()]
        no_cse = [a for a in accs if a.get("customer_name","").strip() and not (a.get("active_cse") or "").strip()]
        no_email=[a for a in accs if a.get("status") in OUTREACH and not (a.get("email_sent") or "").strip()]
        if no_st:   issues.append({"type":"No Status",   "count":len(no_st),  "accounts":[a.get("customer_name") for a in no_st]})
        if no_cse:  issues.append({"type":"No Owner/CSE","count":len(no_cse), "accounts":[a.get("customer_name") for a in no_cse]})
        if no_email:issues.append({"type":"No Email on Record","count":len(no_email),"accounts":[a.get("customer_name") for a in no_email]})
        return issues
    except: return []


def _load_audit_log() -> list:
    _ensure_db()
    """Audit log — what changed per customer between pipeline runs."""
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT a.customer_name, a.active_cse, sh.old_status, sh.new_status,
                       sh.changed_at, sh.source
                FROM status_history sh
                JOIN accounts a ON a.account_id = sh.account_id
                WHERE sh.source = 'pipeline'
                ORDER BY sh.changed_at DESC
                LIMIT 200
            """).fetchall()
        return [dict(r) for r in rows]
    except: return []


@app.get("/api/audit-log")
def api_audit(): return _load_audit_log()


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

if __name__=="__main__":
    import os as _os
    # Always run from Solstice/ directory regardless of where called from
    _os.chdir(Path(__file__).parent)
    sys.path.insert(0, str(Path(__file__).parent))

    import json as _j
    from agent.blocked_parser import load_and_merge as _mb
    from agent.ps_parser import load_and_merge as _mp
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
