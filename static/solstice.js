/**
 * solstice.js — Shared design system for Solstice pages.
 * All public functions on window.S namespace.
 *
 * Each page includes:
 *   <link rel="stylesheet" href="/static/solstice.css">
 *   <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
 *   <script src="/static/solstice.js"></script>
 *   <script>S.initNav('pageid'); S.restoreCard();</script>
 */
(function(S) {
'use strict';

// ── Pure functions ────────────────────────────────────────────────────────────

/**
 * slaCountdown — SLA window status for an account.
 * @param {string|null} m3_actual   M3 completion date (YYYY-MM-DD)
 * @param {string|null} m8_planned  M8 planned date
 * @param {string|null} m8_actual   M8 actual start (null = not started)
 * @param {string|null} m9_planned  M9 planned date
 * @param {string|null} m9_actual   M9 actual date (null = not complete)
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
    return { label:'M3\u2192M8', daysLeft, limit:14, status };
  }
  if (m8_actual && !m9_actual && m9_planned) {
    const m9p = _d(m9_planned); if (!m9p) return null;
    const daysLeft = _days(today, m9p);
    const used = _days(_d(m8_actual), m9p);
    const status = daysLeft < 0 ? 'red' : daysLeft <= 3 ? 'amber' : used > 28 ? 'red' : 'green';
    return { label:'M8\u2192M9', daysLeft, limit:28, status };
  }
  return null;
};

S.slaCountdownHTML = function(m3_actual, m8_planned, m8_actual, m9_planned, m9_actual) {
  const r = S.slaCountdown(m3_actual, m8_planned, m8_actual, m9_planned, m9_actual);
  if (!r) return '';
  const cls = r.status==='red'?'badge-red':r.status==='amber'?'badge-amber':'badge-green';
  const lbl = r.daysLeft<0?r.label+' OVERDUE '+Math.abs(r.daysLeft)+'d':r.label+' '+r.daysLeft+'d left';
  return '<span class="badge '+cls+'" title="SLA limit: '+r.limit+' days">'+lbl+'</span>';
};

/**
 * blockerAge — days since account became blocked.
 * @param {string|null} signalDate ISO date
 * @returns {{days,status}|null}
 */
S.blockerAge = function(signalDate) {
  if (!signalDate) return null;
  const d = new Date(signalDate); d.setHours(0,0,0,0);
  const today = new Date(); today.setHours(0,0,0,0);
  const days = Math.round((today-d)/(1000*60*60*24));
  if (days<0) return null;
  return { days, status: days<7?'green':days<=21?'amber':'red' };
};

S.blockerAgeHTML = function(signalDate) {
  const r = S.blockerAge(signalDate);
  if (!r) return '';
  const cls = r.status==='red'?'badge-red':r.status==='amber'?'badge-amber':'badge-green';
  return '<span class="badge '+cls+'">\u23f1 '+r.days+'d blocked</span>';
};

/**
 * exportCSV — client-side CSV download.
 * @param {Object[]} rows
 * @param {string} filename
 */
S.exportCSV = function(rows, filename) {
  if (!rows||!rows.length) return;
  const headers = Object.keys(rows[0]);
  const lines = [headers.join(',')];
  for (const row of rows) {
    lines.push(headers.map(function(h) {
      const v = row[h]==null?'':String(row[h]);
      return v.includes(',')||v.includes('"')||v.includes('\n')
        ?'"'+v.replace(/"/g,'""')+'"':v;
    }).join(','));
  }
  const blob = new Blob([lines.join('\n')],{type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename||'export.csv';
  a.click();
  URL.revokeObjectURL(a.href);
};

// ── HTML escaping ─────────────────────────────────────────────────────────────

function _esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
S.esc = _esc;

// ── Global search ─────────────────────────────────────────────────────────────

S.gSearch = function(q) {
  var dd = document.getElementById('g-dropdown');
  if (!dd) return;
  if (!q||q.length<2) { dd.style.display='none'; return; }
  fetch('/api/customer-search?q='+encodeURIComponent(q))
    .then(function(r){return r.json();})
    .then(function(data) {
      if (!data.length) { dd.style.display='none'; return; }
      var SC = {green:'#10b981',blocked:'#ef4444',at_risk:'#f59e0b'};
      dd.innerHTML = data.map(function(a) {
        var sc = SC[a.signal]||'#475569';
        var aid = (a.account_id||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'");
        return '<div onclick="S.openAccountCard(\''+aid+'\')" style="padding:.5rem .8rem;cursor:pointer;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:.5rem" onmouseover="this.style.background=\'var(--surface-2)\'" onmouseout="this.style.background=\'\'">'
          +'<span style="width:6px;height:6px;border-radius:50%;background:'+sc+';flex-shrink:0;display:inline-block"></span>'
          +'<div><div style="font-size:10px;font-weight:700;color:var(--text)">'+_esc(a.customer_name)+'</div>'
          +'<div style="font-size:8px;color:var(--muted)">'+_esc(a.active_cse||'\u2014')+' \u00b7 '+_esc(a.sales_region||'\u2014')+'</div></div></div>';
      }).join('');
      dd.style.display='block';
    }).catch(function(){ dd.style.display='none'; });
};

S.closeSearch = function() {
  setTimeout(function() {
    var dd = document.getElementById('g-dropdown');
    if (dd) dd.style.display='none';
  }, 200);
};

// ── Account modal ─────────────────────────────────────────────────────────────

S.openAccountCard = function(account_id) {
  if (!account_id) return;
  localStorage.setItem('lastGCard', account_id);
  fetch('/api/customer/'+encodeURIComponent(account_id))
    .then(function(r){return r.json();})
    .then(function(d){ if (!d.error && !d.detail) _renderCard(d); })
    .catch(function(){});
};

S.closeCard = function() {
  var m = document.getElementById('s-modal');
  if (m) m.remove();
  localStorage.removeItem('lastGCard');
};

S.restoreCard = function() {
  var id = localStorage.getItem('lastGCard');
  if (id) S.openAccountCard(id);
};

function _renderCard(d) {
  var existing = document.getElementById('s-modal');
  if (existing) existing.remove();

  var slaHtml = S.slaCountdownHTML(d.m3_actual, d.m3_planned, d.m8_actual, d.m8_planned, d.m9_actual);
  var ageHtml = (d.signal==='blocked'||d.signal==='at_risk') ? S.blockerAgeHTML(d.status_changed_at) : '';

  var milestones = [
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

  var msBar = milestones.map(function(m) {
    var col = m.done?'#10b981':'#1e2d40';
    var txt = m.done?'#10b981':'#475569';
    return '<div style="flex:1;text-align:center">'
      +'<div style="width:100%;height:4px;background:'+col+';border-radius:2px;margin-bottom:4px"></div>'
      +'<div style="font-size:8px;color:'+txt+';font-family:monospace">'+m.label+'</div>'
      +(m.date?'<div style="font-size:7px;color:#334155">'+String(m.date).slice(0,10)+'</div>':'')
      +'</div>';
  }).join('<div style="width:2px"></div>');

  var hist = (d.history||[]).slice(0,10).map(function(h) {
    return '<div style="font-size:9px;color:#475569;padding:4px 0;border-bottom:1px solid #1e2d40">'
      +'<span style="color:#e2e8f0">'+_esc(h.field_name||'status')+'</span>'
      +' <span style="color:#475569">'+_esc(h.old_status||'\u2014')+' \u2192 </span>'
      +'<span style="color:#22d3ee">'+_esc(h.new_status||'\u2014')+'</span>'
      +'<span style="float:right">'+String(h.changed_at||'').slice(0,10)+'</span>'
      +'</div>';
  }).join('');

  var signalCls = d.signal==='green'?'badge-green':d.signal==='blocked'?'badge-red':'badge-amber';

  var modal = document.createElement('div');
  modal.id = 's-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
  modal.innerHTML = '<div style="background:#0f1729;border:1px solid #1e2d40;border-radius:8px;width:100%;max-width:680px;max-height:90vh;overflow-y:auto;padding:24px;position:relative">'
    +'<button onclick="S.closeCard()" style="position:absolute;top:16px;right:16px;background:none;border:none;color:#475569;font-size:18px;cursor:pointer">\u00d7</button>'
    +'<div style="margin-bottom:16px">'
    +'<div style="font-size:16px;font-weight:700;color:#f0f6fc;margin-bottom:6px">'+_esc(d.customer_name||'')+'</div>'
    +'<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">'
    +'<span style="font-size:11px;color:#475569">'+_esc(d.account_theatre||'EMEA')+' \u00b7 '+_esc(d.sales_region||'')+' \u00b7 '+_esc(d.active_cse||'\u2014')+'</span>'
    +(d.signal?'<span class="badge '+signalCls+'">'+_esc(d.signal)+'</span>':'')
    +(d.churn_risk?'<span class="badge badge-amber">churn risk</span>':'')
    +(d.live_fire?'<span class="badge badge-red">live-fire</span>':'')
    +slaHtml+ageHtml
    +'</div></div>'
    +'<div style="margin-bottom:16px">'
    +'<div style="font-size:9px;color:#475569;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px">Milestones</div>'
    +'<div style="display:flex;align-items:flex-start">'+msBar+'</div>'
    +'</div>'
    +'<div style="background:#0a0e1a;border:1px solid #1e2d40;border-radius:6px;padding:12px;margin-bottom:12px">'
    +'<div style="font-size:9px;color:#22d3ee;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px">Call Prep</div>'
    +'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:10px">'
    +'<div><span style="color:#475569">Last contact</span><br><span style="color:#e2e8f0">'+_esc(d.email_sent||'\u2014')+'</span></div>'
    +'<div><span style="color:#475569">Owner E2E</span><br><span style="color:#e2e8f0">'+_esc(d.owner_e2e||'\u2014')+'</span></div>'
    +'<div><span style="color:#475569">DC Progress</span><br><span style="color:#e2e8f0">'+_esc(d.dc_progress||'\u2014')+'</span></div>'
    +'<div><span style="color:#475569">Churn risk</span><br><span style="color:#e2e8f0">'+_esc(d.churn_risk||'\u2014')+'</span></div>'
    +'</div>'
    +(d.health_notes?'<div style="margin-top:8px;font-size:10px;color:#94a3b8;border-top:1px solid #1e2d40;padding-top:8px">'+_esc(d.health_notes)+'</div>':'')
    +(d.upgrade_notes?'<div style="margin-top:4px;font-size:10px;color:#94a3b8">'+_esc(d.upgrade_notes)+'</div>':'')
    +'</div>'
    +(d.psc?'<div style="background:#0a0e1a;border:1px solid #1e2d40;border-radius:6px;padding:12px;margin-bottom:12px">'
    +'<div style="font-size:9px;color:#22d3ee;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px">PS Engagement</div>'
    +'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:10px">'
    +'<div><span style="color:#475569">PSC</span><br><span style="color:#e2e8f0">'+_esc(d.psc)+'</span></div>'
    +'<div><span style="color:#475569">PM</span><br><span style="color:#e2e8f0">'+_esc(d.pm||'\u2014')+'</span></div>'
    +'<div><span style="color:#475569">Status</span><br><span style="color:#e2e8f0">'+_esc(d.ps_status||'\u2014')+'</span></div>'
    +'<div><span style="color:#475569">Clarizen</span><br><span style="color:#e2e8f0">'+_esc(d.clarizen_id||'\u2014')+'</span></div>'
    +'</div></div>':'')
    +(hist?'<div style="background:#0a0e1a;border:1px solid #1e2d40;border-radius:6px;padding:12px">'
    +'<div style="font-size:9px;color:#22d3ee;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px">Recent History</div>'
    +hist+'</div>':'')
    +'</div>';

  modal.addEventListener('click', function(e){ if(e.target===modal) S.closeCard(); });
  document.body.appendChild(modal);
}

// ── Nav + Health Bar ──────────────────────────────────────────────────────────

var _PAGES = [
  {id:'ops',     label:'Ops',      url:'/ops'},
  {id:'blockers',label:'Blockers', url:'/blockers'},
  {id:'forecast',label:'Forecast', url:'/forecast'},
  {id:'daily',   label:'Daily',    url:'/daily'},
  {id:'audit',   label:'Audit',    url:'/audit'},
  {id:'cse',     label:'CSE',      url:'/cse'},
  {id:'weekly',  label:'Weekly',   url:'/weekly'},
];

S.initNav = function(activePage) {
  var nav = document.getElementById('s-nav');
  if (!nav) return;
  var links = _PAGES.map(function(p) {
    var active = p.id === activePage;
    return '<a href="' + p.url + '" style="'
      + 'font-family:\'Plus Jakarta Sans\',system-ui,sans-serif;'
      + 'font-size:12px;font-weight:' + (active ? '600' : '500') + ';'
      + 'color:' + (active ? '#ffffff' : 'rgba(255,255,255,.45)') + ';'
      + 'text-decoration:none;'
      + 'height:44px;display:flex;align-items:center;padding:0 14px;'
      + 'border-bottom:2px solid ' + (active ? '#0ea5e9' : 'transparent') + ';'
      + 'transition:color .15s;'
      + '">' + p.label + '</a>';
  }).join('');

  nav.innerHTML = '<div style="display:flex;align-items:center;gap:0;flex:1">'
    + '<div style="display:flex;align-items:center;gap:8px;padding-right:20px;margin-right:4px;border-right:1px solid rgba(255,255,255,.1)">'
    + '<div style="width:22px;height:22px;background:#0ea5e9;border-radius:5px;display:flex;align-items:center;justify-content:center;font-size:12px;flex-shrink:0">&#9728;</div>'
    + '<span style="font-family:\'Plus Jakarta Sans\',system-ui;font-size:13px;font-weight:700;color:white;letter-spacing:-.2px">Solstice</span>'
    + '</div>'
    + '<div style="display:flex;gap:0">' + links + '</div>'
    + '</div>'
    + '<div id="s-health" style="display:flex;gap:8px;align-items:center"></div>'
    + '<div style="position:relative;margin-left:12px">'
    + '<input id="g-search" type="text" placeholder="&#9013; Account..." autocomplete="off"'
    + ' style="background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:6px;color:white;font-size:10px;padding:.28rem .65rem;width:150px;outline:none;transition:width .2s;font-family:\'Plus Jakarta Sans\',system-ui"'
    + ' oninput="S.gSearch(this.value)" onfocus="this.style.width=\'210px\'" onblur="S.closeSearch();setTimeout(function(){var e=document.getElementById(\'g-search\');if(e)e.style.width=\'150px\'},200)">'
    + '<div id="g-dropdown" style="display:none;position:absolute;top:calc(100% + 4px);right:0;width:280px;background:white;border:1px solid #e2e8f0;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.12);z-index:1000;max-height:320px;overflow-y:auto"></div>'
    + '</div>';

  _refreshHealth();
  setInterval(_refreshHealth, 5*60*1000);
};

function _refreshHealth() {
  fetch('/api/health-summary')
    .then(function(r){return r.json();})
    .then(function(data) {
      var el = document.getElementById('s-health');
      if (!el) return;
      var icons = {green:'\ud83d\udfe2',amber:'\ud83d\udfe1',red:'\ud83d\udd34'};
      el.innerHTML = Object.keys(data).map(function(t) {
        var v = data[t];
        return '<span title="'+t+': '+v.m9+' M9 \u00b7 '+v.blocked+' blocked" style="font-size:10px;cursor:default">'+(icons[v.status]||'\u26aa')+' <span style="color:#94a3b8;font-size:9px">'+t+'</span></span>';
      }).join('');
    }).catch(function(){});
}

// ── Sync Summary Toast ────────────────────────────────────────────────────────

S.syncSummary = function(events) {
  var existing = document.getElementById('s-toast');
  if (existing) existing.remove();
  if (!events) return;
  var parts = [];
  if (events.m9>0) parts.push('+'+events.m9+' M9');
  if (events.blocked>0) parts.push(events.blocked+' newly blocked');
  if (events.resolved>0) parts.push(events.resolved+' resolved');
  if (!parts.length) return;
  var toast = document.createElement('div');
  toast.id = 's-toast';
  toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#0f1729;border:1px solid #22d3ee;border-radius:6px;padding:12px 16px;font-size:11px;color:#e2e8f0;z-index:8888;display:flex;gap:12px;align-items:center;box-shadow:0 4px 12px rgba(0,0,0,.4)';
  toast.innerHTML = '<span style="color:#22d3ee">\u26a1 Sync</span> '+parts.join(' \u00b7 ')+' <button onclick="this.parentElement.remove()" style="background:none;border:none;color:#475569;cursor:pointer;font-size:14px;margin-left:4px">\u00d7</button>';
  document.body.appendChild(toast);
  setTimeout(function(){ var t=document.getElementById('s-toast'); if(t) t.remove(); }, 8000);
};

})(window.S = window.S || {});
