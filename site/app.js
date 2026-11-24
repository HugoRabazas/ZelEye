'use strict';

// ---------------------------------------------------------------- utilidades
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function parseNum(v) {
  if (v == null) return null;
  const s = String(v).trim().replace(/[,_\s]/g, '');
  const m = s.match(/^(-?\d+(?:\.\d+)?)([kmbt])?$/i);
  if (!m) return null;
  return parseFloat(m[1]) * ({ k: 1e3, m: 1e6, b: 1e9, t: 1e12 }[(m[2] || '').toLowerCase()] || 1);
}
function fmt(n) {
  if (n == null || Number.isNaN(n)) return '<span class="muted">—</span>';
  const a = Math.abs(n);
  if (a >= 1e12) return (n / 1e12).toFixed(2) + 'T';
  if (a >= 1e9) return (n / 1e9).toFixed(2) + 'B';
  if (a >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (a >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return String(Math.round(n));
}
const pct = (n) => (n == null ? '<span class="muted">—</span>' : `<span class="${n >= 0 ? 'pct-up' : 'pct-down'}">${n >= 0 ? '+' : ''}${(n * 100).toFixed(1)}%</span>`);
const norm = (s) => String(s).toLowerCase().replace(/[^a-z0-9]/g, '');

// Mismos alias que scripts/build_data.py
const KINGDOM_ALIASES = {
  kingdom: ['kingdom', 'server', 'serverid', 'kd', 'reino', 'id'],
  zone: ['zone', 'zona', 'region'],
  total_power: ['totalpower', 'power', 'kingdompower', 'poder', 'podertotal'],
  lords: ['lords', 'players', 'lordcount', 'playercount', 'jugadores', 'numlords', 'numjugadores'],
  active_lords: ['activelords', 'activeplayers', 'activos'],
  top1_power: ['top1power', 'top1', 'maxpower', 'highestpower', 'top1poder', 'podertop1', 'podermaximo'],
  p10_power: ['p10power', 'top10thpower', 'rank10power', 'power10', 'decimo', '10poder', 'poder10', 'poderdel10', 'poderdecimo', 'decimopoder', '10power'],
  top10_power: ['top10power', 'top10sum', 'top10'],
  top100_power: ['top100power', 'top100sum', 'top100'],
  t5_lords: ['t5lords', 't5players', 't5', 't5count'],
  merits: ['merits', 'totalmerits', 'meritos'],
  kills: ['kills', 'totalkills', 'unitskilled'],
};
const PLAYER_ALIASES = {
  kingdom: ['kingdom', 'server', 'serverid', 'kd', 'reino'],
  zone: ['zone', 'zona', 'region'],
  power: ['power', 'poder', 'highestpower', 'currentpower'],
  name: ['name', 'lord', 'lordname', 'nombre'],
  alliance: ['alliance', 'guild', 'alianza'],
};

function parseCSV(text) {
  const lines = text.replace(/^﻿/, '').split(/\r?\n/).filter((l) => l.trim() && !l.trim().startsWith('#'));
  if (!lines.length) return [];
  const d = (lines[0].match(/;/g) || []).length >= (lines[0].match(/,/g) || []).length ? ';' : ',';
  const split = (line) => {
    const out = []; let cur = ''; let q = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (q) { if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') q = false; else cur += c; }
      else if (c === '"') q = true; else if (c === d) { out.push(cur); cur = ''; } else cur += c;
    }
    out.push(cur); return out;
  };
  const head = split(lines[0]).map((h) => norm(h));
  return lines.slice(1).map((l) => { const c = split(l); const o = {}; head.forEach((h, i) => { o[h] = (c[i] || '').trim(); }); return o; });
}
function mapRow(row, aliases) {
  const o = {};
  for (const [f, names] of Object.entries(aliases)) for (const n of names) if (row[n] !== undefined && row[n] !== '') { o[f] = row[n]; break; }
  return o;
}
function zoneId(rawK, rawZone) {
  const k = parseNum(rawK); if (k == null) return null;
  let z = (rawZone || '').toLowerCase().trim() || 'global';
  if (k < 0) return { zone: 'china', kingdom: -k };
  if (['cn', 'chn'].includes(z)) z = 'china';
  return { zone: z, kingdom: k };
}

// ---------------------------------------------------------------- estado
const state = { data: null, history: {}, view: 'groups', sort: { groups: ['ease', 'descending'], kingdoms: ['ease', 'descending'] }, open: new Set(), localImport: false };
let kIndex = new Map(); // "zone:kingdom" -> kingdom record

async function load() {
  const [d, h] = await Promise.all([
    fetch('data.json', { cache: 'no-cache' }).then((r) => r.json()),
    fetch('history.json', { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
  ]);
  state.data = d; state.history = h;
  for (const k of d.kingdoms) { k.players = k.players || []; kIndex.set(`${k.zone}:${k.kingdom}`, k); }
  restoreFilters();
  renderMeta();
  render();
}

// ---------------------------------------------------------------- cálculo
function growth7d(keys) {
  const dates = Object.keys(state.history).sort();
  if (dates.length < 2) return null;
  const last = dates[dates.length - 1];
  const target = new Date(new Date(last).getTime() - 7 * 864e5).toISOString().slice(0, 10);
  const base = dates.filter((x) => x <= target).pop() || dates[0];
  if (base === last) return null;
  let a = 0, b = 0, n = 0;
  for (const key of keys) {
    const x = state.history[base]?.[key]?.total_power, y = state.history[last]?.[key]?.total_power;
    if (x && y) { a += x; b += y; n++; }
  }
  return n ? b / a - 1 : null;
}
function rankOf(power, sortedDesc) {
  if (power == null || !sortedDesc.length) return null;
  let r = 1; for (const p of sortedDesc) { if (p > power) r++; else break; }
  return r;
}

function computeGroups() {
  const my = parseNum($('#f-power').value);
  return state.data.groups.map((g) => {
    const ks = g.kingdoms.map((id) => kIndex.get(`${g.zone}:${id}`)).filter(Boolean);
    const players = ks.flatMap((k) => k.players).sort((a, b) => b - a);
    const p10s = ks.map((k) => k.stats.p10_power ?? (k.players.length >= 10 ? k.players[9] : null)).filter((x) => x);
    let thr = null, thrKind = null;
    if (players.length >= 10) { thr = players[9]; thrKind = 'exact'; } else if (p10s.length) { thr = Math.max(...p10s); thrKind = 'lb'; }
    const totals = ks.map((k) => k.stats.total_power).filter((x) => x);
    const top1s = ks.map((k) => k.stats.top1_power ?? k.players[0]).filter((x) => x);
    const withStats = ks.filter((k) => Object.keys(k.stats).some((f) => f !== 'source') || k.players.length).length;
    let myRank = rankOf(my, players);
    let myRankTxt = myRank;
    if (my != null && thr != null && myRank == null) { myRank = my > thr && thrKind === 'exact' ? 10 : null; }
    return {
      g, ks, players, thr, thrKind,
      label: `${g.kingdoms[0]}–${g.kingdoms.at(-1)}`,
      first: g.kingdoms[0],
      top1: top1s.length ? Math.max(...top1s) : null,
      total: totals.length ? totals.reduce((a, b) => a + b, 0) : null,
      avg: totals.length ? totals.reduce((a, b) => a + b, 0) / totals.length : null,
      maxk: totals.length ? Math.max(...totals) : null,
      growth: growth7d(g.kingdoms.map((id) => `${g.zone}:${id}`)),
      myRank, myRankTxt, my,
      rivals: my != null && players.length ? players.filter((p) => p > my).length : null,
      coverage: withStats / g.kingdoms.length,
    };
  });
}

function filterGroups(rows, baseOnly = false) {
  if (baseOnly) return rows;
  const kq = $('#f-kingdom').value.trim();
  const maxThr = parseNum($('#f-maxthr').value), maxAvg = parseNum($('#f-maxavg').value);
  const withStats = $('#f-withstats').checked;
  return rows.filter((r) =>
    (!kq || r.g.kingdoms.some((k) => String(k) === kq)) &&
    (maxThr == null || (r.thr != null && r.thr <= maxThr)) && (maxAvg == null || (r.avg != null && r.avg <= maxAvg)) &&
    (!withStats || r.coverage > 0));
}

// Facilidad: percentil inverso de la métrica de dificultad entre los grupos visibles.
function assignEase(rows) {
  const useThr = rows.some((r) => r.thr != null);
  const metric = (r) => (useThr ? r.thr : r.avg);
  const vals = rows.map(metric).filter((x) => x != null).sort((a, b) => a - b);
  for (const r of rows) {
    const m = metric(r);
    if (m == null || vals.length < 2) { r.ease = m == null ? null : 100; continue; }
    const below = vals.filter((v) => v > m).length; // cuántos grupos son más difíciles
    r.ease = Math.round((below / (vals.length - 1)) * 100);
  }
  return useThr ? 'poder del 10º lord de la zona' : 'poder medio por reino';
}

// ---------------------------------------------------------------- render
function easeBadge(e) {
  if (e == null) return '<span class="muted">—</span>';
  const hue = Math.round((e / 100) * 130); // 0 rojo -> 130 verde
  return `<span class="easebar" title="Facilidad ${e}/100"><span class="track"><span class="fill" style="width:${Math.max(e, 4)}%;background:hsl(${hue} 70% 52%)"></span></span><b>${e}</b></span>`;
}
function thrCell(r) {
  if (r.thr == null) return fmt(null);
  return r.thrKind === 'lb' ? `<span class="lb" title="Mínimo garantizado: faltan datos de jugadores">≥ ${fmt(r.thr)}</span>` : fmt(r.thr);
}
function myCell(r, rank, thr, thrKind) {
  if (r.my == null) return fmt(null);
  if (rank != null) return `<span class="${rank <= 10 ? 'mine-good' : ''}">#${rank}</span>`;
  if (thr != null && thrKind === 'lb' && r.my <= thr) return '<span class="muted" title="El 10º es al menos este poder">fuera</span>';
  return '<span class="muted">?</span>';
}
function sortRows(rows, [key, dir]) {
  const m = dir === 'ascending' ? 1 : -1;
  return rows.sort((a, b) => {
    const x = a[key], y = b[key];
    if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
    return (typeof x === 'string' ? x.localeCompare(y, 'es', { numeric: true }) : x - y) * m;
  });
}

function render() {
  if (!state.data) return;
  const all = computeGroups();
  // La facilidad se calcula sobre todas las zonas, no sobre el resultado de los filtros,
  // para que buscar un reino concreto no cambie su nota.
  const basis = assignEase(filterGroups(all, true));
  const rows = filterGroups(all);
  saveFilters();
  renderSummary(rows, basis);
  renderPodium(all);
  if (state.view === 'groups') renderGroups(rows);
  if (state.view === 'kingdoms') renderKingdoms(rows);
}

function renderSummary(rows, basis) {
  const withThr = rows.filter((r) => r.thr != null);
  const best = sortRows([...rows], ['ease', 'descending'])[0];
  let s = `<strong>${rows.length}</strong> zonas · <strong>${rows.reduce((a, r) => a + r.g.kingdoms.length, 0)}</strong> reinos.`;
  if (withThr.length || rows.some((r) => r.avg != null)) {
    s += ` Competencia medida por el <strong>${basis}</strong>.`;
    if (best?.ease != null) s += ` Zona con menos competencia: <strong>reinos ${esc(best.label)}</strong> (10º lord: ${best.thrKind === 'lb' ? '≥ ' : ''}${fmt(best.thr ?? best.avg)}).`;
  } else s += ' Pulsa una zona para ver sus reinos.';
  $('#summary').innerHTML = s;
}

function renderGroups(rows) {
  sortRows(rows, state.sort.groups);
  const tb = $('#t-groups tbody');
  const html = [];
  for (const r of rows) {
    const id = r.g.id, open = state.open.has(id);
    html.push(`<tr class="g" tabindex="0" data-id="${esc(id)}" aria-expanded="${open}">
      <td>${easeBadge(r.ease)}</td><td class="zone-cell">${esc(r.label)}<small>${r.g.kingdoms.length} reinos</small></td><td>${thrCell(r)}</td><td>${fmt(r.top1)}</td>
      <td>${fmt(r.total)}</td><td>${fmt(r.avg)}</td><td>${fmt(r.maxk)}</td><td>${pct(r.growth)}</td>
      <td>${myCell(r, r.myRankTxt, r.thr, r.thrKind)}</td><td>${r.rivals == null ? fmt(null) : r.rivals}</td><td>${Math.round(r.coverage * 100)}%</td></tr>`);
    if (open) html.push(`<tr class="detail"><td colspan="11">${groupDetail(r)}</td></tr>`);
  }
  tb.innerHTML = html.join('') || '<tr><td colspan="11" class="muted">Ninguna zona cumple los filtros.</td></tr>';
  syncSortHeaders('#t-groups', state.sort.groups);
}

function groupDetail(r) {
  if (!hasStats()) {
    return `<div class="kchips"><span class="kchips-title">Reinos de la zona ${esc(r.label)}</span>${r.g.kingdoms.map((k) => `<span>${k}</span>`).join('')}</div>`;
  }
  const kRows = r.ks.map((k) => {
    const s = k.stats, p10 = s.p10_power ?? (k.players.length >= 10 ? k.players[9] : null);
    return `<tr><td>${k.kingdom}</td><td>${fmt(s.total_power)}</td><td>${fmt(s.lords)}</td>
      <td>${fmt(s.top1_power ?? k.players[0])}</td><td>${fmt(p10)}</td><td>${fmt(s.t5_lords)}</td><td>${fmt(s.merits)}</td>
      <td>${r.my != null ? (rankOf(r.my, k.players) ? '#' + rankOf(r.my, k.players) : '—') : '—'}</td></tr>`;
  }).join('');
  const top = r.ks.flatMap((k) => (k.top_names || []).map((t) => [...t, k.kingdom])).sort((a, b) => b[2] - a[2]).slice(0, 10);
  const topHtml = top.length
    ? `<table class="mini"><thead><tr><th>#</th><th>Lord</th><th>Alianza</th><th>Reino</th><th>Poder</th></tr></thead><tbody>${top.map((t, i) => `<tr><td>${i + 1}</td><td>${esc(t[0])}</td><td>${esc(t[1])}</td><td>${t[3]}</td><td>${fmt(t[2])}</td></tr>`).join('')}</tbody></table>`
    : '<p class="muted">Sin lista de jugadores para esta zona.</p>';
  return `<div class="detail-grid"><div><h4>Reinos de la zona</h4><table class="mini"><thead><tr><th>Reino</th><th>Poder</th><th>Lords</th><th>Top 1</th><th>10º</th><th>T5</th><th>Méritos</th><th>Tu puesto</th></tr></thead><tbody>${kRows}</tbody></table></div>
    <div><h4>Top 10 conocido de la zona</h4>${topHtml}</div></div>`;
}

function renderKingdoms(groupRows) {
  const rows = [];
  const kq = $('#f-kingdom').value.trim();
  for (const r of groupRows) for (const k of r.ks) {
    if (kq && String(k.kingdom) !== kq) continue;
    const s = k.stats;
    rows.push({
      r, k, ease: r.ease, kingdom: k.kingdom, label: r.label, first: r.first,
      total: s.total_power ?? null, lords: s.lords ?? null, top1: s.top1_power ?? k.players[0] ?? null,
      p10: s.p10_power ?? (k.players.length >= 10 ? k.players[9] : null), t5: s.t5_lords ?? null, merits: s.merits ?? null,
      growth: growth7d([`${k.zone}:${k.kingdom}`]), thr: r.thr,
      myRankK: rankOf(r.my, k.players), myRank: r.myRankTxt,
    });
  }
  sortRows(rows, state.sort.kingdoms);
  $('#t-kingdoms tbody').innerHTML = rows.slice(0, 2000).map((x) => `<tr>
    <td>${easeBadge(x.ease)}</td><td>${x.kingdom}</td><td>${esc(x.label)}</td>
    <td>${fmt(x.total)}</td><td>${fmt(x.lords)}</td><td>${fmt(x.top1)}</td><td>${fmt(x.p10)}</td><td>${fmt(x.t5)}</td><td>${fmt(x.merits)}</td>
    <td>${pct(x.growth)}</td><td>${thrCell(x.r)}</td><td>${myCell(x.r, x.myRankK, null, null)}</td><td>${myCell(x.r, x.myRank, x.r.thr, x.r.thrKind)}</td></tr>`).join('')
    || '<tr><td colspan="12" class="muted">Ningún reino cumple los filtros.</td></tr>';
  syncSortHeaders('#t-kingdoms', state.sort.kingdoms);
  state.lastKingdomRows = rows;
}

function syncSortHeaders(sel, [key, dir]) {
  for (const th of document.querySelectorAll(`${sel} thead th`)) {
    if (th.dataset.key === key) th.setAttribute('aria-sort', dir); else th.removeAttribute('aria-sort');
  }
}

function renderMeta() {
  const d = state.data;
  const when = new Date(d.generated_at).toLocaleString('es-ES', { dateStyle: 'medium', timeStyle: 'short' });
  const nice = { 'kingdoms_codtracker.csv': 'cod-tracker.com', 'top_players.csv': 'lords CSV', 'kingdoms.csv': 'CSV', 'api': 'API' };
  const srcs = [...new Set(d.sources.map((x) => nice[x] || x))];
  $('#meta').textContent = `Actualizado: ${when} · Datos: ${srcs.length ? srcs.join(', ') : 'ninguno todavía'}${state.localImport ? ' + CSV local' : ''}`;
  const b = $('#banner');
  const any = hasStats();
  document.body.classList.toggle('nostats', !any);
  $('#cap-groups').textContent = any ? 'Todas las zonas, de menos a más competencia · pulsa una fila para ver sus reinos' : 'Todas las zonas · pulsa una para ver sus reinos';
  b.hidden = any;
  if (!any) b.innerHTML = `<div class="icon" aria-hidden="true">⛰</div><div>
    <h2>Aún no hay stats de reinos</h2>
    <p>Las zonas ya están cargadas: pulsa cualquiera para ver sus 8 reinos. Para saber cuál es la más fácil faltan los datos de poder:</p>
    <ol>
      <li>Pulsa <strong>Importar CSV</strong> con el poder de los lords o reinos (solo se carga en tu navegador).</li>
      <li>O súbelos a <code>data/stats/</code> en GitHub y se publican en la próxima actualización diaria.</li>
    </ol></div>`;
  const ks = d.kingdoms;
  const withData = ks.filter((k) => k.players.length || Object.keys(k.stats).some((f) => f !== 'source')).length;
  $('#chip-zones').textContent = d.groups.length;
  $('#chip-kingdoms').textContent = ks.length;
  $('#chip-coverage').textContent = `${Math.round((withData / ks.length) * 100)}%`;
}
function hasStats() { return state.localImport || state.data.has_stats; }

function renderPodium(all) {
  const box = $('#podium');
  const top = sortRows(all.filter((r) => r.ease != null), ['ease', 'descending']).slice(0, 3);
  box.hidden = !hasStats() || !top.length || state.view === 'help';
  if (box.hidden) return;
  box.innerHTML = top.map((r, i) => `<button type="button" class="card r${i + 1}" data-id="${esc(r.g.id)}">
      <div class="rank">${['🥇 La más fácil', '🥈 2ª más fácil', '🥉 3ª más fácil'][i]}</div>
      <div class="zone">${esc(r.label)}</div>
      <div class="kv"><span>10º lord</span><b>${r.thrKind === 'lb' ? '≥ ' : ''}${fmt(r.thr)}</b></div>
      <div class="kv"><span>Top 1</span><b>${fmt(r.top1)}</b></div>
      <div class="kv"><span>Media por reino</span><b>${fmt(r.avg)}</b></div>
      ${r.my != null ? `<div class="kv"><span>Tu puesto</span><b class="${r.myRankTxt != null && r.myRankTxt <= 10 ? 'good' : ''}">${r.myRankTxt != null ? '#' + r.myRankTxt : '?'}</b></div>` : ''}
    </button>`).join('');
}

// ---------------------------------------------------------------- import / export
async function importFiles(files) {
  let nk = 0, np = 0;
  for (const f of files) {
    const rows = parseCSV(await f.text());
    if (!rows.length) continue;
    const isPlayers = 'power' in rows[0] && !('totalpower' in rows[0]) && ('name' in rows[0] || 'lord' in rows[0] || 'lordname' in rows[0] || 'nombre' in rows[0] || /player|lord|jugador/i.test(f.name));
    const touched = new Set();
    for (const raw of rows) {
      if (isPlayers) {
        const m = mapRow(raw, PLAYER_ALIASES), id = zoneId(m.kingdom, m.zone), p = parseNum(m.power);
        const k = id && kIndex.get(`${id.zone}:${id.kingdom}`);
        if (!k || p == null) continue;
        if (!touched.has(k)) { touched.add(k); k.players = []; k.top_names = []; }
        k.players.push(p); k.top_names.push([m.name || '', m.alliance || '', p]); np++;
      } else {
        const m = mapRow(raw, KINGDOM_ALIASES), id = zoneId(m.kingdom, m.zone);
        const k = id && kIndex.get(`${id.zone}:${id.kingdom}`);
        if (!k) continue;
        for (const f2 of Object.keys(KINGDOM_ALIASES)) if (!['kingdom', 'zone'].includes(f2) && m[f2] != null) k.stats[f2] = parseNum(m[f2]);
        nk++;
      }
    }
    for (const k of touched) { k.players.sort((a, b) => b - a); k.top_names.sort((a, b) => b[2] - a[2]); k.top_names = k.top_names.slice(0, 10); }
  }
  state.localImport = nk + np > 0;
  renderMeta(); render();
  $('#summary').insertAdjacentHTML('afterbegin', `Importado localmente: ${nk} reinos, ${np} lords. `);
}

function exportCSV() {
  const all = computeGroups(); assignEase(filterGroups(all, true)); const groups = filterGroups(all);
  let lines;
  if (state.view === 'kingdoms') {
    renderKingdoms(groups);
    lines = [['ease', 'kingdom', 'zone_kingdoms', 'total_power', 'lords', 'top1_power', 'p10_power', 't5_lords', 'merits', 'zone_top10_threshold']]
      .concat(state.lastKingdomRows.map((x) => [x.ease, x.kingdom, x.label, x.total, x.lords, x.top1, x.p10, x.t5, x.merits, x.thr]));
  } else {
    sortRows(groups, state.sort.groups);
    lines = [['ease', 'first_kingdom', 'last_kingdom', 'top10_threshold', 'threshold_kind', 'top1', 'total_power', 'avg_kingdom_power', 'max_kingdom_power', 'growth_7d', 'rivals_above_you', 'coverage']]
      .concat(groups.map((r) => [r.ease, r.g.kingdoms[0], r.g.kingdoms.at(-1), r.thr, r.thrKind, r.top1, r.total, r.avg, r.maxk, r.growth, r.rivals, r.coverage]));
  }
  const csv = lines.map((l) => l.map((v) => (v == null ? '' : String(v).includes(';') ? `"${v}"` : v)).join(';')).join('\n');
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([csv], { type: 'text/csv' })), download: `great-heights-${state.view === 'groups' ? 'zonas' : 'reinos'}.csv` });
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ---------------------------------------------------------------- filtros persistentes (URL)
const FILTERS = ['f-kingdom', 'f-power', 'f-maxthr', 'f-maxavg', 'f-withstats'];
function saveFilters() {
  const p = new URLSearchParams();
  for (const id of FILTERS) { const el = document.getElementById(id); const v = el.type === 'checkbox' ? (el.checked ? '1' : '') : el.value; if (v) p.set(id.slice(2), v); }
  if (state.view !== 'groups') p.set('view', state.view);
  history.replaceState(null, '', p.toString() ? `?${p}` : location.pathname);
}
function restoreFilters() {
  const p = new URLSearchParams(location.search);
  for (const id of FILTERS) { const v = p.get(id.slice(2)); if (v == null) continue; const el = document.getElementById(id); if (el.type === 'checkbox') el.checked = v === '1'; else el.value = v; }
  if (p.get('view')) setView(p.get('view'), false);
}

function setView(v, rerender = true) {
  state.view = v;
  for (const b of document.querySelectorAll('.tabs button')) b.setAttribute('aria-pressed', String(b.dataset.view === v));
  $('#view-groups').hidden = v !== 'groups'; $('#view-kingdoms').hidden = v !== 'kingdoms'; $('#view-help').hidden = v !== 'help';
  if (rerender) render();
}

// ---------------------------------------------------------------- eventos
let t;
for (const id of FILTERS) document.getElementById(id).addEventListener('input', () => { clearTimeout(t); t = setTimeout(render, 150); });
$('#btn-reset').addEventListener('click', () => { for (const id of FILTERS) { const el = document.getElementById(id); if (el.type === 'checkbox') el.checked = false; else el.value = ''; } render(); });
$('#btn-export').addEventListener('click', exportCSV);
$('#f-import').addEventListener('change', (e) => importFiles([...e.target.files]));
for (const b of document.querySelectorAll('.tabs button')) b.addEventListener('click', () => setView(b.dataset.view));
for (const view of ['groups', 'kingdoms']) {
  document.querySelector(`#t-${view} thead`).addEventListener('click', (e) => {
    const th = e.target.closest('th'); if (!th) return;
    const [key, dir] = state.sort[view];
    state.sort[view] = [th.dataset.key, key === th.dataset.key && dir === 'descending' ? 'ascending' : (key === th.dataset.key ? 'descending' : (th.dataset.type === 'text' || ['first', 'kingdom', 'thr', 'avg', 'total', 'top1', 'maxk', 'p10', 'myRank', 'myRankK', 'rivals'].includes(th.dataset.key) ? 'ascending' : 'descending'))];
    render();
  });
}
const toggleRow = (tr) => { const id = tr.dataset.id; if (state.open.has(id)) state.open.delete(id); else state.open.add(id); render(); };
$('#t-groups tbody').addEventListener('click', (e) => { const tr = e.target.closest('tr.g'); if (tr) toggleRow(tr); });
$('#t-groups tbody').addEventListener('keydown', (e) => { const tr = e.target.closest('tr.g'); if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); toggleRow(tr); } });

$('#podium').addEventListener('click', (e) => {
  const c = e.target.closest('.card'); if (!c) return;
  state.open.add(c.dataset.id); setView('groups');
  requestAnimationFrame(() => document.querySelector(`tr.g[data-id="${CSS.escape(c.dataset.id)}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
});
load().catch((e) => { $('#meta').textContent = 'Error cargando datos: ' + e.message; });
