// app.js — Kommandozentrale (read-only). Vanilla JS, kein Build-Schritt.
const $ = (s) => document.querySelector(s);
const el = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstChild; };
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));

let state = { view: 'workflows', detailId: null };

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

// ── Health / Stats ──────────────────────────────────────────────────────
async function loadHealth() {
  try {
    const h = await getJSON('/api/health');
    $('#nav-wf').textContent = h.workflows;
    $('#nav-os').textContent = h.ossifikat_staging;
    $('#health-text').textContent = `online · ${h.workflows} runs`;
    return h;
  } catch (e) {
    $('#health-text').textContent = 'backend offline';
    throw e;
  }
}

function renderStats(h) {
  $('#stats').innerHTML = '';
  const items = state.view === 'workflows'
    ? [['Workflow-Läufe', h.workflows], ['ossifikat Staging', h.ossifikat_staging], ['bestätigt', h.ossifikat_confirmed]]
    : [['Staging-Tripel', h.ossifikat_staging], ['bestätigt', h.ossifikat_confirmed], ['Workflow-Läufe', h.workflows]];
  for (const [l, n] of items) {
    $('#stats').appendChild(el(`<div class="stat"><div class="n">${esc(n)}</div><div class="l">${esc(l)}</div></div>`));
  }
}

// ── Workflows ───────────────────────────────────────────────────────────
async function viewWorkflows() {
  $('#view-title').textContent = 'Workflows';
  $('#view-sub').textContent = 'Läufe des 6-Phasen-Agenten · neueste zuerst';
  const { workflows } = await getJSON('/api/workflows');
  const c = $('#content'); c.innerHTML = '';
  if (!workflows.length) { c.appendChild(el('<div class="empty">Noch keine Workflow-Läufe.</div>')); return; }
  for (const w of workflows) {
    const verdict = w.mitte_verdict ? `<span class="badge verdict">mitte: ${esc(w.mitte_verdict)}</span>` : '';
    const drift = w.drift_count ? `<span class="badge drift">${w.drift_count}× drift</span>` : '';
    const card = el(`<div class="card" data-id="${esc(w.id)}">
      <div class="card__top">
        <span class="badge ${esc(w.status)}">${esc(w.status)}</span>
        <span class="card__task">${esc(w.task)}</span>
        ${verdict}${drift}
      </div>
      <div class="card__meta">
        <span>${esc(w.id)}</span>
        <span>${esc(w.task_type)}</span>
        <span>${w.phase_count} Phasen</span>
        ${w.files_written.length ? `<span>${w.files_written.length} Datei(en)</span>` : ''}
      </div>
    </div>`);
    card.addEventListener('click', () => { state.detailId = w.id; render(); });
    c.appendChild(card);
  }
}

async function viewWorkflowDetail(id) {
  $('#view-title').textContent = 'Workflow';
  $('#view-sub').textContent = id;
  const d = await getJSON(`/api/workflows/${encodeURIComponent(id)}`);
  const c = $('#content'); c.innerHTML = '';
  c.appendChild(el(`<span class="back" id="back">← zurück zur Liste</span>`));
  $('#back').addEventListener('click', () => { state.detailId = null; render(); });

  const s = d.summary;
  c.appendChild(el(`<div class="section"><h3>Aufgabe</h3><div>${esc(s.task)}</div>
    <div class="card__meta" style="margin-top:8px">
      <span class="badge ${esc(s.status)}">${esc(s.status)}</span>
      <span>tests: ${s.tests_passed === null ? '–' : (s.tests_passed ? '✓' : '✗')}</span>
      <span>committed: ${s.committed ? '✓' : '–'}</span>
      ${s.mitte_verdict ? `<span class="badge verdict">mitte: ${esc(s.mitte_verdict)}</span>` : ''}
    </div></div>`));

  // Healthpoint timeline
  const chips = (d.healthpoint_checks || []).map(ch =>
    `<span class="phasechip ${ch.aligned ? 'aligned' : 'drift'}" title="${esc(ch.drift || '')}">${esc(ch.phase)} ${ch.aligned ? '✓' : '⚠'}</span>`
  ).join('');
  if (chips) c.appendChild(el(`<div class="section"><h3>Healthpoint · Drift-Anker</h3><div class="phaseline">${chips}</div></div>`));

  if (s.files_written && s.files_written.length)
    c.appendChild(el(`<div class="section"><h3>Geschriebene Dateien</h3><div class="filelist">${s.files_written.map(esc).join('<br>')}</div></div>`));

  const sect = (title, body) => { if (body && String(body).trim()) c.appendChild(el(`<div class="section"><h3>${esc(title)}</h3><pre>${esc(body)}</pre></div>`)); };
  sect('Briefing · Analyse', d.briefing?.analysis);
  sect('Strategie', d.strategy);
  sect('Detail-Plan', d.plan);
  if (d.hallucinated_files && d.hallucinated_files.length)
    c.appendChild(el(`<div class="section"><h3>⚠ Halluzinierte Dateien (geblockt)</h3><div class="filelist">${d.hallucinated_files.map(esc).join('<br>')}</div></div>`));
  sect('Code-Review', d.execution?.code_review);
  sect('Verification · Test-Output', d.verification?.output);
  if (d.commit && d.commit.steps) sect('Commit', JSON.stringify(d.commit.steps, null, 2));
}

// ── Knowledge / ossifikat ───────────────────────────────────────────────
async function viewKnowledge() {
  $('#view-title').textContent = 'Wissens-Substrat';
  $('#view-sub').textContent = 'ossifikat-Staging · per Klick bestätigen oder verwerfen';
  const { triples } = await getJSON('/api/ossifikat/staging');
  const c = $('#content'); c.innerHTML = '';
  if (!triples.length) { c.appendChild(el('<div class="empty">Staging leer. Brücken erzeugen via experiments/bridges_to_ossifikat.py</div>')); return; }
  for (const t of triples) {
    const card = el(`<div class="triple" data-id="${esc(t.id)}">
      <div class="triple__edge"><span class="s">${esc(t.subject)}</span><span class="p">—[${esc(t.predicate)}]→</span><span class="o">${esc(t.object)}</span></div>
      ${t.rationale ? `<div class="triple__rat">↳ ${esc(t.rationale)}</div>` : ''}
      <div class="triple__foot"><span>#${esc(t.id)}</span><span>conf ${esc(t.confidence)}</span><span>${esc(t.source)}</span><span>${esc((t.created_at||'').slice(0,19))}</span></div>
      <div class="triple__act">
        <button class="rbtn ok">✓ bestätigen</button>
        <button class="rbtn no">✗ verwerfen</button>
        <span class="rbtn__msg"></span>
      </div>
    </div>`);
    card.querySelector('.rbtn.ok').addEventListener('click', () => ratifyTriple(t.id, 'confirm', card));
    card.querySelector('.rbtn.no').addEventListener('click', () => ratifyTriple(t.id, 'reject', card));
    c.appendChild(card);
  }
}

// Ratifizierung per Klick → POST mit Bearer-Token (aus localStorage, vom Terminal-Tab).
async function ratifyTriple(id, action, card) {
  const token = localStorage.getItem('vibelike_token');
  const msg = card.querySelector('.rbtn__msg');
  if (!token) { msg.textContent = 'Token nötig — im Terminal-Tab eingeben'; return; }
  card.querySelectorAll('.rbtn').forEach(b => b.disabled = true);
  try {
    const r = await fetch(`/api/ossifikat/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
      body: JSON.stringify({ id }),
    });
    if (r.ok) {
      card.classList.add(action === 'confirm' ? 'is-ok' : 'is-no');
      setTimeout(() => {
        card.remove();
        loadHealth().catch(() => {});
        if (!$('#content').querySelector('.triple'))
          $('#content').innerHTML = '<div class="empty">Staging leer — alles ratifiziert. ✓</div>';
      }, 280);
    } else {
      msg.textContent = r.status === 401 ? 'Token ungültig' : r.status === 403 ? 'keine Ratify-Berechtigung' : `Fehler ${r.status}`;
      card.querySelectorAll('.rbtn').forEach(b => b.disabled = false);
    }
  } catch {
    msg.textContent = 'Netzwerkfehler';
    card.querySelectorAll('.rbtn').forEach(b => b.disabled = false);
  }
}

// ── Terminal (xterm.js + WebSocket /ws/terminal) ────────────────────────
let term = null, termFit = null, termWs = null;
const setTmStatus = (s) => { const e = document.getElementById('tm-status'); if (e) e.textContent = s; };
const sendResize = () => {
  if (term && termWs && termWs.readyState === 1) {
    try { termFit.fit(); } catch {}
    termWs.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
  }
};
const onWinResize = () => sendResize();

function cleanupTerminal() {
  window.removeEventListener('resize', onWinResize);
  if (termWs) { try { termWs.close(); } catch {} termWs = null; }
  if (term) { try { term.dispose(); } catch {} term = null; }
}

function connectTerminal() {
  const token = (document.getElementById('tm-token').value || '').trim();
  if (!token) { setTmStatus('Token fehlt'); return; }
  localStorage.setItem('vibelike_token', token);
  cleanupTerminal();
  term = new Terminal({
    fontFamily: 'JetBrains Mono, ui-monospace, monospace', fontSize: 13, cursorBlink: true,
    scrollback: 5000,
    theme: { background: '#13130F', foreground: '#ECE6D9', cursor: '#D08A4D' },
  });
  termFit = new FitAddon.FitAddon();
  term.loadAddon(termFit);
  term.open(document.getElementById('term'));
  requestAnimationFrame(() => { try { termFit.fit(); } catch {} });

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  termWs = new WebSocket(`${proto}://${location.host}/ws/terminal`);
  termWs.onopen = () => { setTmStatus('verbunden'); termWs.send(JSON.stringify({ type: 'auth', token })); sendResize(); };
  termWs.onmessage = (e) => term && term.write(e.data);
  termWs.onerror = () => setTmStatus('Fehler');
  termWs.onclose = (e) => {
    const why = e.code === 4401 ? ' (Auth)' : e.code === 4403 ? ' (keine terminal-Capability)' : e.code >= 4400 ? ` (${e.code})` : '';
    setTmStatus('getrennt' + why);
  };
  term.onData((d) => { if (termWs && termWs.readyState === 1) termWs.send(JSON.stringify({ type: 'input', data: d })); });
  window.addEventListener('resize', onWinResize);
}

function viewTerminal() {
  $('#view-title').textContent = 'Terminal';
  $('#view-sub').textContent = 'PTY · terminal.py hinter Token-Auth';
  $('#stats').innerHTML = '';
  // schon mit offener Session? nicht neu aufbauen.
  if (document.getElementById('term') && termWs && termWs.readyState <= 1) return;
  const saved = localStorage.getItem('vibelike_token') || '';
  const c = $('#content'); c.innerHTML = '';
  const bar = el(`<div class="tmbar">
    <input id="tm-token" type="password" autocomplete="off" placeholder="Bearer-Token (pair_admin / Pairing)" value="${esc(saved)}">
    <button id="tm-connect">Verbinden</button>
    <span id="tm-status" class="tm-status">getrennt</span>
  </div>`);
  c.appendChild(bar);
  const termDiv = el('<div id="term"></div>');
  c.appendChild(termDiv);
  attachTermTouch(termDiv);
  document.getElementById('tm-connect').addEventListener('click', connectTerminal);
}

// Swipe-→-Scrollback: xterm scrollt am Handy nativ unzuverlässig (Viewport vs. Seiten-
// Scroll). Wir mappen die vertikale Wischgeste direkt auf term.scrollLines — renderer-
// agnostisch (Zeilenhöhe aus dem Viewport berechnet). preventDefault hält die Geste im
// Terminal statt die Seite zu scrollen.
function attachTermTouch(node) {
  let ty = null;
  // Capture-Phase (3. Arg capture:true): unser Scroll greift VOR xterms Text-/Auswahl-
  // Ebene — sonst fängt die die Wischgeste über Text ab und es scrollt nur im Schwarzen.
  node.addEventListener('touchstart', (e) => {
    ty = e.touches.length === 1 ? e.touches[0].clientY : null;
  }, { capture: true, passive: true });
  node.addEventListener('touchmove', (e) => {
    if (ty === null || !term) return;
    const vp = term.element && term.element.querySelector('.xterm-viewport');
    const rows = (term.buffer && term.buffer.active && term.buffer.active.length) || term.rows || 24;
    const cell = vp && vp.scrollHeight ? vp.scrollHeight / rows : 18;
    const lines = Math.trunc((ty - e.touches[0].clientY) / cell);
    if (lines !== 0) { term.scrollLines(lines); ty = e.touches[0].clientY; e.preventDefault(); }
  }, { capture: true, passive: false });
  node.addEventListener('touchend', () => { ty = null; }, { capture: true, passive: true });
}

// ── Router ──────────────────────────────────────────────────────────────
async function render() {
  document.querySelectorAll('.navbtn').forEach(b => b.classList.toggle('is-active', b.dataset.view === state.view));
  if (state.view !== 'terminal') cleanupTerminal();
  if (state.view === 'terminal') {
    try { await loadHealth(); } catch {}   // Sidebar-Pills best-effort, Terminal hängt nicht dran
    return viewTerminal();
  }
  try {
    const h = await loadHealth();
    renderStats(h);
    if (state.view === 'workflows') {
      if (state.detailId) await viewWorkflowDetail(state.detailId);
      else await viewWorkflows();
    } else {
      await viewKnowledge();
    }
  } catch (e) {
    $('#content').innerHTML = `<div class="empty">Fehler: ${esc(e.message)}<br>Läuft das Backend? <code>python3 web/server.py</code></div>`;
  }
}

// ── Drawer (mobil) ──────────────────────────────────────────────────────
const closeNav = () => document.body.classList.remove('nav-open');
$('#menu-toggle').addEventListener('click', () => document.body.classList.toggle('nav-open'));
$('#backdrop').addEventListener('click', closeNav);

document.querySelectorAll('.navbtn').forEach(b =>
  b.addEventListener('click', () => { state.view = b.dataset.view; state.detailId = null; closeNav(); render(); }));
$('#refresh').addEventListener('click', render);
render();
