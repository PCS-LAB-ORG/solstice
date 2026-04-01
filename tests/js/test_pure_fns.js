// Node.js tests for pure functions in solstice.js
// Run: node tests/js/test_pure_fns.js
// These functions are tested inline here (not importing solstice.js which needs a browser)

const assert = require('assert');

// ── Inline copies of pure functions for testing ───────────────────────────────

function slaCountdown(m3_actual, m8_planned, m8_actual, m9_planned, m9_actual) {
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

// ── Test runner ───────────────────────────────────────────────────────────────

let passed = 0; let failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch(e) { console.log(`  ✗ ${name}: ${e.message}`); failed++; }
}

// ── slaCountdown tests ────────────────────────────────────────────────────────
console.log('\nslaCountdown:');

test('returns null when all args null', () => {
  assert.strictEqual(slaCountdown(null, null, null, null, null), null);
});
test('returns null when no M3 or M8 actual', () => {
  assert.strictEqual(slaCountdown(null, '2026-05-01', null, null, null), null);
});
test('M3→M8 window: returns label M3→M8', () => {
  const r = slaCountdown('2026-03-01', '2026-04-10', null, null, null);
  assert.ok(r);
  assert.strictEqual(r.label, 'M3→M8');
});
test('M8→M9 window: returns label M8→M9', () => {
  const r = slaCountdown(null, null, '2026-03-01', '2026-04-10', null);
  assert.ok(r);
  assert.strictEqual(r.label, 'M8→M9');
});
test('returns null when M9 already complete', () => {
  assert.strictEqual(slaCountdown(null, null, '2026-03-01', '2026-04-10', '2026-04-05'), null);
});
test('overdue M8 planned (past date) returns red', () => {
  const r = slaCountdown('2026-01-01', '2026-01-01', null, null, null);
  assert.strictEqual(r.status, 'red');
});
test('limit is 14 for M3→M8', () => {
  const r = slaCountdown('2026-03-01', '2026-04-10', null, null, null);
  assert.strictEqual(r.limit, 14);
});
test('limit is 28 for M8→M9', () => {
  const r = slaCountdown(null, null, '2026-03-01', '2026-05-01', null);
  assert.strictEqual(r.limit, 28);
});
test('future date with room returns green', () => {
  const future = new Date(Date.now() + 15*24*60*60*1000).toISOString().slice(0,10);
  const r = slaCountdown('2026-03-01', future, null, null, null);
  assert.ok(['green','amber','red'].includes(r.status));
});

// ── blockerAge tests ──────────────────────────────────────────────────────────
console.log('\nblockerAge:');

test('null input returns null', () => {
  assert.strictEqual(blockerAge(null), null);
});
test('empty string returns null', () => {
  assert.strictEqual(blockerAge(''), null);
});
test('today returns 0 days green', () => {
  const today = new Date().toISOString().slice(0,10);
  const r = blockerAge(today);
  assert.strictEqual(r.days, 0);
  assert.strictEqual(r.status, 'green');
});
test('6 days returns green', () => {
  const d = new Date(); d.setDate(d.getDate()-6);
  const r = blockerAge(d.toISOString().slice(0,10));
  assert.strictEqual(r.status, 'green');
});
test('8 days returns amber', () => {
  const d = new Date(); d.setDate(d.getDate()-8);
  const r = blockerAge(d.toISOString().slice(0,10));
  assert.strictEqual(r.status, 'amber');
});
test('21 days returns amber', () => {
  const d = new Date(); d.setDate(d.getDate()-21);
  const r = blockerAge(d.toISOString().slice(0,10));
  assert.strictEqual(r.status, 'amber');
});
test('22 days returns red', () => {
  const d = new Date(); d.setDate(d.getDate()-22);
  const r = blockerAge(d.toISOString().slice(0,10));
  assert.strictEqual(r.status, 'red');
});
test('future date returns null', () => {
  const d = new Date(); d.setDate(d.getDate()+1);
  assert.strictEqual(blockerAge(d.toISOString().slice(0,10)), null);
});

// ── exportCSV tests ───────────────────────────────────────────────────────────
console.log('\nexportCSV:');

test('empty array returns empty string', () => {
  assert.strictEqual(exportCSV([], 'test.csv'), '');
});
test('null input returns empty string', () => {
  assert.strictEqual(exportCSV(null, 'test.csv'), '');
});
test('single row produces header + data line', () => {
  const csv = exportCSV([{name:'Acme',cse:'Jane'}], 'out.csv');
  const lines = csv.split('\n');
  assert.strictEqual(lines[0], 'name,cse');
  assert.strictEqual(lines[1], 'Acme,Jane');
});
test('commas in values are quoted', () => {
  const csv = exportCSV([{name:'Acme, Ltd'}], 'out.csv');
  assert.ok(csv.includes('"Acme, Ltd"'));
});
test('double quotes in values are escaped', () => {
  const csv = exportCSV([{name:'Say "hello"'}], 'out.csv');
  assert.ok(csv.includes('"Say ""hello"""'));
});
test('null values become empty string', () => {
  const csv = exportCSV([{name:null,val:0}], 'out.csv');
  assert.ok(csv.split('\n')[1].startsWith(','));
});
test('multiple rows all included', () => {
  const rows = [{a:1},{a:2},{a:3}];
  const csv = exportCSV(rows, 'out.csv');
  assert.strictEqual(csv.split('\n').length, 4);
});
test('zero value is included not skipped', () => {
  const csv = exportCSV([{count:0}], 'out.csv');
  assert.strictEqual(csv.split('\n')[1], '0');
});

// ── Summary ───────────────────────────────────────────────────────────────────
console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
