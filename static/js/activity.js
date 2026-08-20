/* Activity — what is running, what finished, what failed and why.
   The point of this page is that none of that ever requires reading a console. */

const act = { kinds: {}, liveId: null, lastLog: 0, watcher: null, paused: false };

function logLines(entries) {
  if (!entries.length) return '<span class="quiet">Nothing yet.</span>';
  return entries.map(l => {
    const at = (l.ts || '').slice(11, 19);
    const cls = l.level === 'warn' ? 'warn' : l.level === 'error' ? 'error' : '';
    return `<div class="ln ${cls}"><span class="at">${text(at)}</span><span>${text(l.message)}</span></div>`;
  }).join('');
}

/** Only autoscroll if already at the bottom, so reading scrollback is not
 *  yanked away on every poll. */
function follow(el) {
  if (!el) return;
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 44) el.scrollTop = el.scrollHeight;
}

function outcome(r) {
  const s = r.stats || {};
  if (r.status === 'failed') return text((r.error || 'failed').split('\n')[0].slice(0, 90));
  const bits = [];
  if (s.new !== undefined) bits.push(`${fmt.num(s.new)} new`);
  if (s.fetched !== undefined && s.new === undefined) bits.push(`${fmt.num(s.fetched)} found`);
  if (s.companies_crawled) bits.push(`${s.companies_crawled} companies`);
  if (s.detected !== undefined) bits.push(`${s.detected} of ${s.checked} boards found`);
  if (s.added !== undefined) bits.push(`${fmt.num(s.added)} added`);
  if (s.generated !== undefined) bits.push(`${s.generated} intros`);
  if (s.updated !== undefined && s.scanned !== undefined) bits.push(`${fmt.num(s.updated)} rescored`);
  if (s.sent !== undefined) bits.push(s.sent ? 'digest sent' : 'not sent');
  if (s.skipped) bits.push('skipped');
  return bits.join(', ');   // empty means 'nothing worth reporting'
}

// ── Live ──────────────────────────────────────────────────────

async function renderLive(run) {
  const panel = $('#live-panel');
  if (!run) {
    panel.hidden = true;
    act.liveId = null; act.lastLog = 0;
    return;
  }
  panel.hidden = false;
  if (act.liveId !== run.id) { act.liveId = run.id; act.lastLog = 0; $('#live-log').innerHTML = ''; }

  const total = run.progress_total || 0, cur = run.progress_current || 0;
  const pct = total ? Math.round(cur / total * 100) : 0;

  $('#live-tag').innerHTML = runTag(run.status);
  $('#live-what').textContent = `${runName(run.kind)} — ${run.progress_label || 'starting'}`;
  $('#live-count').textContent = total ? `${cur} of ${total}` : fmt.duration(run.started_at);
  const bar = $('#live-bar');
  bar.className = 'meter-fill' + (total ? '' : ' unknown');
  bar.style.width = (total ? pct : 32) + '%';

  try {
    const d = await api(`/runs/${run.id}/logs?after_id=${act.lastLog}`);
    if (d.logs.length) {
      act.lastLog = d.last_id;
      const el = $('#live-log');
      el.insertAdjacentHTML('beforeend', logLines(d.logs));
      follow(el);
    }
  } catch {}
}

// ── History ───────────────────────────────────────────────────

async function loadHistory() {
  const state = $('#f-state').value;
  try {
    const d = await api('/runs?limit=40' + (state ? `&status=${state}` : ''));
    act.kinds = d.kinds;
    window.__kinds = d.kinds;

    if (!d.runs.length) {
      setHtml('#history', blank({
        glyph: 'activity',
        title: state ? 'Nothing with that outcome' : 'Nothing has run yet',
        body: state ? '' : 'Use Run above to start something. Scheduled runs are listed here too.',
      }));
      return;
    }

    setHtml('#history', `<div class="tl">${d.runs.map(r => `
      <div class="tl-item ${r.status === 'success' ? 'ok' : r.status === 'failed' ? 'bad'
                            : ['running','queued'].includes(r.status) ? 'live' : ''}"
           data-run="${r.id}">
        <div class="split">
          <span class="tl-title">${text(runName(r.kind))}</span>
          <span class="row" style="gap:var(--s2)">
            ${r.trigger === 'schedule' ? '<span class="tag">scheduled</span>' : ''}
            ${runTag(r.status)}
          </span>
        </div>
        <div class="quiet" style="font-size:var(--t-sm);margin-top:2px">
          ${outcome(r) ? `${text(outcome(r))}<span class="sep">·</span>` : ''}${text(fmt.ago(r.started_at || r.queued_at))}
          ${r.finished_at ? `<span class="sep">·</span>took ${text(fmt.duration(r.started_at, r.finished_at))}` : ''}
        </div>
      </div>`).join('')}</div>`);

    $$('#history [data-run]').forEach(el => el.onclick = () => openRun(el.dataset.run));
  } catch (e) {
    setHtml('#history', failed(e.message, loadHistory));
  }
}

async function openRun(id) {
  openPanel('run-pane');
  setHtml('#rd-body', '<div class="ghost" style="width:66%;height:14px"></div>');
  try {
    const [run, logs] = await Promise.all([api(`/runs/${id}`), api(`/runs/${id}/logs?limit=1000`)]);
    $('#rd-title').textContent = runName(run.kind);
    $('#rd-sub').textContent =
      `Run ${run.id} · ${run.trigger === 'schedule' ? 'on schedule' : 'started by you'} · ${fmt.date(run.started_at || run.queued_at, true)}`;

    const facts = Object.entries(run.stats || {})
      .filter(([, v]) => typeof v !== 'object')
      .map(([k, v]) => `<div class="fact"><span class="fact-k">${text(k.replace(/_/g, ' '))}</span>
                        <span class="fact-v nums">${text(v)}</span></div>`).join('');

    const per = (run.stats || {}).sources || (run.stats || {}).board_sources;
    const perRows = per ? Object.entries(per)
      .map(([k, v]) => `<div class="fact"><span class="fact-k mono">${text(k)}</span>
                        <span class="fact-v nums">${text(v)}</span></div>`).join('') : '';

    setHtml('#rd-body', `
      <div class="row" style="margin-bottom:var(--s5)">
        ${runTag(run.status)}
        <span class="quiet">took ${text(fmt.duration(run.started_at, run.finished_at))}</span>
      </div>

      ${run.error ? `<div class="notice notice-critical" style="margin-bottom:var(--s5)">
        ${icon('alert')}
        <div><strong>This run failed</strong>
        <div class="mono" style="white-space:pre-wrap;margin-top:var(--s2)">${text(run.error)}</div></div>
      </div>` : ''}

      <div class="eyebrow" style="margin-bottom:var(--s2)">What it did</div>
      <div class="facts">${facts || '<div class="quiet">Nothing recorded.</div>'}</div>

      ${perRows ? `<div class="eyebrow" style="margin:var(--s6) 0 var(--s2)">By source</div>
                   <div class="facts">${perRows}</div>` : ''}

      <div class="eyebrow" style="margin:var(--s6) 0 var(--s2)">Log</div>
      <div class="log">${logLines(logs.logs)}</div>`);
  } catch (e) {
    setHtml('#rd-body', failed(e.message));
  }
}

// ── Side panels ───────────────────────────────────────────────

function renderSystem(s) {
  act.paused = !s.scheduler.enabled || !s.scheduler.running;
  const next = s.scheduler.next_run;

  $('#sched-tag').innerHTML = s.scheduler.enabled && s.scheduler.running
    ? '<span class="tag tag-good"><span class="pip"></span>On</span>'
    : '<span class="tag tag-caution"><span class="pip"></span>Paused</span>';

  setHtml('#sched', `
    <div class="figure">
      <span class="figure-n" style="font-size:var(--t-xl)">${next ? text(fmt.until(next.iso)) : '—'}</span>
      <span class="figure-l">${next ? text(next.display) : 'nothing scheduled'}</span>
    </div>
    <div class="facts" style="margin-top:var(--s4)">
      <div class="fact"><span class="fact-k">Every day at</span>
        <span class="fact-v">${text(s.scheduler.hour)}:00 ${text(s.scheduler.timezone)}</span></div>
      <div class="fact"><span class="fact-k">It does</span>
        <span class="fact-v">Find roles, write intros, send digest</span></div>
    </div>`);

  $('#btn-sched').textContent = act.paused ? 'Resume' : 'Pause';

  const yes = '<span class="tag tag-good">Running</span>';
  const no = '<span class="tag tag-critical">Stopped</span>';
  setHtml('#services', `
    <div class="facts">
      <div class="fact"><span class="fact-k">Scheduler</span><span class="fact-v">${s.scheduler.running ? yes : no}</span></div>
      <div class="fact"><span class="fact-k">Worker</span><span class="fact-v">${s.worker.alive ? yes : no}</span></div>
      <div class="fact"><span class="fact-k">Search API</span><span class="fact-v">${
        s.jsearch.configured
          ? `<span class="tag tag-good">Connected</span>`
          : '<span class="tag tag-caution">No key</span>'}</span></div>
      <div class="fact"><span class="fact-k">Email</span><span class="fact-v">${
        s.email.sender_configured ? '<span class="tag tag-good">Ready</span>'
                                  : '<span class="tag tag-caution">Not set up</span>'}</span></div>
      <div class="fact"><span class="fact-k">Database</span>
        <span class="fact-v quiet">${text(fmt.bytes(s.database.size_bytes))}, ${fmt.num(s.database.jobs)} roles</span></div>
      <div class="fact"><span class="fact-k">Running since</span>
        <span class="fact-v quiet">${text(fmt.ago(s.started_at))}</span></div>
    </div>`);

  const w = $('#act-where');
  if (w) w.textContent = s.active_run ? 'something is running'
    : (next ? `next run ${fmt.until(next.iso)}` : '');
}

async function loadSends() {
  try {
    const d = await api('/email/log?limit=8');
    if (!d.sends.length) {
      setHtml('#sends', blank({
        glyph: 'intros', title: 'No digests yet',
        body: 'The daily run emails your shortlist once intros are written.',
      }));
      return;
    }
    setHtml('#sends', `<div class="facts">${d.sends.map(s => `
      <div class="fact">
        <span class="fact-k">${text(fmt.date(s.sent_at, true))}</span>
        <span class="fact-v">${s.status === 'sent'
          ? `${fmt.num(s.items_count)} roles`
          : `<span class="tag tag-critical" title="${escapeHtml(s.error || '')}">${text(s.status)}</span>`}</span>
      </div>`).join('')}</div>`);
  } catch (e) {
    setHtml('#sends', failed(e.message, loadSends));
  }
}

async function loadAppLog() {
  try {
    const d = await api('/logs?limit=140');
    const el = $('#app-log');
    el.innerHTML = logLines(d.logs);
    follow(el);
  } catch {}
}

// ── Runs ──────────────────────────────────────────────────────

function watch() {
  if (act.watcher && !act.watcher.stopped) return;
  let wasRunning = false;
  act.watcher = poll(async () => {
    const state = $('#f-state').value;
    const d = await api('/runs?limit=40' + (state ? `&status=${state}` : ''));
    act.kinds = d.kinds; window.__kinds = d.kinds;
    await renderLive(d.active);

    if (d.active) { wasRunning = true; loadAppLog(); }
    else if (wasRunning) {
      wasRunning = false;
      await Promise.all([loadHistory(), loadSends(), loadAppLog()]);
      const last = d.runs[0];
      if (last) toast(`${runName(last.kind)} — ${outcome(last)}`,
        last.status === 'success' ? 'ok' : 'error', 8000);
    }
    return true;               // always monitoring; this page is the watchpost
  }, 1200);
}

document.addEventListener('system', e => renderSystem(e.detail));

document.addEventListener('DOMContentLoaded', () => {
  $('#btn-run').onclick = async function () {
    const kind = $('#run-kind').value;
    try {
      await withBusy(this, 'Starting', () => api('/runs', { method: 'POST', body: { kind } }));
      toast(`${runName(kind)} started`, 'ok');
      watch();
    } catch {}
  };

  $('#btn-stop').onclick = async function () {
    if (!act.liveId) return;
    try {
      await withBusy(this, 'Stopping', () => api(`/runs/${act.liveId}/cancel`, { method: 'POST' }));
      toast('Stopping', 'warn');
    } catch {}
  };

  $('#btn-sched').onclick = async function () {
    try {
      await withBusy(this, '…', () => api('/settings',
        { method: 'PUT', body: { schedule_enabled: act.paused } }));
      toast(act.paused ? 'Automatic runs resumed' : 'Automatic runs paused', 'ok');
    } catch {}
  };

  $('#f-state').onchange = loadHistory;

  loadHistory();
  loadSends();
  loadAppLog();
  watch();

  const wanted = new URLSearchParams(location.search).get('run');
  if (wanted) openRun(wanted);
  wired();
});
