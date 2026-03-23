"""
reporter.py — Generate a light HTML report with three sections:
  1. Approved Tasks (from pending_tasks.csv)
  2. What To Do Next (problematic statuses from state.json)
  3. Completed (accounts that reached Completed, with date)

Callable from pipeline (generate_report()) or standalone (python3 agent/reporter.py).
"""
from __future__ import annotations
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.constants import PENDING_TASKS_FILE, STATE_FILE, SALESFORCE_ID_PATTERN

OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"

CATEGORY_COLORS: dict[str, tuple[str, str]] = {
    "SENTIMENT_RISK":        ("#9C1C1C", "#FFF0F0"),
    "DELIVERY_IMPACT":       ("#BF5000", "#FFF4EC"),
    "DEPLOYMENT_IMPACT":     ("#C62828", "#FEF2F2"),
    "TECHNICAL_STABILITY":   ("#5D4037", "#F4EFEC"),
    "RELATIONSHIP_RECOVERY": ("#4527A0", "#F0EBFF"),
    "AUDIT_COMPLIANCE":      ("#1055A8", "#EAF2FF"),
    "PROJECT_CLOSURE":       ("#00695C", "#E4F5F3"),
    "UNCLASSIFIED":          ("#555555", "#F2F2F2"),
}

PRIORITY_COLOR: dict[str, str] = {
    "HIGH":   "#C62828",
    "MEDIUM": "#D97706",
    "LOW":    "#2E7D32",
}

# Problematic status groups — what needs action
STATUS_GROUPS = {
    "Ready To Engage": {
        "statuses": ["Ready To Engage"],
        "color": "#065F46",
        "bg": "#ECFDF5",
        "dot": "#10B981",
        "desc": "Not yet contacted — start outreach now",
    },
    "Account Team Contacted": {
        "statuses": ["Account team contacted"],
        "color": "#B45309",
        "bg": "#FFFBEB",
        "dot": "#F59E0B",
        "desc": "Initial contact made — chase for response",
    },
    "Churning / Sales Hold": {
        "statuses": ["Churning/Churned", "Sales Hold"],
        "color": "#7F1D1D",
        "bg": "#FEF2F2",
        "dot": "#DC2626",
        "desc": "Critical — account churning or frozen by sales",
    },
    "Escalation Risk": {
        "statuses": ["Backoff", "Cancelled"],
        "color": "#991B1B",
        "bg": "#FFF5F5",
        "dot": "#EF4444",
        "desc": "Account backed off or cancelled — immediate attention required",
    },
    "Blocked": {
        "statuses": ["Blocked: Tech limitation"],
        "color": "#5D4037",
        "bg": "#F9F5F3",
        "dot": "#A1887F",
        "desc": "Technical blocker preventing migration progress",
    },
    "On Hold": {
        "statuses": ["On Hold"],
        "color": "#1E40AF",
        "bg": "#EFF6FF",
        "dot": "#93C5FD",
        "desc": "Parked — awaiting customer or internal action",
    },
    "Active Migration": {
        "statuses": ["In Progress", "Customer Engaged", "Kick Off Scheduled",
                     "Customer Acceptance", "PS", "Upgrade Email Sent", "Dev testing"],
        "color": "#065F46",
        "bg": "#F0FDF4",
        "dot": "#4ADE80",
        "desc": "Migration actively underway — monitor for blockers",
    },
    "No Status": {
        "statuses": ["", "Blank"],
        "color": "#6B7280",
        "bg": "#F9FAFB",
        "dot": "#D1D5DB",
        "desc": "Missing status — data quality issue, update the sheet",
    },
}


def _load_tasks(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        return []
    tasks = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if SALESFORCE_ID_PATTERN.match(row.get("account_id", "")):
                tasks.append(row)
    return tasks


def _load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8")).get("accounts", {})
    except Exception:
        return {}


def _fmt_dt(iso: str, date_only: bool = False) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y") if date_only else dt.strftime("%d %b %Y · %H:%M UTC")
    except Exception:
        return iso or "—"


def _days_ago(iso: str) -> str:
    """Return 'X days ago' from an ISO or DD/MM/YYYY HH:MM:SS timestamp."""
    if not iso:
        return "—"
    dt = None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(iso.strip(), fmt).replace(tzinfo=timezone.utc)
            break
        except ValueError:
            pass
    if dt is None:
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except Exception:
            return "—"
    days = (datetime.now(timezone.utc) - dt).days
    if days == 0:
        return "today"
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


def _badge(cat: str) -> str:
    fg, bg = CATEGORY_COLORS.get(cat, ("#555", "#F2F2F2"))
    return (
        f'<span class="badge" style="color:{fg};background:{bg};border-color:{fg}44">'
        f'{cat.replace("_", " ")}</span>'
    )


def _priority(pri: str) -> str:
    c = PRIORITY_COLOR.get(pri, "#555")
    return (
        f'<span class="pri-dot" style="background:{c}"></span>'
        f'<span class="pri-txt" style="color:{c}">{pri}</span>'
    )


def _stat(label: str, count: int, color: str) -> str:
    return (
        f'<div class="stat">'
        f'<span class="stat-n" style="color:{color}">{count}</span>'
        f'<span class="stat-l">{label}</span>'
        f'</div>'
    )


def _section_header(title: str, subtitle: str, count: int) -> str:
    return f"""
    <div class="sec-hdr">
      <div>
        <h2 class="sec-title">{title}</h2>
        <div class="sec-sub">{subtitle}</div>
      </div>
      <div class="sec-count">{count}</div>
    </div>"""


def _task_cards(tasks: list[dict]) -> str:
    if not tasks:
        return '<div class="empty">No approved tasks yet. Drop a CSV into data/inbox/ to begin.</div>'

    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    sorted_tasks = sorted(tasks, key=lambda t: priority_order.get(t.get("priority", "LOW"), 9))
    cards = ""
    for t in sorted_tasks:
        cat    = t.get("category", "UNCLASSIFIED")
        pri    = t.get("priority", "LOW")
        border = PRIORITY_COLOR.get(pri, "#999")
        name   = t.get("customer_name") or t.get("account_id", "—")
        acc_id = t.get("account_id", "")
        region = t.get("region") or "—"
        cse    = t.get("cse") or "—"
        action = t.get("suggested_action", "")
        old_v  = t.get("old_value", "")
        new_v  = t.get("new_value", "")
        ts     = _fmt_dt(t.get("detected_at", ""))

        change_html = ""
        if old_v or new_v:
            change_html = (
                f'<div class="change">'
                f'<span class="chg-lbl">Change</span>'
                f'<span class="chg-val">{old_v or "—"} → {new_v or "—"}</span>'
                f'</div>'
            )

        cards += f"""
        <div class="card" style="border-left-color:{border}">
          <div class="card-top">
            {_badge(cat)}
            <div class="pri-wrap">{_priority(pri)}</div>
          </div>
          <div class="card-name">{name}</div>
          <div class="card-id">{acc_id}</div>
          <div class="card-meta">{region} · {cse}</div>
          <div class="card-action">{action}</div>
          {change_html}
          <div class="card-ts">{ts}</div>
        </div>"""
    return cards


def _action_section(accounts: dict) -> str:
    """Build the What To Do Next section from state accounts."""
    html = ""
    total_action = 0

    for group_name, cfg in STATUS_GROUPS.items():
        rows = [
            (acc_id, acc)
            for acc_id, acc in accounts.items()
            if (acc.get("status") or "") in cfg["statuses"]
            and acc.get("customer_name", "").strip()
        ]
        if not rows:
            continue

        total_action += len(rows)
        rows_sorted = sorted(rows, key=lambda x: x[1].get("customer_name", ""))

        is_outreach = group_name in ("Ready To Engage", "Account Team Contacted")
        is_blocked  = group_name == "Blocked"
        rows_html = ""
        for acc_id, acc in rows_sorted:
            status   = acc.get("status", "—")
            name     = acc.get("customer_name", "—")
            region   = acc.get("sales_region") or "—"
            cse      = acc.get("active_cse") or "—"
            changed  = _fmt_dt(acc.get("status_changed_at", ""), date_only=True)
            blockers = acc.get("blockers") or []

            contact_iso = acc.get("email_sent", "") or acc.get("status_changed_at", "")
            last_col = _days_ago(contact_iso) if is_outreach else changed
            last_col_html = last_col
            if is_outreach:
                try:
                    days = int(last_col.split()[0]) if "day" in last_col else 0
                    color = "#C62828" if days > 14 else ("#D97706" if days > 7 else "#2E7D32")
                    last_col_html = f'<span style="color:{color};font-weight:600">{last_col}</span>'
                except Exception:
                    pass

            # Blockers tags — shown for all groups when present
            blocker_html = ""
            if blockers:
                tags = "".join(
                    f'<span class="blocker-tag">{b.replace(" (blocker)", "").strip()}</span>'
                    for b in blockers
                )
                blocker_html = f'<div class="blocker-tags">{tags}</div>'

            if is_outreach:
                raw_comments = (acc.get("comments") or "").replace("\r\n", " ").replace("\n", " ").strip()
                if raw_comments:
                    notes_html = f'<span class="notes-text">{raw_comments[:180]}{"…" if len(raw_comments) > 180 else ""}</span>'
                else:
                    notes_html = '<span class="notes-none">No data available</span>'
                rows_html += f"""
                <tr>
                  <td class="tbl-name">{name}{blocker_html}</td>
                  <td><span class="status-chip" style="color:{cfg['color']};background:{cfg['bg']};border-color:{cfg['dot']}55">{status}</span></td>
                  <td class="tbl-region">{region}</td>
                  <td class="tbl-cse">{cse}</td>
                  <td class="tbl-date">{last_col_html}</td>
                  <td class="tbl-notes">{notes_html}</td>
                </tr>"""
            elif is_blocked:
                rows_html += f"""
                <tr>
                  <td class="tbl-name">{name}</td>
                  <td class="tbl-region">{region}</td>
                  <td class="tbl-cse">{cse}</td>
                  <td class="tbl-date">{changed}</td>
                  <td class="tbl-notes">{blocker_html if blocker_html else '<span class="notes-none">No blockers recorded</span>'}</td>
                </tr>"""
            else:
                rows_html += f"""
                <tr>
                  <td class="tbl-name">{name}{blocker_html}</td>
                  <td><span class="status-chip" style="color:{cfg['color']};background:{cfg['bg']};border-color:{cfg['dot']}55">{status}</span></td>
                  <td class="tbl-region">{region}</td>
                  <td class="tbl-cse">{cse}</td>
                  <td class="tbl-date">{last_col_html}</td>
                </tr>"""

        last_col_header  = "Last Contact" if is_outreach else "Since"
        notes_header     = "<th>Notes / Next Steps</th>" if is_outreach else ""
        blocked_headers  = "<th>Region</th><th>CSE</th><th>Since</th><th>Blockers</th>" if is_blocked else f"<th>Status</th><th>Region</th><th>CSE</th><th>{last_col_header}</th>{notes_header}"
        group_id = "group-" + group_name.lower().replace(" / ", "-").replace(" ", "-").replace("/", "-")
        html += f"""
        <div class="action-group" id="{group_id}">
          <div class="action-group-hdr" style="border-left-color:{cfg['dot']}">
            <span class="ag-dot" style="background:{cfg['dot']}"></span>
            <span class="ag-name" style="color:{cfg['color']}">{group_name}</span>
            <span class="ag-count">{len(rows)}</span>
            <span class="ag-desc">{cfg['desc']}</span>
          </div>
          <div class="tbl-wrap">
            <table class="acct-tbl">
              <thead><tr>
                <th>Customer</th>{blocked_headers}
              </tr></thead>
              <tbody>{rows_html}</tbody>
            </table>
          </div>
        </div>"""

    return html, total_action


def _completed_section(accounts: dict) -> str:
    """Build the Completed accounts table."""
    completed = [
        (acc_id, acc) for acc_id, acc in accounts.items()
        if acc.get("status") == "Completed"
    ]
    if not completed:
        return '<div class="empty-sm">No completed accounts yet.</div>', 0

    completed_sorted = sorted(
        completed,
        key=lambda x: x[1].get("status_changed_at", ""),
        reverse=True,
    )

    rows_html = ""
    for acc_id, acc in completed_sorted:
        name    = acc.get("customer_name", "—")
        region  = acc.get("sales_region") or "—"
        cse     = acc.get("active_cse") or "—"
        date    = _fmt_dt(acc.get("status_changed_at", ""), date_only=True)
        rows_html += f"""
        <tr>
          <td class="tbl-name">{name}</td>
          <td class="tbl-region">{region}</td>
          <td class="tbl-cse">{cse}</td>
          <td><span class="done-chip">✓ {date}</span></td>
        </tr>"""

    return f"""
    <div class="tbl-wrap">
      <table class="acct-tbl">
        <thead><tr>
          <th>Customer</th><th>Region</th><th>CSE</th><th>Completed</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>""", len(completed)


def _status_chart(accounts: dict) -> str:
    """Build a donut chart + table showing status distribution across all accounts."""
    from collections import Counter
    counts = Counter(acc.get("status") or "Blank" for acc in accounts.values())
    ordered = sorted(counts.items(), key=lambda x: -x[1])
    total = sum(counts.values())

    # Colour palette per status
    STATUS_COLORS = {
        "Account team contacted": "#F59E0B",
        "Ready To Engage":        "#10B981",
        "Sales Hold":             "#EF4444",
        "Churning/Churned":       "#DC2626",
        "Blocked: Tech limitation": "#A1887F",
        "In Progress":            "#6366F1",
        "Customer Engaged":       "#3B82F6",
        "Kick Off Scheduled":     "#8B5CF6",
        "On Hold":                "#93C5FD",
        "PS":                     "#06B6D4",
        "Customer Acceptance":    "#14B8A6",
        "Completed":              "#22C55E",
        "Cancelled":              "#F87171",
        "Backoff":                "#FB923C",
        "Upgrade Email Sent":     "#FBBF24",
        "Dev testing":            "#A3E635",
        "Blank":                  "#D1D5DB",
    }
    default_colors = ["#94A3B8","#CBD5E1","#E2E8F0"]

    labels = [s for s, _ in ordered]
    values = [n for _, n in ordered]
    colors = [STATUS_COLORS.get(s, default_colors[i % 3]) for i, s in enumerate(labels)]

    labels_js  = json.dumps(labels)
    values_js  = json.dumps(values)
    colors_js  = json.dumps(colors)

    # Status → section anchor mapping
    STATUS_ANCHOR = {
        "Ready To Engage":        "group-ready-to-engage",
        "Account team contacted":  "group-account-team-contacted",
        "Sales Hold":              "group-churning-sales-hold",
        "Churning/Churned":        "group-churning-sales-hold",
        "Backoff":                 "group-escalation-risk",
        "Cancelled":               "group-escalation-risk",
        "Blocked: Tech limitation":"group-blocked",
        "On Hold":                 "group-on-hold",
        "In Progress":             "group-active-migration",
        "Customer Engaged":        "group-active-migration",
        "Kick Off Scheduled":      "group-active-migration",
        "Customer Acceptance":     "group-active-migration",
        "PS":                      "group-active-migration",
        "Upgrade Email Sent":      "group-active-migration",
        "Dev testing":             "group-active-migration",
        "Blank":                   "group-no-status",
        "":                        "group-no-status",
        "Completed":               "section-completed",
    }
    anchors_js = json.dumps({s: STATUS_ANCHOR.get(s, "") for s, _ in ordered})

    # Table rows — clickable when anchor exists
    table_rows = ""
    for i, (status, count) in enumerate(ordered):
        pct = round(count / total * 100, 1)
        color = colors[i]
        anchor = STATUS_ANCHOR.get(status, "")
        if anchor:
            row_attrs = f'class="chart-row-link" onclick="jumpTo(\'{anchor}\')" title="Jump to {status} section"'
        else:
            row_attrs = 'class="chart-row-plain"'
        arrow = ' <span class="chart-arrow">↓</span>' if anchor else ""
        table_rows += f"""
        <tr {row_attrs}>
          <td><span class="chart-dot" style="background:{color}"></span>{status}{arrow}</td>
          <td class="chart-count">{count}</td>
          <td class="chart-pct">{pct}%</td>
        </tr>"""

    return f"""
    <div class="chart-wrap">
      <div class="chart-canvas-wrap">
        <canvas id="statusChart" width="280" height="280" style="cursor:pointer"></canvas>
        <div class="chart-centre">
          <div class="chart-centre-n">{total}</div>
          <div class="chart-centre-l">accounts</div>
        </div>
      </div>
      <div class="chart-table-wrap">
        <table class="chart-tbl">
          <thead><tr><th>Status</th><th>Count</th><th>%</th></tr></thead>
          <tbody>{table_rows}</tbody>
        </table>
      </div>
    </div>
    <script>
    var STATUS_ANCHORS = {anchors_js};

    function jumpTo(id) {{
      var el = document.getElementById(id);
      if (el) {{ el.scrollIntoView({{ behavior: 'smooth', block: 'start' }}); }}
    }}

    (function() {{
      var ctx = document.getElementById('statusChart').getContext('2d');
      var chart = new Chart(ctx, {{
        type: 'doughnut',
        data: {{
          labels: {labels_js},
          datasets: [{{ data: {values_js}, backgroundColor: {colors_js}, borderWidth: 2, borderColor: '#F7F5F1', hoverOffset: 8 }}]
        }},
        options: {{
          cutout: '68%',
          plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{
            label: function(c) {{
              var anchor = STATUS_ANCHORS[c.label];
              var suffix = anchor ? ' →' : '';
              return ' ' + c.label + ': ' + c.raw + ' (' + Math.round(c.raw/{total}*1000)/10 + '%)' + suffix;
            }}
          }} }} }},
          animation: {{ animateRotate: true, duration: 800 }},
          onClick: function(evt, elements) {{
            if (!elements.length) return;
            var label = chart.data.labels[elements[0].index];
            var anchor = STATUS_ANCHORS[label];
            if (anchor) jumpTo(anchor);
          }}
        }}
      }});
    }})();
    </script>"""


def _render(tasks: list[dict], accounts: dict, generated_at: str) -> str:
    total_tasks = len(tasks)

    by_cat: dict[str, int] = {}
    by_pri: dict[str, int] = {}
    for t in tasks:
        c = t.get("category", "UNCLASSIFIED")
        p = t.get("priority", "LOW")
        by_cat[c] = by_cat.get(c, 0) + 1
        by_pri[p] = by_pri.get(p, 0) + 1

    cat_stats = "".join(
        _stat(c.replace("_", " "), n, CATEGORY_COLORS.get(c, ("#555", "#F2F2F2"))[0])
        for c, n in sorted(by_cat.items(), key=lambda x: -x[1])
    )
    pri_stats = "".join([
        _stat("HIGH",   by_pri.get("HIGH", 0),   PRIORITY_COLOR["HIGH"]),
        _stat("MEDIUM", by_pri.get("MEDIUM", 0), PRIORITY_COLOR["MEDIUM"]),
        _stat("LOW",    by_pri.get("LOW", 0),     PRIORITY_COLOR["LOW"]),
    ])

    task_cards        = _task_cards(tasks)
    action_html, n_action = _action_section(accounts)
    completed_html, n_completed = _completed_section(accounts)
    status_chart      = _status_chart(accounts)

    # No-status alert banner
    no_status_accounts = [
        acc for acc in accounts.values()
        if not (acc.get("status") or "").strip()
        and acc.get("customer_name", "").strip()
    ]
    no_status_items = "".join(
        f'<div class="alert-item">'
        f'<span class="alert-acct">{acc.get("customer_name","—")}</span>'
        f'<span class="alert-owner">'
        + (acc.get("active_cse") or '<span class="alert-no-owner">⚠ NO OWNER</span>')
        + f'</span></div>'
        for acc in sorted(no_status_accounts, key=lambda a: a.get("customer_name",""))
    )
    no_status_banner = f"""
    <div class="alert-banner" id="alert-banner">
      <div class="alert-left">
        <span class="alert-icon">!</span>
        <div>
          <div class="alert-title">
            {len(no_status_accounts)} account{'s' if len(no_status_accounts) != 1 else ''} missing status — chase the owners to update the tracker
          </div>
          <div class="alert-body">{no_status_items}</div>
        </div>
      </div>
    </div>""" if no_status_accounts else ""
    total_accounts    = len(accounts)

    # Open Graph summary for Slack unfurling
    og_title       = f"Solstice EMEA Migration Report — {generated_at}"
    og_description = (
        f"{total_accounts} accounts tracked | "
        f"{n_action} need action | "
        f"{n_completed} completed | "
        f"{total_tasks} tasks approved this session"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Solstice EMEA — Report</title>

<!-- Open Graph meta tags for Slack link unfurling -->
<meta property="og:type"        content="website">
<meta property="og:title"       content="{og_title}">
<meta property="og:description" content="{og_description}">
<meta property="og:site_name"   content="Solstice EMEA Migration Agent">
<meta name="description"        content="{og_description}">
<meta name="twitter:card"       content="summary">
<meta name="twitter:title"      content="{og_title}">
<meta name="twitter:description" content="{og_description}">

<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,700;1,9..144,400&family=Geist+Mono:wght@400;500&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --bg:     #F7F5F1;
  --card:   #FFFFFF;
  --text:   #1A1209;
  --muted:  #7C776E;
  --border: #E5E1D8;
  --ink:    #0F1923;
}}
body {{ background: var(--bg); color: var(--text); font-family: 'DM Sans', sans-serif; font-size: 14px; min-height: 100vh; }}

/* Header */
.hdr {{ background: var(--ink); color: #F7F5F1; padding: 2.5rem 3rem 2.2rem; position: relative; overflow: hidden; }}
.hdr::after {{ content:''; position:absolute; bottom:-80px; right:-80px; width:300px; height:300px; border-radius:50%; background:rgba(255,255,255,0.03); pointer-events:none; }}
.hdr-eye {{ font-family:'Geist Mono',monospace; font-size:10px; letter-spacing:0.2em; text-transform:uppercase; color:#6A8099; margin-bottom:0.5rem; }}
.hdr-title {{ font-family:'Fraunces',serif; font-size:clamp(2.4rem,5vw,3.8rem); font-weight:700; letter-spacing:-0.025em; line-height:1; }}
.hdr-title em {{ font-style:italic; font-weight:400; color:#7EB8FF; }}
.hdr-sub {{ font-family:'Geist Mono',monospace; font-size:11px; color:#6A8099; margin-top:1rem; letter-spacing:0.04em; }}
.hdr-meta {{ position:absolute; top:2.5rem; right:3rem; text-align:right; display:flex; flex-direction:column; gap:1rem; }}
.hdr-pill {{ display:flex; flex-direction:column; align-items:flex-end; }}
.hdr-num {{ font-family:'Fraunces',serif; font-size:3.2rem; font-weight:600; line-height:1; color:#FFF; }}
.hdr-num-lbl {{ font-family:'Geist Mono',monospace; font-size:9px; letter-spacing:0.18em; text-transform:uppercase; color:#6A8099; }}

/* Stats bar */
.stats {{ background:var(--card); border-bottom:1px solid var(--border); padding:1rem 3rem; display:flex; gap:2rem; align-items:center; flex-wrap:wrap; }}
.stats-grp {{ display:flex; gap:1.5rem; align-items:center; }}
.stats-div {{ width:1px; height:32px; background:var(--border); }}
.stat {{ display:flex; flex-direction:column; gap:2px; }}
.stat-n {{ font-family:'Fraunces',serif; font-size:1.5rem; font-weight:600; line-height:1; }}
.stat-l {{ font-family:'Geist Mono',monospace; font-size:9px; letter-spacing:0.12em; text-transform:uppercase; color:var(--muted); }}

/* Wrapper */
.wrap {{ max-width:1300px; margin:0 auto; padding:2.5rem 3rem; display:flex; flex-direction:column; gap:3.5rem; }}

/* Section headers */
.sec-hdr {{ display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:1.25rem; padding-bottom:0.75rem; border-bottom:2px solid var(--ink); }}
.sec-title {{ font-family:'Fraunces',serif; font-size:1.6rem; font-weight:700; letter-spacing:-0.02em; }}
.sec-sub {{ font-size:12px; color:var(--muted); margin-top:0.2rem; font-family:'Geist Mono',monospace; letter-spacing:0.04em; }}
.sec-count {{ font-family:'Fraunces',serif; font-size:2.8rem; font-weight:600; color:var(--muted); line-height:1; }}

/* Task cards */
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:1.2rem; }}
.card {{ background:var(--card); border:1px solid var(--border); border-left:4px solid #ccc; border-radius:8px; padding:1.2rem 1.4rem; display:flex; flex-direction:column; gap:0.5rem; transition:box-shadow 0.16s,transform 0.16s; }}
.card:hover {{ box-shadow:0 8px 28px rgba(0,0,0,0.08); transform:translateY(-2px); }}
.card-top {{ display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap; }}
.badge {{ font-family:'Geist Mono',monospace; font-size:9.5px; font-weight:500; letter-spacing:0.08em; text-transform:uppercase; padding:3px 7px; border-radius:4px; border:1px solid; }}
.pri-wrap {{ margin-left:auto; display:flex; align-items:center; gap:5px; }}
.pri-dot {{ width:7px; height:7px; border-radius:50%; display:inline-block; }}
.pri-txt {{ font-family:'Geist Mono',monospace; font-size:9.5px; font-weight:500; letter-spacing:0.1em; text-transform:uppercase; }}
.card-name {{ font-family:'Fraunces',serif; font-size:1.05rem; font-weight:600; color:var(--ink); line-height:1.2; margin-top:0.15rem; }}
.card-id {{ font-family:'Geist Mono',monospace; font-size:10.5px; color:var(--muted); }}
.card-meta {{ font-size:12px; color:var(--muted); font-weight:500; }}
.card-action {{ font-family:'Fraunces',serif; font-size:13.5px; font-style:italic; font-weight:400; line-height:1.6; color:var(--text); background:var(--bg); border-radius:5px; padding:0.6rem 0.75rem; margin-top:0.15rem; }}
.change {{ font-size:11.5px; color:var(--muted); display:flex; gap:0.5rem; align-items:baseline; }}
.chg-lbl {{ font-family:'Geist Mono',monospace; font-size:9px; text-transform:uppercase; letter-spacing:0.1em; flex-shrink:0; }}
.chg-val {{ font-family:'Geist Mono',monospace; font-size:11px; color:var(--text); }}
.card-ts {{ font-family:'Geist Mono',monospace; font-size:9.5px; color:#B5AFA8; margin-top:auto; padding-top:0.5rem; border-top:1px solid var(--border); }}

/* Action groups */
.action-group {{ margin-bottom:1.75rem; }}
.action-group-hdr {{ display:flex; align-items:center; gap:0.65rem; padding:0.65rem 0.9rem; border-left:3px solid; background:var(--card); border-radius:0 6px 6px 0; margin-bottom:0.6rem; }}
.ag-dot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; }}
.ag-name {{ font-weight:600; font-size:13.5px; }}
.ag-count {{ font-family:'Fraunces',serif; font-size:1.1rem; font-weight:700; margin-left:0.3rem; }}
.ag-desc {{ font-size:11.5px; color:var(--muted); margin-left:auto; font-style:italic; }}

/* Tables */
.tbl-wrap {{ overflow-x:auto; border-radius:8px; border:1px solid var(--border); }}
.acct-tbl {{ width:100%; border-collapse:collapse; background:var(--card); }}
.acct-tbl thead tr {{ background:#F2EFE9; }}
.acct-tbl th {{ font-family:'Geist Mono',monospace; font-size:9.5px; letter-spacing:0.1em; text-transform:uppercase; color:var(--muted); padding:0.6rem 1rem; text-align:left; font-weight:500; border-bottom:1px solid var(--border); white-space:nowrap; }}
.acct-tbl td {{ padding:0.6rem 1rem; border-bottom:1px solid var(--border); vertical-align:middle; }}
.acct-tbl tr:last-child td {{ border-bottom:none; }}
.acct-tbl tr:hover td {{ background:#FAFAF7; }}
.tbl-name {{ font-weight:600; color:var(--ink); font-size:13px; }}
.tbl-region,.tbl-cse,.tbl-date,.tbl-exp {{ font-family:'Geist Mono',monospace; font-size:11px; color:var(--muted); white-space:nowrap; }}
.tbl-notes {{ max-width:340px; }}
.notes-text {{ font-size:12px; color:var(--text); line-height:1.45; display:block; }}
.notes-none {{ font-size:11px; color:#C5BFB5; font-style:italic; font-family:'Geist Mono',monospace; }}
.blocker-tags {{ display:flex; flex-wrap:wrap; gap:4px; margin-top:5px; }}
.blocker-tag {{ font-family:'Geist Mono',monospace; font-size:9.5px; padding:2px 6px; border-radius:3px; background:#FEF3C7; color:#92400E; border:1px solid #FCD34D; white-space:nowrap; }}
.status-chip {{ font-family:'Geist Mono',monospace; font-size:10px; font-weight:500; padding:2px 7px; border-radius:4px; border:1px solid; white-space:nowrap; }}
.done-chip {{ font-family:'Geist Mono',monospace; font-size:11px; color:#15803D; background:#F0FDF4; border:1px solid #86EFAC; padding:3px 8px; border-radius:4px; white-space:nowrap; }}

.empty {{ grid-column:1/-1; text-align:center; padding:5rem; font-family:'Fraunces',serif; font-size:1.1rem; font-style:italic; color:var(--muted); }}
.empty-sm {{ padding:2rem; text-align:center; font-family:'Fraunces',serif; font-style:italic; color:var(--muted); font-size:1rem; }}

/* Alert Banner */
.alert-banner {{ display:flex; justify-content:space-between; align-items:flex-start; background:#7F1D1D; color:#FEF2F2; padding:1rem 2rem; gap:1rem; border-bottom:3px solid #DC2626; }}
.alert-left {{ display:flex; align-items:flex-start; gap:1rem; }}
.alert-icon {{ font-family:'Fraunces',serif; font-size:1.6rem; font-weight:700; color:#FCA5A5; flex-shrink:0; line-height:1; margin-top:2px; }}
.alert-title {{ font-weight:600; font-size:13.5px; margin-bottom:0.6rem; color:#FEF2F2; letter-spacing:0.01em; }}
.alert-body {{ display:flex; flex-wrap:wrap; gap:0.5rem; }}
.alert-item {{ display:flex; flex-direction:column; background:rgba(0,0,0,0.2); border:1px solid rgba(255,255,255,0.15); border-radius:6px; padding:0.4rem 0.75rem; min-width:160px; }}
.alert-acct {{ font-size:12px; font-weight:600; color:#FEF2F2; }}
.alert-owner {{ font-family:'Geist Mono',monospace; font-size:10px; color:#FCA5A5; margin-top:2px; }}
.alert-no-owner {{ color:#F87171; font-weight:700; letter-spacing:0.05em; }}
.alert-close {{ background:none; border:none; color:#FCA5A5; font-size:1.1rem; cursor:pointer; padding:0.25rem 0.5rem; flex-shrink:0; line-height:1; opacity:0.7; }}
.alert-close:hover {{ opacity:1; }}

/* Chart */
.chart-wrap {{ display:flex; gap:2.5rem; align-items:flex-start; flex-wrap:wrap; }}
.chart-canvas-wrap {{ position:relative; width:240px; height:240px; flex-shrink:0; }}
.chart-centre {{ position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); text-align:center; pointer-events:none; }}
.chart-centre-n {{ font-family:'Fraunces',serif; font-size:2rem; font-weight:700; color:var(--ink); line-height:1; }}
.chart-centre-l {{ font-family:'Geist Mono',monospace; font-size:9px; letter-spacing:0.14em; text-transform:uppercase; color:var(--muted); }}
.chart-table-wrap {{ flex:1; min-width:260px; overflow-x:auto; }}
.chart-tbl {{ width:100%; border-collapse:collapse; }}
.chart-tbl th {{ font-family:'Geist Mono',monospace; font-size:9px; letter-spacing:0.1em; text-transform:uppercase; color:var(--muted); padding:0.4rem 0.75rem; text-align:left; border-bottom:1px solid var(--border); }}
.chart-tbl td {{ padding:0.35rem 0.75rem; font-size:12.5px; border-bottom:1px solid var(--border); vertical-align:middle; }}
.chart-tbl tr:last-child td {{ border-bottom:none; }}
.chart-tbl tr:hover td {{ background:#FAFAF7; }}
.chart-dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:7px; flex-shrink:0; vertical-align:middle; }}
.chart-count {{ font-family:'Fraunces',serif; font-size:1rem; font-weight:600; text-align:right; width:50px; }}
.chart-pct {{ font-family:'Geist Mono',monospace; font-size:11px; color:var(--muted); text-align:right; width:50px; }}
.chart-row-link {{ cursor:pointer; }}
.chart-row-link:hover td {{ background:#F0EDE6; }}
.chart-row-plain {{ cursor:default; }}
.chart-arrow {{ font-size:10px; color:var(--muted); margin-left:4px; }}

/* Footer */
.footer {{ text-align:center; padding:1.8rem; font-family:'Geist Mono',monospace; font-size:9.5px; letter-spacing:0.14em; text-transform:uppercase; color:#C5BFB5; border-top:1px solid var(--border); margin-top:1rem; }}

@media (max-width:700px) {{
  .hdr,.stats,.wrap {{ padding-left:1.25rem; padding-right:1.25rem; }}
  .hdr-meta {{ display:none; }}
  .grid {{ grid-template-columns:1fr; }}
  .ag-desc {{ display:none; }}
}}
</style>
</head>
<body>

<header class="hdr">
  <div class="hdr-eye">Solstice · EMEA CC Migration Intelligence</div>
  <h1 class="hdr-title">Migration <em>Report</em></h1>
  <div class="hdr-sub">Generated {generated_at}</div>
  <div class="hdr-meta">
    <div class="hdr-pill">
      <div class="hdr-num">{total_accounts}</div>
      <div class="hdr-num-lbl">Total Accounts</div>
    </div>
    <div class="hdr-pill">
      <div class="hdr-num" style="color:#F87171">{n_action}</div>
      <div class="hdr-num-lbl">Need Action</div>
    </div>
    <div class="hdr-pill">
      <div class="hdr-num" style="color:#86EFAC">{n_completed}</div>
      <div class="hdr-num-lbl">Completed</div>
    </div>
  </div>
</header>

<div class="stats">
  <div class="stats-grp">{cat_stats}</div>
  <div class="stats-div"></div>
  <div class="stats-grp">{pri_stats}</div>
</div>

{no_status_banner}

<div class="wrap">

  <!-- SECTION 0: Status Overview -->
  <section>
    {_section_header("Status Overview", "Distribution of all EMEA accounts by current migration status", total_accounts)}
    {status_chart}
  </section>

  <!-- SECTION 1: Approved Tasks -->
  <section>
    {_section_header("Approved Tasks", "Actions reviewed and approved in this session", total_tasks)}
    <div class="grid">{task_cards}</div>
  </section>

  <!-- SECTION 2: What To Do Next -->
  <section>
    {_section_header("What To Do Next", "Accounts requiring follow-up based on current status", n_action)}
    {action_html if action_html else '<div class="empty-sm">No action items detected.</div>'}
  </section>

  <!-- SECTION 3: Completed -->
  <section id="section-completed">
    {_section_header("Completed", "Accounts that reached Completed status — migration done", n_completed)}
    {completed_html}
  </section>

</div>

<footer class="footer">
  Solstice Agent · EMEA CC Migration · {generated_at}
</footer>

</body>
</html>"""


def generate_report(
    csv_path: Path = PENDING_TASKS_FILE,
    state_path: Path = STATE_FILE,
    output_dir: Path = OUTPUTS_DIR,
) -> Path:
    """Generate HTML report. Returns path to output file."""
    output_dir.mkdir(exist_ok=True)
    tasks    = _load_tasks(csv_path)
    accounts = _load_state(state_path)
    now          = datetime.now(timezone.utc)
    generated_at = now.strftime("%d %b %Y · %H:%M UTC")
    slug         = now.strftime("%Y%m%d_%H%M%S")
    out_path     = output_dir / f"report_{slug}.html"
    out_path.write_text(_render(tasks, accounts, generated_at), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    path = generate_report()
    print(f"Report generated: {path}")
