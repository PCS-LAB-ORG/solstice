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


def _load_stats() -> dict:
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
            stale      = conn.execute("""SELECT COUNT(*) FROM accounts a
                JOIN blocked_data b ON a.account_id=b.account_id
                WHERE a.status IN ('Ready To Engage','Account team contacted') AND b.signal='green'""").fetchone()[0]
            last_run   = STATE_FILE.stat().st_mtime if STATE_FILE.exists() else 0
            last_str   = datetime.fromtimestamp(last_run,timezone.utc).strftime("%d %b %Y · %H:%M UTC") if last_run else "—"
            return dict(total=total,completed=completed,no_status=no_status,
                        stalls=stalls,core_rep_blocking=core_rep,ps_active=ps_active,
                        no_cse=no_cse,stale_tracker=stale,by_status=by_status,last_run=last_str)
    except Exception as e:
        return {"error": str(e)}


def _load_weekly() -> list:
    try:
        today  = date.today()
        weeks  = {}
        with get_db() as conn:
            for row in conn.execute("""SELECT a.customer_name,a.active_cse,a.status,
                b.m8_planned,b.m9_planned,b.m8_started,b.m9_complete
                FROM accounts a JOIN blocked_data b ON a.account_id=b.account_id
                WHERE b.m8_planned!='' OR b.m9_planned!=''"""):
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
                        weeks.setdefault(k,{"key":k,"label":f"W{d.strftime('%U')} · {ws.strftime('%d %b')}","m8":[],"m9":[],"done":[]})
                        e={"name":row["customer_name"],"cse":row["active_cse"] or "—"}
                        if label=="M8" and not done: weeks[k]["m8"].append(e)
                        elif label=="M9" and not done: weeks[k]["m9"].append(e)
                        elif label=="M9" and done: weeks[k]["done"].append(e)
                    except: pass
        tw=today.strftime("%Y-W%U")
        sw=sorted(weeks.values(),key=lambda x:x["key"])
        idx=next((i for i,w in enumerate(sw) if w["key"]>=tw),0)
        return sw[max(0,idx-3):idx+6]
    except: return []


def _load_cse() -> list:
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
    init_db()
    print("Solstice Control Center → http://localhost:8200")
    uvicorn.run(app,host="0.0.0.0",port=8200,log_level="warning")
