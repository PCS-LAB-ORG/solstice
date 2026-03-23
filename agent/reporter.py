"""
reporter.py — Generate a light HTML report with three sections:
  1. Approved Tasks (from pending_tasks.csv)
  2. Open Actions (problematic statuses from state.json)
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
    "Sales Hold": {
        "statuses": ["Sales Hold"],
        "color": "#7C2D12",
        "bg": "#FFF7ED",
        "dot": "#EA580C",
        "desc": "CRITICAL — blocked by RFE, RFP or competition; someone is stopping progress",
    },
    "Churning / Churned": {
        "statuses": ["Churning/Churned"],
        "color": "#7F1D1D",
        "bg": "#FEF2F2",
        "dot": "#DC2626",
        "desc": "Customer at risk of leaving or already churned",
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

def _lf(acc: dict) -> str:
    """Return live fire badge with DC name if account is live fire."""
    if not acc.get("live_fire"):
        return ""
    dc = acc.get("live_fire_dc", "").strip()
    dc_label = f'<span class="lf-dc">{dc}</span>' if dc else ""
    dc_title = dc if dc else "TBD"
    return f'<span class="lf-icon" title="Live Fire · DC: {dc_title}">🔥 DC{dc_label}</span>'


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
          <div class="card-name">{name}{_lf(t)}</div>
          <div class="card-id">{acc_id}</div>
          <div class="card-meta">{region} · {cse}</div>
          <div class="card-action">{action}</div>
          {change_html}
          <div class="card-ts">{ts}</div>
        </div>"""
    return cards


def _action_section(accounts: dict) -> str:
    """Build the Open Actions section from state accounts."""
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

            # Cross-check: blocked CSV signal vs EMEA tracker status
            bd_signal = (acc.get("blocked_data") or {}).get("signal", "")
            cross_check_html = ""
            if bd_signal == "green" and is_outreach:
                cross_check_html = '<span class="xcheck-green tooltip-wrap">✅ Tracker outdated<span class="tooltip-text">Blocked accounts CSV shows ✅ green — outreach complete. EMEA tracker status is stale and needs updating by the CSE.</span></span>'
            elif bd_signal == "blocked":
                cross_check_html = '<span class="xcheck-blocked tooltip-wrap">🛑 Confirmed blocked<span class="tooltip-text">Blocked accounts CSV confirms this account is hard blocked. Check Status Detail in Milestone Tracker.</span></span>'
            elif bd_signal == "at_risk":
                cross_check_html = '<span class="xcheck-risk tooltip-wrap">👎 At risk<span class="tooltip-text">Blocked accounts CSV flags this account as at risk or behind. Check Status Detail in Milestone Tracker.</span></span>'

            # Blockers tags — shown for all groups when present
            blocker_html = ""
            if blockers:
                tags = "".join(
                    f'<span class="blocker-tag">{b.replace(" (blocker)", "").strip()}</span>'
                    for b in blockers
                )
                blocker_html = f'<div class="blocker-tags">{tags}</div>'

            # AI enrichment — blocker / owner / accountable extracted from comments
            enrichment  = acc.get("ai_enrichment") or {}
            ai_blocker  = enrichment.get("blocker")
            ai_owner    = enrichment.get("owner")
            ai_accountable = enrichment.get("accountable")

            # Build notes cell: AI enrichment first, raw comments as fallback
            raw_comments = (acc.get("comments") or "").replace("\r\n", " ").replace("\n", " ").strip()
            notes_parts = []
            if ai_blocker:
                notes_parts.append(f'<div class="ai-field"><span class="ai-label">Blocker</span> {ai_blocker}</div>')
            if ai_owner and ai_owner != cse:
                notes_parts.append(f'<div class="ai-field"><span class="ai-label">Owner</span> {ai_owner}</div>')
            if ai_accountable:
                notes_parts.append(f'<div class="ai-field ai-accountable"><span class="ai-label">Accountable</span><span class="ai-accountable-value">{ai_accountable}</span></div>')
            if not notes_parts and raw_comments:
                notes_parts.append(f'<span class="notes-text">{raw_comments[:200]}{"…" if len(raw_comments) > 200 else ""}</span>')
            elif not notes_parts and is_outreach:
                notes_parts.append('<span class="notes-none">No data available</span>')

            notes_html = "".join(notes_parts)

            # CSE — flag missing owner inline
            cse_html = cse if cse and cse != "—" else '<span class="no-owner-inline">⚠ NO OWNER</span>'

            if is_blocked:
                blocker_content = blocker_html if blocker_html else '<span class="notes-none">No blockers recorded</span>'
                combined_notes = f'{blocker_content}{"<div style=\'margin-top:4px\'>" + notes_html + "</div>" if notes_html else ""}'
                rows_html += f"""
                <tr>
                  <td class="tbl-name">{name}{_lf(acc)}{f"<div>{cross_check_html}</div>" if cross_check_html else ""}</td>
                  <td class="tbl-region">{region}</td>
                  <td class="tbl-cse">{cse_html}</td>
                  <td class="tbl-date">{changed}</td>
                  <td class="tbl-notes">{combined_notes}</td>
                </tr>"""
            else:
                rows_html += f"""
                <tr>
                  <td class="tbl-name">{name}{_lf(acc)}{blocker_html}{f"<div>{cross_check_html}</div>" if cross_check_html else ""}</td>
                  <td><span class="status-chip" style="color:{cfg['color']};background:{cfg['bg']};border-color:{cfg['dot']}55">{status}</span></td>
                  <td class="tbl-region">{region}</td>
                  <td class="tbl-cse">{cse_html}</td>
                  <td class="tbl-date">{last_col_html}</td>
                  <td class="tbl-notes">{notes_html}</td>
                </tr>"""

        last_col_header  = "Last Contact" if is_outreach else "Since"
        blocked_headers  = "<th>Region</th><th>CSE</th><th>Since</th><th>Notes / Blockers</th>" if is_blocked else f"<th>Status</th><th>Region</th><th>CSE</th><th>{last_col_header}</th><th>Notes</th>"
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


SIGNAL_STYLE = {
    "green":    ("#065F46", "#ECFDF5", "✅"),
    "at_risk":  ("#92400E", "#FFFBEB", "👎"),
    "blocked":  ("#7F1D1D", "#FEF2F2", "🛑"),
    "unknown":  ("#6B7280", "#F9FAFB", "·"),
}

SUBTYPE_LABEL = {
    "core_rep_blocking": ("CORE REP BLOCKING", "#DC2626"),
    "tech_blocker":      ("TECH BLOCKER",      "#D97706"),
    "no_contact":        ("NO CONTACT",         "#7C3AED"),
    "active_deal":       ("ACTIVE DEAL",        "#1D4ED8"),
    "no_response":       ("NO RESPONSE",        "#6B7280"),
}


def _milestone(done: bool, date: str) -> str:
    if done:
        return f'<span class="ms-done">✓</span>'
    if date:
        return f'<span class="ms-date">{date}</span>'
    return '<span class="ms-blank">—</span>'


def _blocked_milestone_section(accounts: dict) -> tuple[str, int]:
    """Build the Milestone Tracker section from blocked_data in state."""
    rows_with_data = [
        (aid, acc, acc["blocked_data"])
        for aid, acc in accounts.items()
        if acc.get("blocked_data") and acc.get("customer_name", "").strip()
    ]
    if not rows_with_data:
        return '<div class="empty-sm">No milestone data loaded. Drop blocked_accounts.csv into data/.</div>', 0

    # Sort: core_rep_blocking first, then at_risk, then blocked, then green
    signal_order = {"blocked": 0, "at_risk": 1, "core_rep_blocking": -1, "green": 3, "unknown": 4}

    def sort_key(item):
        _, _, bd = item
        if bd.get("subtype") == "core_rep_blocking":
            return -1
        return signal_order.get(bd.get("signal", "unknown"), 4)

    rows_with_data.sort(key=sort_key)

    rows_html = ""
    for aid, acc, bd in rows_with_data:
        name    = acc.get("customer_name", "—")
        cse     = acc.get("active_cse") or ""
        cse_html = cse if cse else '<span class="no-owner-inline">⚠ NO OWNER</span>'
        team    = bd.get("team", "")
        is_cs   = bd.get("is_cs_team", False)
        team_html = f'<span class="cs-team-badge">CS</span>' if is_cs else f'<span class="named-badge">{team}</span>'

        signal  = bd.get("signal", "unknown")
        subtype = bd.get("subtype")
        color, bg, emoji = SIGNAL_STYLE.get(signal, SIGNAL_STYLE["unknown"])

        sd_label = ""
        if subtype and subtype in SUBTYPE_LABEL:
            lbl, lbl_color = SUBTYPE_LABEL[subtype]
            sd_label = f'<span class="subtype-badge" style="color:{lbl_color};border-color:{lbl_color}44;background:{lbl_color}11">{lbl}</span>'

        status_detail = bd.get("status_detail", "")
        # Strip emoji prefix for display
        clean_sd = status_detail
        for emoji_char in ("✅", "👎", "🛑"):
            clean_sd = clean_sd.replace(emoji_char, "").strip()
        sd_html = f'{sd_label}<div class="sd-text">{clean_sd[:120]}{"…" if len(clean_sd) > 120 else ""}</div>' if clean_sd else sd_label

        milestone_cat = bd.get("milestone_category", "")
        cat_html = f'<span class="ms-cat">{milestone_cat}</span>' if milestone_cat else ""

        rows_html += f"""
        <tr>
          <td class="tbl-name">
            {name}{_lf(acc)}
            <div style="margin-top:3px;display:flex;gap:4px;flex-wrap:wrap">{team_html}{cat_html}</div>
          </td>
          <td class="tbl-cse">{cse_html}</td>
          <td style="text-align:center">{_milestone(bd.get('m3_complete'), bd.get('m3_planned',''))}</td>
          <td style="text-align:center">{_milestone(bd.get('m8_started'), bd.get('m8_planned',''))}</td>
          <td style="text-align:center">{_milestone(bd.get('m9_complete'), bd.get('m9_planned',''))}</td>
          <td><span class="signal-dot" style="color:{color}">{emoji}</span></td>
          <td class="tbl-notes">{sd_html}</td>
        </tr>"""

    return f"""
    <div class="tbl-wrap">
      <table class="acct-tbl">
        <thead><tr>
          <th>Customer</th><th>CSE</th>
          <th>M3 Buy-in</th><th>M8 Started</th><th>M9 Complete</th>
          <th>Signal</th><th>Status Detail</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>""", len(rows_with_data)


def _stall_section(accounts: dict) -> tuple[str, int]:
    """Milestone stall report — Scale cohort accounts over timeline limits."""
    from agent.blocked_parser import check_milestone_stalls
    stalls = check_milestone_stalls(accounts)
    if not stalls:
        return '<div class="empty-sm">No milestone stalls detected.</div>', 0

    rows_html = ""
    for s in stalls:
        over   = s["over_by"]
        color  = "#DC2626" if over > 14 else "#D97706"
        rows_html += f"""
        <tr>
          <td class="tbl-name">{s['customer_name']}</td>
          <td class="tbl-cse">{s['cse']}</td>
          <td><span class="status-chip" style="color:#1D4ED8;background:#EFF6FF;border-color:#93C5FD">{s['transition']}</span></td>
          <td style="font-family:'Geist Mono',monospace;font-size:11px">{s['ref_date']}</td>
          <td style="font-family:'Geist Mono',monospace;font-size:11px;color:{color};font-weight:700">+{over}d over</td>
          <td class="tbl-region">{s['status']}</td>
        </tr>"""

    return f"""
    <div class="tbl-wrap">
      <table class="acct-tbl">
        <thead><tr>
          <th>Customer</th><th>CSE</th><th>Transition</th>
          <th>Reference Date</th><th>Over Limit</th><th>Status</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>""", len(stalls)


def _ps_unmatched_section() -> str:
    """Show PS-eligible accounts that don't appear in the EMEA tracker — separate sub-table."""
    try:
        import csv as csvlib
        ps_file = Path(__file__).parent.parent / "data" / "ps_tracker.csv"
        if not ps_file.exists():
            return ""
        all_ps = list(csvlib.DictReader(open(ps_file, encoding="utf-8-sig")))
        # Load matched names from state
        import json as jsonlib
        from agent.constants import STATE_FILE
        state = jsonlib.loads(STATE_FILE.read_text())
        matched_names = {a.get("ps_data", {}).get("ps_name", "") for a in state["accounts"].values() if a.get("ps_data")}
        unmatched = [r for r in all_ps if r.get("PS Eligible Account Name", "").strip() not in matched_names
                     and r.get("PS Eligible Account Name", "").strip()]
        if not unmatched:
            return ""
        rows = "".join(
            f'<tr><td class="tbl-name">{r["PS Eligible Account Name"]}</td>'
            f'<td class="tbl-region">{r.get("Country","—")}</td>'
            f'<td class="tbl-cse">{r.get("Assigned PSC","—") or "—"}</td>'
            f'<td class="tbl-cse">{r.get("Assigned PM","—") or "—"}</td>'
            f'<td class="tbl-region">{r.get("Estimated Time for PS Engagement","—") or "—"}</td></tr>'
            for r in sorted(unmatched, key=lambda x: x.get("PS Eligible Account Name",""))
        )
        return f"""
        <div style="margin-top:1.5rem">
          <div class="sec-sub" style="margin-bottom:0.6rem;color:#F59E0B">⚠ PS Eligible — Not yet in EMEA Tracker ({len(unmatched)} accounts)</div>
          <div class="tbl-wrap">
            <table class="acct-tbl">
              <thead><tr><th>Customer</th><th>Country</th><th>PSC</th><th>PM</th><th>Timeline</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
        </div>"""
    except Exception as e:
        return f'<div class="empty-sm">Could not load unmatched PS accounts: {e}</div>'


def _ps_section(accounts: dict) -> tuple[str, int]:
    """Build PS Engagement section from accounts with ps_data."""
    ps_accounts = [
        (aid, acc, acc["ps_data"])
        for aid, acc in accounts.items()
        if acc.get("ps_data") and acc.get("customer_name", "").strip()
    ]
    if not ps_accounts:
        return '<div class="empty-sm">No PS data loaded. Drop ps_tracker.csv into data/.</div>', 0

    # Sort: active first (In Progress, Starting), then On Hold, then blank
    status_order = {"In Progress": 0, "Starting": 1, "Pending IKO": 2, "On Hold": 3, "Completed": 4, "": 9}
    ps_accounts.sort(key=lambda x: (status_order.get(x[2].get("ps_status", ""), 9), x[1].get("customer_name", "")))

    PS_STATUS_STYLE = {
        "In Progress": ("#065F46", "#ECFDF5"),
        "Starting":    ("#1D4ED8", "#EFF6FF"),
        "Pending IKO": ("#92400E", "#FFFBEB"),
        "On Hold":     ("#6B7280", "#F3F4F6"),
        "Completed":   ("#15803D", "#F0FDF4"),
    }

    rows_html = ""
    for aid, acc, ps in ps_accounts:
        name        = acc.get("customer_name", "—")
        cse         = acc.get("active_cse") or ""
        cse_html    = cse if cse else '<span class="no-owner-inline">⚠ NO OWNER</span>'
        psc         = ps.get("psc") or "—"
        psc_shadow  = ps.get("psc_shadow") or ""
        pm          = ps.get("pm") or "—"
        ps_status   = ps.get("ps_status") or "—"
        clarizen    = ps.get("clarizen_id") or "—"
        timeline    = ps.get("timeline") or "—"
        conf        = ps.get("match_confidence", 0)

        ps_color, ps_bg = PS_STATUS_STYLE.get(ps_status, ("#6B7280", "#F9FAFB"))
        psc_html = psc
        if psc_shadow:
            psc_html += f'<span class="psc-shadow"> / {psc_shadow}</span>'

        conf_color = "#16A34A" if conf >= 0.95 else "#D97706"
        rows_html += f"""
        <tr>
          <td class="tbl-name">{name}{_lf(acc)}<div style="margin-top:2px"><span class="cs-team-badge">PS</span></div></td>
          <td class="tbl-cse">{cse_html}</td>
          <td class="tbl-cse">{psc_html}</td>
          <td class="tbl-cse">{pm}</td>
          <td><span class="status-chip" style="color:{ps_color};background:{ps_bg};border-color:{ps_color}44">{ps_status}</span></td>
          <td class="tbl-region">{clarizen}</td>
          <td class="tbl-notes" style="font-size:11.5px;color:var(--muted)">{timeline}</td>
          <td style="font-family:'Geist Mono',monospace;font-size:9px;color:{conf_color}">{conf:.0%}</td>
        </tr>"""

    return f"""
    <div class="tbl-wrap">
      <table class="acct-tbl">
        <thead><tr>
          <th>Customer</th><th>CSE</th><th>PSC</th><th>PM</th>
          <th>PS Status</th><th>Clarizen</th><th>Timeline</th><th>Match</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>""", len(ps_accounts)


def _status_history_section() -> tuple[str, int]:
    """Show status changes per account from DB status_history table."""
    try:
        from agent.db import get_db
        with get_db() as conn:
            rows = conn.execute("""
                SELECT a.customer_name, a.active_cse, a.sales_region,
                       sh.old_status, sh.new_status, sh.changed_at, sh.source,
                       a.live_fire, a.live_fire_dc
                FROM status_history sh
                JOIN accounts a ON a.account_id = sh.account_id
                WHERE sh.new_status IS NOT NULL AND sh.new_status != ''
                ORDER BY sh.changed_at DESC
            """).fetchall()
        if not rows:
            return '<div class="empty-sm">No status changes recorded yet — changes will appear after the next pipeline run detects a diff.</div>', 0
        # Group by account
        from collections import defaultdict
        by_account: dict = defaultdict(list)
        meta: dict = {}
        for r in rows:
            name = r["customer_name"]
            by_account[name].append(r)
            if name not in meta:
                meta[name] = {"cse": r["active_cse"] or "—", "region": r["sales_region"] or "—",
                               "live_fire": r["live_fire"], "live_fire_dc": r["live_fire_dc"] or ""}
        html = ""
        for name in sorted(by_account, key=lambda n: by_account[n][0]["changed_at"], reverse=True):
            changes = by_account[name]
            m = meta[name]
            lf = _lf(m)
            rows_html = "".join(
                f'<tr>'
                f'<td class="tbl-date">{r["changed_at"][:10]}</td>'
                f'<td><span class="status-chip" style="color:var(--muted);background:rgba(255,255,255,0.05);border-color:var(--border)">{r["old_status"] or "—"}</span></td>'
                f'<td><span style="color:var(--muted)">→</span></td>'
                f'<td><span class="status-chip" style="color:#5EEAD4;background:rgba(20,184,166,0.1);border-color:rgba(20,184,166,0.3)">{r["new_status"]}</span></td>'
                f'<td class="tbl-region" style="font-size:9px;opacity:.6">{r["source"]}</td>'
                f'</tr>'
                for r in changes
            )
            html += f"""
            <div style="margin-bottom:1.25rem">
              <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.4rem">
                <span class="tbl-name">{name}{lf}</span>
                <span class="tbl-region">{m["region"]}</span>
                <span class="tbl-cse" style="margin-left:auto">{m["cse"]}</span>
              </div>
              <table class="acct-tbl" style="font-size:12px">
                <thead><tr><th>Date</th><th>From</th><th></th><th>To</th><th>Source</th></tr></thead>
                <tbody>{rows_html}</tbody>
              </table>
            </div>"""
        return html, len(by_account)
    except Exception as e:
        return f'<div class="empty-sm">Status history unavailable: {e}</div>', 0


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
          <td class="tbl-name">{name}{_lf(acc)}</td>
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


def _weekly_view(accounts: dict) -> str:
    """
    Weekly M8/M9 completion tracker by North America week number (Sunday start).
    Shows past weeks (planned vs done), current week, and 4-week forecast.
    """
    from datetime import datetime, date, timedelta

    today = date(2026, 3, 23)

    def _parse(s: str):
        if not s: return None
        for fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try: return datetime.strptime(s.strip(), fmt).date()
            except: pass
        return None

    def _week_key(d: date) -> str:
        # North America week: Sunday-start, strftime %U
        return d.strftime("%Y-W%U")

    def _week_label(d: date) -> str:
        # Week start (Sunday) and end (Saturday)
        start = d - timedelta(days=d.weekday() + 1) if d.weekday() != 6 else d
        end   = start + timedelta(days=6)
        wnum  = int(d.strftime("%U"))
        return f"Week {wnum} · {start.strftime('%d %b')}–{end.strftime('%d %b')}"

    # Build {week_key: {m8: [], m9: [], m9_done: []}}
    weeks: dict = {}

    for acc in accounts.values():
        bd = acc.get("blocked_data") or {}
        if not bd: continue
        name   = acc.get("customer_name", "—")
        cse    = acc.get("active_cse") or "—"
        status = acc.get("status", "—")
        lf_icon = _lf(acc)

        m8d = _parse(bd.get("m8_planned", ""))
        m9d = _parse(bd.get("m9_planned", ""))
        m8_done = bd.get("m8_started", False)
        m9_done = bd.get("m9_complete", False) or status == "Completed"

        if m8d:
            k = _week_key(m8d)
            weeks.setdefault(k, {"date": m8d, "m8": [], "m9": [], "m9_done": []})
            weeks[k]["m8"].append({"name": name, "cse": cse, "done": m8_done, "status": status, "lf": lf_icon})

        if m9d:
            k = _week_key(m9d)
            weeks.setdefault(k, {"date": m9d, "m8": [], "m9": [], "m9_done": []})
            if m9_done:
                weeks[k]["m9_done"].append({"name": name, "cse": cse, "status": status, "lf": lf_icon})
            else:
                weeks[k]["m9"].append({"name": name, "cse": cse, "status": status, "lf": lf_icon})

    if not weeks:
        return '<div class="empty-sm">No milestone date data available.</div>', 0

    # Show 4 weeks back + current + 6 weeks forward
    today_week = _week_key(today)
    sorted_weeks = sorted(weeks.items(), key=lambda x: x[0])

    today_idx = next((i for i, (k, _) in enumerate(sorted_weeks) if k >= today_week), 0)
    start_idx = max(0, today_idx - 4)
    display_weeks = sorted_weeks[start_idx:today_idx + 7]

    n_cols = len(display_weeks)
    html = f'<div class="weekly-grid" style="grid-template-columns:repeat({n_cols},1fr)">'
    for week_key, data in display_weeks:
        is_current = week_key == today_week
        is_past    = week_key < today_week
        label      = _week_label(data["date"])
        m8_list    = data["m8"]
        m9_list    = data["m9"]
        m9_done    = data["m9_done"]

        header_cls = "week-header-current" if is_current else ("week-header-past" if is_past else "week-header-future")

        # M9 done rows (green)
        done_rows = "".join(
            f'<div class="week-row week-done">✓ {r.get("lf","")}{r["name"]}<span class="week-cse">{r["cse"]}</span></div>'
            for r in sorted(m9_done, key=lambda x: x["name"])
        )
        # M9 planned rows
        m9_rows = "".join(
            f'<div class="week-row week-m9">M9 {r.get("lf","")}{r["name"]}<span class="week-cse">{r["cse"]}</span><span class="week-status">{r["status"]}</span></div>'
            for r in sorted(m9_list, key=lambda x: x["name"])
        )
        # M8 planned rows
        m8_rows = "".join(
            f'<div class="week-row week-m8">M8 {r.get("lf","")}{r["name"]}<span class="week-cse">{r["cse"]}</span><span class="week-status">{r["status"]}</span></div>'
            for r in sorted(m8_list, key=lambda x: x["name"])
        )

        total_m9 = len(m9_list) + len(m9_done)
        badge = f'<span class="week-badge-done">{len(m9_done)} done</span>' if m9_done else ""
        badge += f'<span class="week-badge-planned">{len(m9_list)} M9 planned</span>' if m9_list else ""
        badge += f'<span class="week-badge-m8">{len(m8_list)} M8</span>' if m8_list else ""

        html += f"""
        <div class="week-col {'week-col-current' if is_current else ''}">
          <div class="{header_cls}">
            <div class="week-label">{label}</div>
            <div class="week-badges">{badge}</div>
          </div>
          <div class="week-body">
            {done_rows}{m9_rows}{m8_rows}
            {"<div class='week-empty'>No milestones</div>" if not (done_rows or m9_rows or m8_rows) else ""}
          </div>
        </div>"""

    html += "</div>"
    return html, len(weeks)


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
        "Sales Hold":             "#EA580C",
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
        "Sales Hold":              "group-sales-hold",
        "Churning/Churned":        "group-churning-churned",
        "Backoff":                 "group-escalation-risk",
        "Cancelled":               "group-escalation-risk",
        "Blocked: Tech limitation":"group-blocked",
        "On Hold":                 "group-on-hold",
        "In Progress":             "group-active-migration",
        "Customer Engaged":        "group-active-migration",
        "Kick Off Scheduled":      "group-active-migration",
        "Customer Acceptance":     "group-active-migration",
        "PS":                      "section-ps",
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
          datasets: [{{ data: {values_js}, backgroundColor: {colors_js}, borderWidth: 2, borderColor: '#0D1117', hoverOffset: 8 }}]
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
    history_html, n_history     = _status_history_section()
    weekly_html, n_weeks        = _weekly_view(accounts)
    milestone_html, n_milestone = _blocked_milestone_section(accounts)
    stall_html, n_stalls        = _stall_section(accounts)
    ps_html, n_ps               = _ps_section(accounts)
    status_chart      = _status_chart(accounts)

    # ── Data Quality Alert — cross-checks all 3 CSVs ──────────────────────────
    from agent.constants import STATUSES as _STATUSES
    OUTREACH_ST = {"Ready To Engage", "Account team contacted"}

    _no_status     = [a for a in accounts.values() if not (a.get("status") or "").strip() and a.get("customer_name","").strip()]
    _unknown_st    = [a for a in accounts.values() if (a.get("status") or "").strip() and a.get("status") not in _STATUSES]
    _no_cse        = [a for a in accounts.values() if a.get("customer_name","").strip() and not (a.get("active_cse") or "").strip()]
    _stale_tracker = [a for a in accounts.values() if a.get("status") in OUTREACH_ST and (a.get("blocked_data") or {}).get("signal") == "green"]
    _no_email      = [a for a in accounts.values() if a.get("status") in OUTREACH_ST and not (a.get("email_sent") or "").strip()]

    def _dq_items(accs, label_field="customer_name", extra_field=None):
        items = ""
        for a in sorted(accs, key=lambda x: x.get("customer_name","")):
            owner = a.get("active_cse") or '<span class="alert-no-owner">⚠ NO OWNER</span>'
            extra = f' <span style="font-size:9px;opacity:.7">({a.get(extra_field,"")})</span>' if extra_field and a.get(extra_field) else ""
            items += (f'<div class="alert-item"><span class="alert-acct">{a.get("customer_name","—")}</span>'
                      f'<span class="alert-owner">{owner}{extra}</span></div>')
        return items

    dq_sections = []
    if _no_status:
        dq_sections.append(("No Status", len(_no_status), "EMEA tracker has no status — update immediately", _dq_items(_no_status)))
    if _unknown_st:
        dq_sections.append(("Invalid Status", len(_unknown_st), "Status value not in the known list", _dq_items(_unknown_st, extra_field="status")))
    if _no_cse:
        dq_sections.append(("No Owner / CSE", len(_no_cse), "No CSE assigned — who is responsible?", _dq_items(_no_cse)))
    if _stale_tracker:
        dq_sections.append(("Stale EMEA Tracker", len(_stale_tracker), "Blocked CSV shows ✅ green but EMEA tracker not updated — chase CSE to update sheet", _dq_items(_stale_tracker)))
    if _no_email:
        dq_sections.append(("In Outreach — No Email on Record", len(_no_email), "Status says outreach started but no email_sent date in sheet", _dq_items(_no_email)))

    total_dq = sum(s[1] for s in dq_sections)

    if dq_sections:
        dq_body = "".join(
            f'<div class="dq-group">'
            f'<div class="dq-group-title"><span class="dq-count">{n}</span>{title} — <span class="dq-desc">{desc}</span></div>'
            f'<div class="alert-body">{items}</div>'
            f'</div>'
            for title, n, desc, items in dq_sections
        )
        no_status_banner = f"""
    <div class="alert-banner" id="alert-banner">
      <div class="alert-left">
        <span class="alert-icon">!</span>
        <div style="flex:1">
          <div class="alert-title">
            {total_dq} data quality issues across {len(dq_sections)} categories — all 3 CSVs cross-checked
          </div>
          {dq_body}
        </div>
      </div>
    </div>"""
    else:
        no_status_banner = ""
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
  --bg:     #0D1117;
  --card:   #161B22;
  --text:   #E6EDF3;
  --muted:  #7D8590;
  --border: #21262D;
  --ink:    #010409;
}}
body {{ background: var(--bg); color: var(--text); font-family: 'DM Sans', sans-serif; font-size: 14px; min-height: 100vh; }}

/* ── Side Navigation ── */
.sidenav {{ position:fixed; left:0; top:0; height:100vh; width:200px; background:var(--ink); z-index:100; display:flex; flex-direction:column; overflow-y:auto; }}
.sidenav-inner {{ padding:1.5rem 0 2rem; display:flex; flex-direction:column; gap:2px; }}
.sidenav-title {{ font-family:'Geist Mono',monospace; font-size:9px; letter-spacing:0.18em; text-transform:uppercase; color:#4A6078; padding:0 1.25rem 0.75rem; }}
.sidenav-item {{ display:flex; align-items:center; gap:8px; padding:0.45rem 1.25rem; text-decoration:none; color:#8A9BB0; font-size:11.5px; font-family:'DM Sans',sans-serif; border-left:2px solid transparent; transition:color 0.15s, border-color 0.15s, background 0.15s; cursor:pointer; }}
.sidenav-item:hover {{ color:#F7F5F1; background:rgba(255,255,255,0.05); }}
.sidenav-active {{ color:#F7F5F1 !important; border-left-color:#7EB8FF !important; background:rgba(126,184,255,0.08) !important; }}
.sidenav-dot {{ width:5px; height:5px; border-radius:50%; background:currentColor; flex-shrink:0; opacity:0.5; }}
.sidenav-active .sidenav-dot {{ opacity:1; }}
.sidenav-label {{ flex:1; }}
.sidenav-count {{ font-family:'Geist Mono',monospace; font-size:9px; color:#4A6078; background:rgba(255,255,255,0.06); padding:1px 5px; border-radius:3px; }}
.sidenav-active .sidenav-count {{ color:#7EB8FF; }}
.sidenav-toggle-all {{ margin-top:1.5rem; padding:0 1.25rem; display:flex; gap:6px; flex-direction:column; }}
.sidenav-toggle-all button {{ background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.1); color:#8A9BB0; font-family:'Geist Mono',monospace; font-size:9px; letter-spacing:0.06em; text-transform:uppercase; padding:4px 8px; border-radius:4px; cursor:pointer; transition:background 0.15s,color 0.15s; }}
.sidenav-toggle-all button:hover {{ background:rgba(255,255,255,0.12); color:#F7F5F1; }}

/* ── Collapsible sections ── */
.collapsible-section {{ overflow:hidden; }}
.sec-toggle {{ display:flex; align-items:flex-end; justify-content:space-between; cursor:pointer; user-select:none; }}
.sec-toggle:hover .toggle-icon {{ color:var(--ink); }}
.toggle-icon {{ font-size:1.1rem; color:var(--muted); margin-bottom:0.8rem; flex-shrink:0; transition:transform 0.2s; }}
.collapsible-section.collapsed .toggle-icon {{ transform:rotate(-90deg); }}
.sec-body {{ transition:max-height 0.35s ease, opacity 0.25s ease; max-height:9999px; opacity:1; }}
.collapsible-section.collapsed .sec-body {{ max-height:0; opacity:0; overflow:hidden; }}

/* Header */
/* Layout — pure CSS, no JS needed */
:root {{ --nav-w: clamp(48px, 14vw, 220px); }}
.sidenav {{ width:var(--nav-w); transition:width 0.2s; overflow:hidden; }}
.hdr, .stats, .alert-banner, #main-wrap, .footer {{ margin-left:var(--nav-w); transition:margin-left 0.2s; }}
/* Hide labels when nav is narrow */
@media(max-width:1100px){{
  .sidenav-label,.sidenav-count,.sidenav-title,.sidenav-toggle-all{{display:none}}
  .nav-item{{justify-content:center;padding:0.5rem 0}}
}}
@media(max-width:700px){{
  :root{{--nav-w:0px}}
  .nav-burger{{display:flex}}
  .sidenav.nav-open{{width:200px}}
  .hdr,.stats,.alert-banner,#main-wrap,.footer{{margin-left:0}}
}}

.hdr {{ background: #161B22; color: #E6EDF3; border-bottom: 1px solid #21262D; padding: 2.5rem 3rem 2.2rem; position: relative; overflow: hidden; }}
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
.wrap {{ max-width:1400px; margin:0 auto; padding:2rem 2rem; display:flex; flex-direction:column; gap:3rem; }}

/* Section headers */
.sec-hdr {{ display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:1.25rem; padding-bottom:0.75rem; border-bottom:2px solid #30363D; }}
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
.card-name {{ font-family:'Fraunces',serif; font-size:1.05rem; font-weight:600; color:#E6EDF3; line-height:1.2; margin-top:0.15rem; }}
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
.acct-tbl thead tr {{ background:#1C2128; }}
.acct-tbl th {{ font-family:'Geist Mono',monospace; font-size:9.5px; letter-spacing:0.1em; text-transform:uppercase; color:var(--muted); padding:0.6rem 1rem; text-align:left; font-weight:500; border-bottom:1px solid var(--border); white-space:nowrap; }}
.acct-tbl td {{ padding:0.6rem 1rem; border-bottom:1px solid var(--border); vertical-align:middle; }}
.acct-tbl tr:last-child td {{ border-bottom:none; }}
.acct-tbl tr:hover td {{ background:#1C2128; }}
.tbl-name {{ font-weight:600; color:#E6EDF3; font-size:13px; }}
.tbl-region,.tbl-cse,.tbl-date,.tbl-exp {{ font-family:'Geist Mono',monospace; font-size:11px; color:#8B949E; white-space:nowrap; }}
.tbl-notes {{ max-width:340px; }}
.notes-text {{ font-size:12.5px; color:#E6EDF3; line-height:1.5; display:block; }}
.notes-none {{ font-size:11px; color:#6B7280; font-style:italic; font-family:'Geist Mono',monospace; }}
.no-owner-inline {{ font-family:'Geist Mono',monospace; font-size:10px; color:#DC2626; font-weight:700; letter-spacing:0.05em; }}
.xcheck-green {{ font-family:'Geist Mono',monospace; font-size:9px; color:#065F46; background:#DCFCE7; border:1px solid #86EFAC; padding:1px 5px; border-radius:3px; margin-top:3px; display:inline-block; cursor:help; }}
.xcheck-blocked {{ font-family:'Geist Mono',monospace; font-size:9px; color:#7F1D1D; background:#FEF2F2; border:1px solid #FCA5A5; padding:1px 5px; border-radius:3px; margin-top:3px; display:inline-block; cursor:help; }}
.xcheck-risk {{ font-family:'Geist Mono',monospace; font-size:9px; color:#92400E; background:#FEF3C7; border:1px solid #FCD34D; padding:1px 5px; border-radius:3px; margin-top:3px; display:inline-block; cursor:help; }}
.tooltip-wrap {{ position:relative; }}
.tooltip-text {{ display:none; position:absolute; left:0; top:calc(100% + 4px); z-index:999; background:#1A1209; color:#F7F5F1; font-family:'DM Sans',sans-serif; font-size:11px; line-height:1.45; padding:6px 10px; border-radius:6px; width:240px; white-space:normal; box-shadow:0 4px 16px rgba(0,0,0,0.25); pointer-events:none; }}
.tooltip-wrap:hover .tooltip-text {{ display:block; }}
.psc-shadow {{ color:var(--muted); font-size:10px; }}
.lf-icon {{ display:inline-flex; align-items:center; gap:3px; font-size:10px; font-family:'Geist Mono',monospace; font-weight:600; color:#F97316; background:rgba(249,115,22,0.12); border:1px solid rgba(249,115,22,0.3); padding:1px 5px; border-radius:4px; margin-left:5px; vertical-align:middle; white-space:nowrap; }}
.lf-dc {{ color:#FED7AA; font-weight:400; margin-left:3px; font-size:9px; }}
.cs-team-badge {{ font-family:'Geist Mono',monospace; font-size:9px; padding:1px 5px; border-radius:3px; background:#DBEAFE; color:#1D4ED8; border:1px solid #93C5FD; font-weight:600; }}
.named-badge {{ font-family:'Geist Mono',monospace; font-size:9px; padding:1px 5px; border-radius:3px; background:#F3F4F6; color:#6B7280; border:1px solid #D1D5DB; }}
.ms-done {{ color:#16A34A; font-size:13px; font-weight:700; }}
.ms-date {{ font-family:'Geist Mono',monospace; font-size:10px; color:var(--muted); }}
.ms-blank {{ color:#D1D5DB; }}
.ms-cat {{ font-family:'Geist Mono',monospace; font-size:9px; padding:1px 5px; border-radius:3px; background:#FEF3C7; color:#92400E; border:1px solid #FCD34D; }}
.signal-dot {{ font-size:14px; }}
.subtype-badge {{ font-family:'Geist Mono',monospace; font-size:9px; padding:2px 6px; border-radius:3px; border:1px solid; font-weight:700; letter-spacing:0.06em; display:inline-block; margin-bottom:3px; }}
.sd-text {{ font-size:11.5px; color:var(--muted); line-height:1.4; margin-top:2px; }}
.ai-field {{ font-size:13px; color:#E6EDF3; line-height:1.55; margin-bottom:6px; padding:4px 0; }}
.ai-field:last-child {{ margin-bottom:0; }}
.ai-label {{ font-family:'Geist Mono',monospace; font-size:9px; text-transform:uppercase; letter-spacing:0.12em; color:#5EEAD4; display:block; margin-bottom:3px; font-weight:600; }}
.ai-accountable {{ background:rgba(245,158,11,0.2); border-left:3px solid #F59E0B; padding:6px 10px; border-radius:0 5px 5px 0; }}
.ai-accountable .ai-label {{ color:#F59E0B; }}
.ai-accountable-value {{ color:#FDE68A; font-weight:700; font-size:13px; display:block; }}
.blocker-tags {{ display:flex; flex-wrap:wrap; gap:4px; margin-top:5px; }}
.blocker-tag {{ font-family:'Geist Mono',monospace; font-size:9.5px; padding:2px 6px; border-radius:3px; background:#FEF3C7; color:#92400E; border:1px solid #FCD34D; white-space:nowrap; }}
.status-chip {{ font-family:'Geist Mono',monospace; font-size:10px; font-weight:500; padding:2px 7px; border-radius:4px; border:1px solid; white-space:nowrap; }}
.done-chip {{ font-family:'Geist Mono',monospace; font-size:11px; color:#15803D; background:#F0FDF4; border:1px solid #86EFAC; padding:3px 8px; border-radius:4px; white-space:nowrap; }}

.empty {{ grid-column:1/-1; text-align:center; padding:5rem; font-family:'Fraunces',serif; font-size:1.1rem; font-style:italic; color:var(--muted); }}
.empty-sm {{ padding:2rem; text-align:center; font-family:'Fraunces',serif; font-style:italic; color:var(--muted); font-size:1rem; }}

/* Weekly view */
.weekly-grid {{ display:grid; gap:0.5rem; width:100%; overflow:hidden; }}
.week-col {{ min-width:0; border:1px solid var(--border); border-radius:8px; overflow:hidden; background:var(--card); }}
.week-col-current {{ border-color:#3B82F6; box-shadow:0 0 0 2px #BFDBFE; }}
.week-header-current {{ background:#1D4ED8; color:#fff; padding:0.6rem 0.75rem; }}
.week-header-past {{ background:#F2EFE9; color:var(--muted); padding:0.6rem 0.75rem; }}
.week-header-future {{ background:var(--ink); color:#F7F5F1; padding:0.6rem 0.75rem; }}
.week-label {{ font-family:'Fraunces',serif; font-size:0.85rem; font-weight:600; }}
.week-badges {{ display:flex; flex-wrap:wrap; gap:3px; margin-top:4px; }}
.week-badge-done {{ font-family:'Geist Mono',monospace; font-size:9px; padding:1px 5px; border-radius:3px; background:#DCFCE7; color:#15803D; }}
.week-badge-planned {{ font-family:'Geist Mono',monospace; font-size:9px; padding:1px 5px; border-radius:3px; background:#DBEAFE; color:#1D4ED8; }}
.week-badge-m8 {{ font-family:'Geist Mono',monospace; font-size:9px; padding:1px 5px; border-radius:3px; background:#FEF3C7; color:#92400E; }}
.week-body {{ padding:0.5rem 0.6rem; display:flex; flex-direction:column; gap:3px; max-height:320px; overflow-y:auto; }}
.week-row {{ font-size:11px; line-height:1.35; padding:3px 5px; border-radius:4px; display:flex; flex-direction:column; }}
.week-done {{ background:#F0FDF4; color:#15803D; font-weight:600; }}
.week-m9 {{ background:#EFF6FF; color:#1D4ED8; }}
.week-m8 {{ background:#FFFBEB; color:#92400E; }}
.week-cse {{ font-family:'Geist Mono',monospace; font-size:9px; color:var(--muted); margin-top:1px; }}
.week-status {{ font-family:'Geist Mono',monospace; font-size:8.5px; color:var(--muted); opacity:.7; }}
.week-empty {{ font-size:10px; color:#C5BFB5; font-style:italic; padding:4px; }}

/* Alert Banner */
.alert-banner {{ display:flex; justify-content:space-between; align-items:flex-start; background:#450A0A; color:#FEF2F2; padding:1rem 2rem; gap:1rem; border-bottom:3px solid #DC2626; border-top:1px solid #7F1D1D; }}
.alert-left {{ display:flex; align-items:flex-start; gap:1rem; width:100%; }}
.alert-icon {{ font-family:'Fraunces',serif; font-size:1.6rem; font-weight:700; color:#F87171; flex-shrink:0; line-height:1; margin-top:2px; }}
.alert-title {{ font-weight:700; font-size:13px; margin-bottom:0.5rem; color:#FECACA; letter-spacing:0.01em; }}
.alert-body {{ display:flex; flex-wrap:wrap; gap:0.4rem; }}
.alert-item {{ display:flex; flex-direction:column; background:rgba(220,38,38,0.15); border:1px solid rgba(248,113,113,0.3); border-radius:5px; padding:0.35rem 0.65rem; min-width:140px; }}
.alert-acct {{ font-size:12px; font-weight:600; color:#FEF2F2 !important; }}
.alert-owner {{ font-family:'Geist Mono',monospace; font-size:9.5px; color:#FCA5A5 !important; margin-top:2px; }}
.alert-no-owner {{ color:#F87171 !important; font-weight:700; letter-spacing:0.05em; }}
.alert-close {{ background:none; border:none; color:#FCA5A5; font-size:1.1rem; cursor:pointer; padding:0.25rem 0.5rem; flex-shrink:0; line-height:1; opacity:0.7; }}
.alert-close:hover {{ opacity:1; }}
.dq-group {{ margin-top:0.75rem; padding-top:0.75rem; border-top:1px solid rgba(248,113,113,0.25); }}
.dq-group:first-child {{ margin-top:0.4rem; padding-top:0; border-top:none; }}
.dq-group-title {{ font-size:11.5px; font-weight:700; color:#FECACA; margin-bottom:0.4rem; }}
.dq-count {{ display:inline-block; font-family:'Fraunces',serif; font-size:1.1rem; font-weight:700; color:#F87171; margin-right:0.4rem; line-height:1; }}
.dq-desc {{ font-weight:400; color:#FCA5A5; font-style:italic; }}

/* Chart */
.chart-wrap {{ display:grid; grid-template-columns:280px 1fr; gap:2rem; align-items:center; width:100%; }}
.chart-canvas-wrap {{ position:relative; width:280px; height:280px; }}
.chart-centre {{ position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); text-align:center; pointer-events:none; }}
.chart-centre-n {{ font-family:'Fraunces',serif; font-size:2.2rem; font-weight:700; color:var(--text); line-height:1; }}
.chart-centre-l {{ font-family:'Geist Mono',monospace; font-size:9px; letter-spacing:0.14em; text-transform:uppercase; color:var(--muted); }}
.chart-table-wrap {{ overflow-x:auto; min-width:0; }}
.chart-tbl {{ width:100%; border-collapse:collapse; }}
.chart-tbl th {{ font-family:'Geist Mono',monospace; font-size:9px; letter-spacing:0.1em; text-transform:uppercase; color:var(--muted); padding:0.4rem 0.75rem; text-align:left; border-bottom:1px solid var(--border); }}
.chart-tbl td {{ padding:0.35rem 0.75rem; font-size:12.5px; border-bottom:1px solid var(--border); vertical-align:middle; }}
.chart-tbl tr:last-child td {{ border-bottom:none; }}
.chart-tbl tr:hover td {{ background:#1C2128; }}
.chart-dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:7px; flex-shrink:0; vertical-align:middle; }}
.chart-count {{ font-family:'Fraunces',serif; font-size:1rem; font-weight:600; text-align:right; width:50px; }}
.chart-pct {{ font-family:'Geist Mono',monospace; font-size:11px; color:var(--muted); text-align:right; width:50px; }}
.chart-row-link {{ cursor:pointer; }}
.chart-row-link:hover td {{ background:#F0EDE6; }}
.chart-row-plain {{ cursor:default; }}
.chart-arrow {{ font-size:10px; color:var(--muted); margin-left:4px; }}

/* Footer */
.footer {{ text-align:center; padding:1.8rem; font-family:'Geist Mono',monospace; font-size:9.5px; letter-spacing:0.14em; text-transform:uppercase; color:#C5BFB5; border-top:1px solid var(--border); margin-top:1rem; }}

.nav-burger {{ display:none; position:fixed; top:1rem; left:1rem; z-index:200; background:var(--ink); border:none; color:#8A9BB0; font-size:1.2rem; width:36px; height:36px; border-radius:6px; cursor:pointer; align-items:center; justify-content:center; }}
@media (max-width:900px) {{
  .nav-burger {{ display:flex; }}
  .sidenav {{ width:0; overflow:hidden; }}
  .sidenav.nav-open {{ width:200px; }}
  .hdr, .stats, .alert-banner, #main-wrap, .footer {{ margin-left:0; }}
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

<button class="nav-burger" onclick="toggleNav()" title="Toggle navigation">☰</button>

<!-- Side Navigation -->
<nav class="sidenav" id="sidenav">
  <div class="sidenav-inner">
    <div class="sidenav-title">SECTIONS</div>
    <a class="sidenav-item" href="#section-weekly"   onclick="expandSection('section-weekly')">
      <span class="sidenav-dot"></span><span class="sidenav-label">Weekly Tracker</span><span class="sidenav-count">{n_weeks}w</span>
    </a>
    <a class="sidenav-item" href="#section-overview" onclick="expandSection('section-overview')">
      <span class="sidenav-dot"></span><span class="sidenav-label">Status Overview</span><span class="sidenav-count">{total_accounts}</span>
    </a>
    <a class="sidenav-item" href="#section-tasks"    onclick="expandSection('section-tasks')">
      <span class="sidenav-dot"></span><span class="sidenav-label">Approved Tasks</span><span class="sidenav-count">{total_tasks}</span>
    </a>
    <a class="sidenav-item" href="#section-todo"     onclick="expandSection('section-todo')">
      <span class="sidenav-dot"></span><span class="sidenav-label">Open Actions</span><span class="sidenav-count">{n_action}</span>
    </a>
    <a class="sidenav-item" href="#section-stalls"   onclick="expandSection('section-stalls')">
      <span class="sidenav-dot"></span><span class="sidenav-label">Milestone Stalls</span><span class="sidenav-count">{n_stalls}</span>
    </a>
    <a class="sidenav-item" href="#section-ps"       onclick="expandSection('section-ps')">
      <span class="sidenav-dot"></span><span class="sidenav-label">PS Engagement</span><span class="sidenav-count">{n_ps}</span>
    </a>
    <a class="sidenav-item" href="#section-milestones" onclick="expandSection('section-milestones')">
      <span class="sidenav-dot"></span><span class="sidenav-label">Milestone Tracker</span><span class="sidenav-count">{n_milestone}</span>
    </a>
    <a class="sidenav-item" href="#section-history" onclick="expandSection('section-history')">
      <span class="sidenav-dot"></span><span class="sidenav-label">Status History</span><span class="sidenav-count" id="nb-history">{n_history}</span>
    </a>
    <a class="sidenav-item" href="#section-completed" onclick="expandSection('section-completed')">
      <span class="sidenav-dot"></span><span class="sidenav-label">Completed</span><span class="sidenav-count">{n_completed}</span>
    </a>
    <div class="sidenav-toggle-all">
      <button onclick="toggleAll(true)">Expand all</button>
      <button onclick="toggleAll(false)">Collapse all</button>
    </div>
  </div>
</nav>

<div class="wrap" id="main-wrap">

  <section id="section-weekly" class="collapsible-section">
    <div class="sec-toggle" onclick="toggleSection('section-weekly')">
      {_section_header("Weekly Tracker", "M8 / M9 milestones by North America week · 4 weeks back · current · 6 weeks ahead", n_weeks)}
      <span class="toggle-icon">▾</span>
    </div>
    <div class="sec-body">{weekly_html}</div>
  </section>

  <section id="section-overview" class="collapsible-section">
    <div class="sec-toggle" onclick="toggleSection('section-overview')">
      {_section_header("Status Overview", "Distribution of all EMEA accounts by current migration status", total_accounts)}
      <span class="toggle-icon">▾</span>
    </div>
    <div class="sec-body">{status_chart}</div>
  </section>

  <section id="section-tasks" class="collapsible-section">
    <div class="sec-toggle" onclick="toggleSection('section-tasks')">
      {_section_header("Approved Tasks", "Actions reviewed and approved in this session", total_tasks)}
      <span class="toggle-icon">▾</span>
    </div>
    <div class="sec-body"><div class="grid">{task_cards}</div></div>
  </section>

  <section id="section-todo" class="collapsible-section">
    <div class="sec-toggle" onclick="toggleSection('section-todo')">
      {_section_header("Open Actions", "Accounts requiring follow-up based on current status", n_action)}
      <span class="toggle-icon">▾</span>
    </div>
    <div class="sec-body">{action_html if action_html else '<div class="empty-sm">No action items detected.</div>'}</div>
  </section>

  <section id="section-stalls" class="collapsible-section">
    <div class="sec-toggle" onclick="toggleSection('section-stalls')">
      {_section_header("Milestone Stalls", "Scale cohort accounts exceeding M3→M8 (14d) or M8→M9 (28d) limits · effective 09 Mar 2026", n_stalls)}
      <span class="toggle-icon">▾</span>
    </div>
    <div class="sec-body">{stall_html}</div>
  </section>

  <section id="section-ps" class="collapsible-section">
    <div class="sec-toggle" onclick="toggleSection('section-ps')">
      {_section_header("PS Engagement", f"Professional Services assignments · {n_ps} accounts matched · PSC = PS Consultant", n_ps)}
      <span class="toggle-icon">▾</span>
    </div>
    <div class="sec-body">{ps_html}{_ps_unmatched_section()}</div>
  </section>

  <section id="section-milestones" class="collapsible-section">
    <div class="sec-toggle" onclick="toggleSection('section-milestones')">
      {_section_header("Milestone Tracker", f"M3 / M8 / M9 progress · {n_milestone} accounts · CS team + Named · Core Rep Blocking flagged first", n_milestone)}
      <span class="toggle-icon">▾</span>
    </div>
    <div class="sec-body">{milestone_html}</div>
  </section>

  <section id="section-history" class="collapsible-section">
    <div class="sec-toggle" onclick="toggleSection('section-history')">
      {_section_header("Status History", "Status changes per account — tracked by pipeline", n_history)}
      <span class="toggle-icon">▾</span>
    </div>
    <div class="sec-body">{history_html}</div>
  </section>

  <section id="section-completed" class="collapsible-section">
    <div class="sec-toggle" onclick="toggleSection('section-completed')">
      {_section_header("Completed", "Accounts that reached Completed status — migration done", n_completed)}
      <span class="toggle-icon">▾</span>
    </div>
    <div class="sec-body">{completed_html}</div>
  </section>

</div>

<footer class="footer">
  Solstice Agent · EMEA CC Migration · {generated_at}
</footer>

<script>
// ── Collapse / Expand ────────────────────────────────────────────
function toggleSection(id) {{
  var sec = document.getElementById(id);
  var body = sec.querySelector('.sec-body');
  var icon = sec.querySelector('.toggle-icon');
  var collapsed = sec.classList.toggle('collapsed');
  icon.textContent = collapsed ? '▸' : '▾';
}}

function expandSection(id) {{
  var sec = document.getElementById(id);
  if (sec && sec.classList.contains('collapsed')) {{
    sec.classList.remove('collapsed');
    sec.querySelector('.toggle-icon').textContent = '▾';
  }}
}}

function toggleAll(expand) {{
  document.querySelectorAll('.collapsible-section').forEach(function(sec) {{
    var body = sec.querySelector('.sec-body');
    var icon = sec.querySelector('.toggle-icon');
    if (expand) {{ sec.classList.remove('collapsed'); icon.textContent = '▾'; }}
    else        {{ sec.classList.add('collapsed');    icon.textContent = '▸'; }}
  }});
}}

// ── Hamburger toggle (mobile) ────────────────────────────────────
function toggleNav() {{
  document.getElementById('sidenav').classList.toggle('nav-open');
}}

// CSS handles all responsive behaviour via clamp(48px, 14vw, 220px)

// ── Active nav item via IntersectionObserver ─────────────────────
var sections = document.querySelectorAll('.collapsible-section');
var navItems = document.querySelectorAll('.sidenav-item');

var observer = new IntersectionObserver(function(entries) {{
  entries.forEach(function(entry) {{
    if (entry.isIntersecting) {{
      var id = entry.target.id;
      navItems.forEach(function(a) {{
        a.classList.toggle('sidenav-active', a.getAttribute('href') === '#' + id);
      }});
    }}
  }});
}}, {{ rootMargin: '-20% 0px -70% 0px', threshold: 0 }});

sections.forEach(function(s) {{ observer.observe(s); }});
</script>

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
