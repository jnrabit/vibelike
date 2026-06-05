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
  $('#view-sub').textContent = 'ossifikat-Staging · Kandidaten warten auf Ratifizierung';
  const { triples } = await getJSON('/api/ossifikat/staging');
  const c = $('#content'); c.innerHTML = '';
  if (!triples.length) { c.appendChild(el('<div class="empty">Kein Staging. Brücken erzeugen via experiments/bridges_to_ossifikat.py</div>')); return; }
  for (const t of triples) {
    c.appendChild(el(`<div class="triple">
      <div class="triple__edge"><span class="s">${esc(t.subject)}</span><span class="p">—[${esc(t.predicate)}]→</span><span class="o">${esc(t.object)}</span></div>
      ${t.rationale ? `<div class="triple__rat">↳ ${esc(t.rationale)}</div>` : ''}
      <div class="triple__foot"><span>#${esc(t.id)}</span><span>conf ${esc(t.confidence)}</span><span>${esc(t.source)}</span><span>${esc((t.created_at||'').slice(0,19))}</span></div>
    </div>`));
  }
}

// ── Router ──────────────────────────────────────────────────────────────
async function render() {
  document.querySelectorAll('.navbtn').forEach(b => b.classList.toggle('is-active', b.dataset.view === state.view));
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
