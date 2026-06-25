// app.js — Kommandozentrale (read-only). Vanilla JS, kein Build-Schritt.
const $ = (s) => document.querySelector(s);
const el = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstChild; };
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));

let state = { view: 'workflows', detailId: null, ratifyView: 'queue' };

function showToast(msg) {
  const toast = document.createElement('div');
  toast.style.cssText = 'position:fixed;bottom:1rem;right:1rem;background:var(--tm-accent);color:#fff;padding:0.75rem 1rem;border-radius:4px;z-index:9999;font-size:0.875rem;box-shadow:0 4px 12px rgba(0,0,0,0.3);animation:slideIn 0.3s ease';
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; setTimeout(() => toast.remove(), 300); }, 3000);
}

// Add animation keyframes if not exists
if (!document.getElementById('toast-styles')) {
  const style = document.createElement('style');
  style.id = 'toast-styles';
  style.textContent = '@keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }';
  document.head.appendChild(style);
}

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
  const rv = state.ratifyView || 'queue';
  $('#view-title').textContent = 'Wissens-Substrat';
  $('#view-sub').textContent = 'ossifikat · verbürgen, parken oder archivieren (alles reversibel)';
  const data = await getJSON('/api/ossifikat/staging?view=' + rv);
  const triples = data.triples || [];
  const k = data.counts || { queue: 0, parked: 0, archived: 0 };
  const c = $('#content'); c.innerHTML = '';

  const nav = el(`<div class="subnav">
    <span class="subnav__btn" data-rv="queue">Queue <b>${k.queue}</b></span>
    <span class="subnav__btn" data-rv="parked">Geparkt <b>${k.parked}</b></span>
    <span class="subnav__btn" data-rv="archived">Archiv <b>${k.archived}</b></span>
  </div>`);
  nav.querySelectorAll('.subnav__btn').forEach(b => {
    if (b.dataset.rv === rv) b.classList.add('is-active');
    b.addEventListener('click', () => { state.ratifyView = b.dataset.rv; viewKnowledge(); });
  });
  c.appendChild(nav);

  if (!triples.length) {
    const m = rv === 'queue' ? 'Queue leer — alles entschieden. ✓'
            : rv === 'parked' ? 'Nichts geparkt.' : 'Archiv leer.';
    c.appendChild(el(`<div class="empty">${m}</div>`)); return;
  }
  for (const t of triples) {
    const acts = rv === 'queue'
      ? `<button class="rbtn ok" data-a="confirm">✓ verbürgen</button>
         <button class="rbtn park" data-a="park">~ parken</button>
         <button class="rbtn no" data-a="archive">✗ archivieren</button>`
      : rv === 'parked'
      ? `<button class="rbtn ok" data-a="confirm">✓ verbürgen</button>
         <button class="rbtn back" data-a="restore">↩ in die Queue</button>
         <button class="rbtn no" data-a="archive">✗ archivieren</button>`
      : `<button class="rbtn back" data-a="restore">↩ in die Queue</button>
         <button class="rbtn del" data-a="reject">🗑 endgültig löschen</button>`;
    const card = el(`<div class="triple" data-id="${esc(t.id)}">
      <div class="triple__edge"><span class="s">${esc(t.subject)}</span><span class="p">—[${esc(t.predicate)}]→</span><span class="o">${esc(t.object)}</span></div>
      ${t.rationale ? `<div class="triple__rat">↳ ${esc(t.rationale)}</div>` : ''}
      <div class="triple__foot"><span>#${esc(t.id)}</span><span>conf ${esc(t.confidence)}</span><span>${esc(t.source)}</span><span>${esc((t.created_at||'').slice(0,19))}</span></div>
      <div class="triple__act">${acts}<span class="rbtn__msg"></span></div>
    </div>`);
    card.querySelectorAll('.rbtn').forEach(b =>
      b.addEventListener('click', () => ratifyTriple(t.id, b.dataset.a, card)));
    c.appendChild(card);
  }
}

// Ratifizierung per Klick → POST mit Bearer-Token (aus localStorage, vom Terminal-Tab).
// Aktionen: confirm | park | archive | restore | reject(endgültig).
async function ratifyTriple(id, action, card) {
  const token = localStorage.getItem('vibelike_token');
  const msg = card.querySelector('.rbtn__msg');
  if (!token) { msg.textContent = 'Token nötig — im Terminal-Tab eingeben'; return; }
  if (action === 'reject' && !confirm('Endgültig löschen? Das ist unwiderruflich.')) return;
  card.querySelectorAll('.rbtn').forEach(b => b.disabled = true);
  try {
    const r = await fetch(`/api/ossifikat/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
      body: JSON.stringify({ id }),
    });
    if (r.ok) {
      const cls = (action === 'confirm' || action === 'restore') ? 'is-ok'
                : action === 'park' ? 'is-park' : 'is-no';
      card.classList.add(cls);
      setTimeout(() => { loadHealth().catch(() => {}); viewKnowledge(); }, 280);
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
let term = null, termFit = null, termWs = null, termBuilt = false, ratMode = false;
const setTmStatus = (s) => { const e = document.getElementById('tm-status'); if (e) e.textContent = s; };

// Rat-Modus-Toggle: hängt '??' vor jede gesendete Zeile → Council (lokal+Frontier+Synthese).
// Mechanik: beim Einschalten + nach jedem Enter wird '??' an den Prompt geschickt.
function toggleRat() {
  ratMode = !ratMode;
  const btn = document.getElementById('tm-rat');
  if (btn) { btn.classList.toggle('is-on', ratMode); btn.textContent = ratMode ? '🜂 Rat: AN' : '🜂 Rat'; }
  if (ratMode && termWs && termWs.readyState === 1) termWs.send(JSON.stringify({ type: 'input', data: '??' }));
}
const termVisible = () => term && term.element && term.element.offsetParent !== null;
const sendResize = () => {
  if (term && termWs && termWs.readyState === 1 && termVisible()) {
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
  term.onData((d) => {
    if (!(termWs && termWs.readyState === 1)) return;
    termWs.send(JSON.stringify({ type: 'input', data: d }));
    // Rat-Modus: nach Enter '??' an den nächsten Prompt voranstellen
    if (ratMode && d.indexOf('\r') !== -1) termWs.send(JSON.stringify({ type: 'input', data: '??' }));
  });
  window.addEventListener('resize', onWinResize);
}

// Terminal-Pane EINMAL bauen (persistent außerhalb von #content) → überlebt Tab-Wechsel.
function ensureTermPane() {
  const pane = $('#term-pane');
  if (termBuilt) return pane;
  const saved = localStorage.getItem('vibelike_token') || '';
  pane.innerHTML = '';
  pane.appendChild(el(`<div class="tmbar">
    <input id="tm-token" type="password" autocomplete="off" placeholder="Bearer-Token (pair_admin / Pairing)" value="${esc(saved)}">
    <button id="tm-connect">Verbinden</button>
    <button id="tm-rat" class="tm-rat" title="Rat-Modus: jede Zeile über lokal + Frontier + Synthese (Konsens & Unterschiede)">🜂 Rat</button>
    <span id="tm-status" class="tm-status">getrennt</span>
  </div>`));
  const termDiv = el('<div id="term"></div>');
  pane.appendChild(termDiv);
  attachTermTouch(termDiv);
  document.getElementById('tm-connect').addEventListener('click', connectTerminal);
  document.getElementById('tm-rat').addEventListener('click', toggleRat);
  termBuilt = true;
  return pane;
}

function viewTerminal() {
  $('#view-title').textContent = 'Terminal';
  $('#view-sub').textContent = 'PTY · terminal.py hinter Token-Auth';
  $('#stats').innerHTML = '';
  $('#content').classList.add('hidden');
  ensureTermPane().classList.remove('hidden');
  // sichtbar geworden → neu einpassen (Session + Scrollback bleiben erhalten)
  if (term && termFit) requestAnimationFrame(() => sendResize());
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

// ── Models Status (Sidebar Live Updates) ──────────────────────────────
let modelStatusInterval = null;

async function loadModelStatus() {
  try {
    const r = await fetch('/api/models/status');
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  } catch (e) {
    console.warn('Model status fetch failed:', e);
    return [];
  }
}

function renderModelStatus(models) {
  const container = document.getElementById('model-status');
  if (!container) return;

  container.innerHTML = '';

  if (!models || models.length === 0) {
    container.innerHTML = '<div class="model-status-item">Keine Modelle</div>';
    return;
  }

  for (const m of models) {
    const statusIcon = m.status === '✓' ? '✓' : '✗';
    const statusColor = m.available ? '#6fc041' : '#999';
    const item = document.createElement('div');
    item.className = 'model-status-item';
    item.innerHTML = `
      <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
        <input type="checkbox" class="model-checkbox" data-model="${m.name}"
               ${m.available ? 'checked' : 'disabled'}>
        <span style="color:${statusColor}; font-weight:bold;">${statusIcon}</span>
        <span style="flex:1;">${m.name}</span>
        <span style="font-size:11px; color:#999;">${m.tier}</span>
      </label>
    `;
    container.appendChild(item);

    // Checkbox-Handler
    const checkbox = item.querySelector('.model-checkbox');
    checkbox.addEventListener('change', updateSelectedModels);
  }
}

async function updateSelectedModels() {
  const token = getToken();
  if (!token) return;

  const selected = Array.from(document.querySelectorAll('.model-checkbox:checked'))
    .map(cb => cb.dataset.model);

  try {
    await fetch('/api/models/selected', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ models: selected })
    });
  } catch (e) {
    console.warn('Model selection save failed:', e);
  }
}

function startModelStatusUpdates() {
  if (modelStatusInterval) clearInterval(modelStatusInterval);

  // Load once immediately
  loadModelStatus().then(renderModelStatus);

  // Update every 5 seconds
  modelStatusInterval = setInterval(() => {
    loadModelStatus().then(renderModelStatus);
  }, 5000);
}

// ── Models / Backends ───────────────────────────────────────────────────
function getToken() {
  const el = document.getElementById('tm-token');
  if (!el) return null;
  const token = (el.value || '').trim();
  if (token) return token;
  // Fallback: localStorage (falls Terminal noch nicht verbunden)
  return (localStorage.getItem('vibelike_token') || '').trim();
}

async function loadBackends() {
  const token = getToken();
  if (!token) { throw new Error('Token fehlt — zuerst im Terminal connecten'); }
  const r = await fetch('/api/backends', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  if (!r.ok) throw new Error(`${r.status} Backends laden`);
  return r.json();
}

async function setBackendKey(name, key) {
  const token = getToken();
  if (!token) throw new Error('Token fehlt — im Terminal connecten');
  const r = await fetch(`/api/backends/${name}/key`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ key })
  });
  if (!r.ok) {
    const err = await r.text();
    throw new Error(`${r.status}: ${err}`);
  }
  return r.json();
}

async function setPrivacyLevel(level) {
  const token = getToken();
  if (!token) throw new Error('Token fehlt — im Terminal connecten');
  const r = await fetch('/api/privacy/level', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ level })
  });
  if (!r.ok) throw new Error(`${r.status} Privacy-Level setzen`);
  return r.json();
}

async function updateLLMMode(mode) {
  // Setzt die Environment-Variable VIBELIKE_DEEPSEEK_MAX oder VIBELIKE_ARCH
  // via /api/config endpoint (wird in server.py implementiert)
  const envVars = {};
  
  switch(mode) {
    case 'deepseek-max':
      envVars['VIBELIKE_DEEPSEEK_MAX'] = '1';
      envVars['VIBELIKE_ARCH'] = 'default';
      break;
    case 'mitte':
      envVars['VIBELIKE_DEEPSEEK_MAX'] = '0';
      envVars['VIBELIKE_ARCH'] = 'mitte';
      break;
    case 'default':
      envVars['VIBELIKE_DEEPSEEK_MAX'] = '0';
      envVars['VIBELIKE_ARCH'] = 'default';
      break;
  }
  
  try {
    const token = getToken();
    if (!token) {
      console.warn('Token fehlt für Mode-Update');
      return;
    }
    
    const r = await fetch('/api/config/llm-mode', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ mode, env_vars: envVars })
    });
    
    if (!r.ok) {
      console.warn(`LLM Mode update: ${r.status}`);
      return;
    }
    
    const data = await r.json();
    console.log(`✓ LLM Mode geändert: ${mode}`);
    
    // Show toast: terminal restart needed
    showToast(`✓ ${mode} aktiv. Terminal neustarten (Ctrl+D → Neu), damit es greift.`);
  } catch (e) {
    console.warn('LLM Mode update fehlgeschlagen:', e);
  }
}

async function viewModels() {
  try {
    $('#view-title').textContent = '⚙ Ausführungs-Modi';
    $('#view-sub').textContent = 'Wähle die Orchestrierungs-Strategie für Workflows';
    $('#stats').innerHTML = '';
    const c = $('#content'); c.innerHTML = '';

    const pane = el(`<div class="models-panel">`);

  // ═════════════════════════════════════════════════════════════════════
  // MODE SELECTION: 3 Modes für LLM-Orchestrierung
  // ═════════════════════════════════════════════════════════════════════
  const modesDiv = el(`<div class="modes-panel" style="background: var(--tm-bg); border-radius: 8px; padding: 2rem; margin-bottom: 2rem;">
    <h2 style="margin-top: 0; color: var(--tm-text);">Ausführungs-Modi</h2>
    <p style="color: var(--tm-faint); margin: 0 0 1.5rem 0;">
      Wie sollen Briefs, Pläne und Code-Reviews orchestriert werden?
    </p>
    
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem;">
      
      <!-- MODE 1: DEEPSEEK-MAX -->
      <label class="mode-card" style="cursor: pointer; border: 2px solid var(--tm-dim); border-radius: 6px; padding: 1rem; transition: all 0.2s;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
          <input type="radio" name="llm-mode" value="deepseek-max" style="width: 20px; height: 20px; cursor: pointer;">
          <span style="font-weight: bold; color: var(--tm-text); font-size: 16px;">⚡ DEEPSEEK-MAX</span>
        </div>
        <div style="margin-left: 32px; font-size: 14px; color: var(--tm-faint);">
          <div style="margin-bottom: 6px;"><strong>Alles lokal, 1 Modell</strong></div>
          <div>• Briefing: deepseek:6.7b</div>
          <div>• Planning: deepseek:6.7b</div>
          <div>• Execution: deepseek:6.7b</div>
          <div>• Code-Review: deepseek (Self-Review)</div>
          <div style="margin-top: 8px; color: var(--tm-accent);">✓ Schnell · Lokal · Memory-effizient</div>
        </div>
      </label>
      
      <!-- MODE 2: MITTE -->
      <label class="mode-card" style="cursor: pointer; border: 2px solid var(--tm-dim); border-radius: 6px; padding: 1rem; transition: all 0.2s;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
          <input type="radio" name="llm-mode" value="mitte" style="width: 20px; height: 20px; cursor: pointer;">
          <span style="font-weight: bold; color: var(--tm-text); font-size: 16px;">🎯 MITTE</span>
        </div>
        <div style="margin-left: 32px; font-size: 14px; color: var(--tm-faint);">
          <div style="margin-bottom: 6px;"><strong>Claude plant/reviewt, deepseek codet</strong></div>
          <div>• Briefing: Claude (API)</div>
          <div>• Planning: Claude (API)</div>
          <div>• Execution: deepseek:6.7b</div>
          <div>• Code-Review: Claude (API)</div>
          <div style="margin-top: 8px; color: var(--tm-accent);">✓ Hybrid · Qualität/Geschwindigkeit-Balance</div>
        </div>
      </label>
      
      <!-- MODE 3: DEFAULT -->
      <label class="mode-card" style="cursor: pointer; border: 2px solid var(--tm-dim); border-radius: 6px; padding: 1rem; transition: all 0.2s;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
          <input type="radio" name="llm-mode" value="default" style="width: 20px; height: 20px; cursor: pointer;">
          <span style="font-weight: bold; color: var(--tm-text); font-size: 16px;">🚀 DEFAULT</span>
        </div>
        <div style="margin-left: 32px; font-size: 14px; color: var(--tm-faint);">
          <div style="margin-bottom: 6px;"><strong>Claude codet, deepseek validator</strong></div>
          <div>• Briefing: Claude (API)</div>
          <div>• Planning: Claude (API)</div>
          <div>• Execution: Claude (API)</div>
          <div>• Code-Review: deepseek (lokal)</div>
          <div style="margin-top: 8px; color: var(--tm-accent);">✓ Frontier-Qualität · API-abhängig</div>
        </div>
      </label>
      
    </div>
  </div>`);
  
  pane.appendChild(modesDiv);
  
  // Mode-Selection Handler
  modesDiv.querySelectorAll('input[name="llm-mode"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
      const selectedMode = e.target.value;
      // Update ENV via /api/config endpoint (falls verfügbar)
      updateLLMMode(selectedMode).catch(err => {
        console.warn('LLM Mode update fehlgeschlagen:', err);
        // Optional: Toast-Nachricht?
      });
      
      // Visuelle Rückmeldung: Hervorheben der ausgewählten Card
      modesDiv.querySelectorAll('.mode-card').forEach(card => {
        const radio = card.querySelector('input[name="llm-mode"]');
        if (radio.checked) {
          card.style.borderColor = 'var(--tm-accent)';
          card.style.backgroundColor = 'rgba(95, 137, 167, 0.05)';
        } else {
          card.style.borderColor = 'var(--tm-dim)';
          card.style.backgroundColor = 'transparent';
        }
      });
    });
  });

  // Aktuell persistierten Modus laden + reflektieren (Fix: zeigte immer DEFAULT).
  const applyModeHighlight = () => {
    modesDiv.querySelectorAll('.mode-card').forEach(card => {
      const r = card.querySelector('input[name="llm-mode"]');
      card.style.borderColor = r.checked ? 'var(--tm-accent)' : 'var(--tm-dim)';
      card.style.backgroundColor = r.checked ? 'rgba(95, 137, 167, 0.05)' : 'transparent';
    });
  };
  fetch('/api/config/llm-mode')
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      const mode = (data && data.mode) || 'default';
      const radio = modesDiv.querySelector(`input[name="llm-mode"][value="${mode}"]`);
      if (radio) radio.checked = true;
      applyModeHighlight();
    })
    .catch(() => applyModeHighlight());

  // Privacy-Level Radio-Buttons (behalten)
  const privacyDiv = el(`<div class="privacy-panel">
    <h3>Privacy-Level</h3>
    <label><input type="radio" name="privacy" value="auto" checked> Auto</label>
    <label><input type="radio" name="privacy" value="public"> Public</label>
    <label><input type="radio" name="privacy" value="internal"> Internal</label>
    <label><input type="radio" name="privacy" value="secret"> Secret</label>
    <label><input type="radio" name="privacy" value="substrat"> Substrat-Pass</label>
  </div>`);
  pane.appendChild(privacyDiv);

  // Radio-Handler für Privacy
  privacyDiv.querySelectorAll('input[name="privacy"]').forEach(r =>
    r.addEventListener('change', async () => {
      try {
        await setPrivacyLevel(r.value);
      } catch (e) {
        alert('Fehler: ' + e.message);
      }
    })
  );

    c.appendChild(pane);
  } catch (e) {
    $('#content').innerHTML = `<div class="empty">Fehler: ${esc(e.message)}</div>`;
  }
}

// ── Router ──────────────────────────────────────────────────────────────
async function render() {
  document.querySelectorAll('.navbtn').forEach(b => b.classList.toggle('is-active', b.dataset.view === state.view));
  if (state.view === 'terminal') {
    try { await loadHealth(); } catch {}   // Sidebar-Pills best-effort, Terminal hängt nicht dran
    return viewTerminal();
  }
  // andere Sicht: Terminal-Pane nur verstecken (Session bleibt am Leben), Content zeigen
  const tp = $('#term-pane'); if (tp) tp.classList.add('hidden');
  $('#content').classList.remove('hidden');
  try {
    const h = await loadHealth();
    renderStats(h);
    if (state.view === 'workflows') {
      if (state.detailId) await viewWorkflowDetail(state.detailId);
      else await viewWorkflows();
    } else if (state.view === 'knowledge') {
      await viewKnowledge();
    } else if (state.view === 'models') {
      await viewModels();
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
startModelStatusUpdates();  // Live model status in sidebar
