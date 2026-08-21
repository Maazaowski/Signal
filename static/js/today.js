/* Today — a briefing, not a dashboard.
   The lead sentence answers "is there anything for me right now?" before any
   number appears, because that is the only question this page exists to answer. */

let watcher = null;

// ── The lead ──────────────────────────────────────────────────

async function loadLede() {
  try {
    const [stats, intros, companies] = await Promise.all([
      api('/stats'), api('/outreach/stats'), api('/companies/stats'),
    ]);

    const open = (stats.by_location_fit || {}).yes || 0;
    const maybe = (stats.by_location_fit || {}).maybe || 0;
    const ready = (intros.by_status || {}).pending || 0;
    const total = stats.total || 0;

    let lede;
    if (!total) {
      lede = `Nothing collected yet. Run <em>Find roles</em> and this page will fill in.`;
    } else if (ready) {
      lede = `<strong>${fmt.num(ready)}</strong> ${ready === 1 ? 'intro is' : 'intros are'} written and waiting to go out.`;
    } else if (open) {
      lede = `<strong>${fmt.num(open)}</strong> of ${fmt.num(total)} roles collected are open to you.`;
    } else {
      lede = `${fmt.num(total)} roles collected, but none are open to your location yet.`;
    }
    $('#lede').innerHTML = lede;

    const crawlable = (companies.by_status || {}).active || 0;
    const parts = [
      `${fmt.num(total)} collected`,
      `${fmt.num(open)} open`,
      `${fmt.num(maybe)} possible`,
      `${fmt.num(crawlable)} of ${fmt.num(companies.total || 0)} company boards active`,
    ];
    $('#lede-detail').innerHTML = parts
      .map(p => `<span>${text(p)}</span>`).join('<span class="sep">·</span>');

    const d = $('#date-line');
    if (d) d.textContent = new Date().toLocaleDateString(undefined,
      { weekday: 'long', day: 'numeric', month: 'long' });
  } catch (e) {
    $('#lede').innerHTML = `<span class="quiet">Couldn't read the summary — ${text(e.message)}</span>`;
  }
}

// ── Shortlist ─────────────────────────────────────────────────

async function loadShortlist() {
  setHtml('#shortlist', ghostEntries(4));
  try {
    const d = await api('/jobs?min_score=45&location_fit=maybe&limit=6');
    if (!d.jobs.length) {
      setHtml('#shortlist', blank({
        glyph: 'roles',
        title: 'Nothing to read yet',
        body: 'When a run finds roles that fit and are open to your location, the best of them appear here.',
        action: `<button class="btn btn-primary" onclick="document.getElementById('btn-find').click()">
                   ${icon('search', 'ico ico-sm')} Find roles</button>`,
      }));
      $('#shortlist-note').textContent = '';
      return;
    }
    $('#shortlist-note').textContent = `${d.jobs.length} scoring 45 or better`;
    setHtml('#shortlist', d.jobs.map(j => `
      <div class="entry" data-role="${escapeHtml(j.id)}">
        <div>${score(j.relevance_score)}</div>
        <div>
          <div class="entry-title">${text(j.title)}</div>
          <div class="entry-meta">
            <span>${text(j.company)}</span>
            ${j.location ? `<span class="sep">·</span><span>${text(j.location)}</span>` : ''}
            ${j.salary ? `<span class="sep">·</span><span>${text(j.salary)}</span>` : ''}
          </div>
        </div>
        <div class="entry-aside">${fitTag(j.location_fit, j.location_note)}</div>
      </div>`).join(''));
    $$('#shortlist [data-role]').forEach(el =>
      el.onclick = () => location.href = `/roles?role=${encodeURIComponent(el.dataset.role)}`);
  } catch (e) {
    setHtml('#shortlist', failed(e.message, loadShortlist));
  }
}

// ── Side panels ───────────────────────────────────────────────

function renderNextRun(s) {
  const sc = s.scheduler || {};
  if (!sc.enabled) {
    setHtml('#next-run', `
      <p class="subdued">Automatic runs are turned off.</p>
      <a class="btn btn-sm" href="/settings" style="margin-top:var(--s3)">
        ${icon('settings', 'ico ico-sm')} Turn them on</a>`);
    return;
  }
  const next = sc.next_run;
  setHtml('#next-run', `
    <div class="figure">
      <span class="figure-n" style="font-size:var(--t-xl)">${next ? text(fmt.until(next.iso)) : '—'}</span>
      <span class="figure-l">${next ? text(next.display) : 'nothing scheduled'}</span>
    </div>
    <div class="facts" style="margin-top:var(--s4)">
      <div class="fact"><span class="fact-k">Every day at</span>
        <span class="fact-v">${text(sc.hour)}:00 ${text(String(sc.timezone).split('/').pop().replace('_',' '))}</span></div>
      <div class="fact"><span class="fact-k">Sends to</span>
        <span class="fact-v">${s.email.recipient ? text(s.email.recipient) : '<span class="quiet">nobody yet</span>'}</span></div>
    </div>`);
}

function renderAllowance(s) {
  const q = s.jsearch || {};
  if (!q.configured) {
    setHtml('#allowance', `
      <p class="subdued">No search key, so results come only from the free boards
      and company career pages.</p>
      <a class="btn btn-sm" href="/settings" style="margin-top:var(--s3)">
        ${icon('plus', 'ico ico-sm')} Add a key</a>`);
    return;
  }
  const pct = q.limit ? Math.min(100, Math.round(q.used_this_month / q.limit * 100)) : 0;
  const tone = pct >= 90 ? 'critical' : pct >= 70 ? 'caution' : '';
  setHtml('#allowance', `
    <div class="split">
      <div class="figure">
        <span class="figure-n ${tone}" style="font-size:var(--t-xl)">${fmt.num(q.remaining)}</span>
        <span class="figure-l">searches left this month</span>
      </div>
    </div>
    <div class="meter" style="margin-top:var(--s4)">
      <div class="meter-fill ${tone}" style="width:${pct}%"></div>
    </div>
    <p class="figure-l" style="margin-top:var(--s3)">
      ${fmt.num(q.used_this_month)} of ${fmt.num(q.limit)} used${q.used_today ? `, ${q.used_today} today` : ''}</p>`);
}

// ── Activity ──────────────────────────────────────────────────

function runSummary(r) {
  const s = r.stats || {};
  if (r.status === 'failed') return text((r.error || 'failed').split(':')[0]);
  const bits = [];
  if (s.new !== undefined) bits.push(`${fmt.num(s.new)} new`);
  if (s.detected !== undefined) bits.push(`${s.detected} boards found`);
  if (s.added !== undefined) bits.push(`${fmt.num(s.added)} added`);
  if (s.generated !== undefined) bits.push(`${s.generated} intros`);
  if (s.updated !== undefined && s.scanned !== undefined) bits.push(`${fmt.num(s.updated)} rescored`);
  return bits.join(', ') || '—';
}

async function loadRecent() {
  try {
    const d = await api('/runs?limit=5');
    window.__kinds = d.kinds;
    if (!d.runs.length) {
      setHtml('#recent', blank({
        glyph: 'activity', title: 'Nothing has run yet',
        body: 'Runs started here or on a schedule are listed with what they found.',
      }));
      return;
    }
    setHtml('#recent', `<div class="tl">${d.runs.map(r => `
      <div class="tl-item ${r.status === 'success' ? 'ok' : r.status === 'failed' ? 'bad' : r.status === 'running' ? 'live' : ''}"
           data-run="${r.id}">
        <div class="split">
          <span class="tl-title">${text(runName(r.kind))}</span>
          <span class="quiet" style="font-size:var(--t-sm)">${text(fmt.ago(r.started_at || r.queued_at))}</span>
        </div>
        <div class="quiet" style="font-size:var(--t-sm)">
          ${text(runSummary(r))}${r.trigger === 'schedule' ? ' · on schedule' : ''}
        </div>
      </div>`).join('')}</div>`);
    $$('#recent [data-run]').forEach(el =>
      el.onclick = () => location.href = `/activity?run=${el.dataset.run}`);
  } catch (e) {
    setHtml('#recent', failed(e.message, loadRecent));
  }
}

// ── Runs ──────────────────────────────────────────────────────

function renderLive(run) {
  const host = $('#live');
  if (!run) { host.innerHTML = ''; return; }
  const total = run.progress_total || 0, cur = run.progress_current || 0;
  const pct = total ? Math.round(cur / total * 100) : 0;
  host.innerHTML = `
    <div class="panel">
      <div class="panel-bd">
        <div class="split" style="margin-bottom:var(--s3)">
          <div class="row">
            ${runTag(run.status)}
            <strong>${text(runName(run.kind))}</strong>
            <span class="quiet">${text(run.progress_label || 'starting')}</span>
          </div>
          <div class="row">
            <span class="quiet nums">${total ? `${cur} of ${total}` : ''}</span>
            <a href="/activity" class="btn btn-sm">Watch</a>
          </div>
        </div>
        <div class="meter"><div class="meter-fill ${total ? '' : 'unknown'}"
             style="width:${total ? pct : 32}%"></div></div>
      </div>
    </div>`;
}

async function start(kind, btn, opts = {}) {
  try {
    const res = await withBusy(btn, 'Starting', () =>
      api('/runs', { method: 'POST', body: { kind, ...opts } }));
    $('#live').dataset.busy = '1';
    renderLive({ id: res.run_id, kind, status: 'queued',
                 progress_current: 0, progress_total: 0, progress_label: 'queued' });
    toast(`${runName(kind)} started`, 'ok');
    watch();
  } catch (e) { /* withBusy already reported it */ }
}

function watch() {
  if (watcher && !watcher.stopped) return;
  let wasRunning = false;
  watcher = poll(async () => {
    const d = await api('/runs?limit=5');
    window.__kinds = d.kinds;

    if (d.active) {
      renderLive(d.active);
      wasRunning = true;
      return true;
    }

    if (wasRunning) {
      wasRunning = false;
      // Hold the finished run on screen for a moment instead of clearing it
      // the instant it completes. A short run would otherwise flash and vanish,
      // leaving no trace of what just happened.
      delete $('#live').dataset.busy;
      const done = d.runs[0];
      if (done) {
        renderLive({ ...done, progress_label: runSummary(done) });
        setTimeout(() => { if (!$('#live').dataset.busy) renderLive(null); }, 6000);
      } else {
        renderLive(null);
      }
      const last = d.runs[0];
      if (last) toast(last.status === 'success'
        ? `${runName(last.kind)} finished — ${runSummary(last)}`
        : `${runName(last.kind)} ${RUN_STATE[last.status]?.label.toLowerCase() || last.status}`,
        last.status === 'success' ? 'ok' : 'error', 8000);
      await Promise.all([loadLede(), loadShortlist(), loadRecent()]);
    }
    return true;
  }, 1500);
}

document.addEventListener('system', e => {
  renderNextRun(e.detail);
  renderAllowance(e.detail);
  if (e.detail.active_run) renderLive(e.detail.active_run);
});

document.addEventListener('DOMContentLoaded', () => {
  $('#btn-find').onclick = function () { start('collect', this); };
  $('#btn-full').onclick = function () { start('pipeline', this, { send: true }); };
  loadLede();
  loadShortlist();
  loadRecent();
  watch();
  wired();
});
