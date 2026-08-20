/* Roles — a reading list.
   Rows are typographic rather than a data grid: you scan titles, not cells.
   Everything else lives in the detail pane. */

const view = { offset: 0, per: 40, watcher: null };

function params() {
  const p = new URLSearchParams({ limit: String(view.per), offset: String(view.offset) });
  const q = $('#f-q').value.trim();
  const open = $('#f-open').value;
  const min = $('#f-score').value;
  const state = $('#f-state').value;
  const src = $('#f-src').value;
  if (q) p.set('search', q);
  if (open) p.set('india_friendly', open);
  if (min && min !== '0') p.set('min_score', min);
  if (state) p.set('status', state);
  if (src) p.set('source', src);
  return p;
}

const filtered = () =>
  $('#f-q').value.trim() || $('#f-state').value || $('#f-src').value ||
  $('#f-open').value !== 'maybe' || $('#f-score').value !== '45';

async function load() {
  setHtml('#roles', ghostEntries(6));
  try {
    const d = await api('/jobs?' + params());

    if (!d.jobs.length) {
      setHtml('#roles', blank({
        glyph: 'roles',
        title: filtered() ? 'Nothing matches those filters' : 'No roles yet',
        body: filtered()
          ? 'Try a lower minimum score, or widen availability to Everything.'
          : 'Run a search and roles from the free boards, your search key and your company list appear here.',
        action: filtered()
          ? `<button class="btn" onclick="clearFilters()">Clear filters</button>`
          : `<button class="btn btn-primary" onclick="document.getElementById('btn-find').click()">
               ${icon('search', 'ico ico-sm')} Find roles</button>`,
      }));
      $('#roles-count').textContent = '';
      $('#btn-back').disabled = view.offset === 0;
      $('#btn-more').disabled = true;
      return;
    }

    setHtml('#roles', d.jobs.map(j => `
      <div class="entry" data-role="${escapeHtml(j.id)}">
        <div>${score(j.relevance_score)}</div>
        <div>
          <div class="entry-title">${text(j.title)}</div>
          <div class="entry-meta">
            <span>${text(j.company)}</span>
            ${j.location ? `<span class="sep">·</span><span>${text(j.location)}</span>` : ''}
            ${j.salary ? `<span class="sep">·</span><span>${text(j.salary)}</span>` : ''}
            <span class="sep">·</span><span>${text(fmt.ago(j.last_seen || j.discovered_at))}</span>
            ${j.status && j.status !== 'new' ? `<span class="sep">·</span><span>${text(j.status)}</span>` : ''}
            ${j.mark_for_email ? `<span class="sep">·</span><span>in digest</span>` : ''}
          </div>
        </div>
        <div class="entry-aside">${fitTag(j.india_friendly, j.location_note)}</div>
      </div>`).join(''));

    $$('#roles [data-role]').forEach(el => el.onclick = () => openRole(el.dataset.role));

    const from = view.offset + 1, to = view.offset + d.jobs.length;
    $('#roles-count').textContent = `Showing ${from}–${to}`;
    $('#roles-where').textContent = `${to - from + 1} shown`;
    $('#btn-back').disabled = view.offset === 0;
    $('#btn-more').disabled = d.jobs.length < view.per;
  } catch (e) {
    setHtml('#roles', failed(e.message, load));
  }
}

// Marking a role puts it at the top of the next digest — get_unemailed_outreach
// orders by mark_for_email before score. The button reports the state it is in,
// not the action, so it reads the same as the row's "in digest" marker.
function digestButton(on) {
  return `<button class="btn btn-sm ${on ? 'btn-primary' : ''}" data-digest>
            ${on ? icon('check', 'ico ico-sm') + ' In digest' : 'Send in digest'}
          </button>`;
}


function wireDigest(id) {
  const b = $('#rp-foot [data-digest]');
  if (!b) return;
  b.onclick = async () => {
    try {
      const r = await withBusy(b, '…', () =>
        api(`/jobs/${encodeURIComponent(id)}/mark-for-email`, { method: 'POST' }));
      // Re-render in place rather than closing: this is a toggle, and seeing it
      // flip is the confirmation. The list behind it still needs refreshing.
      setHtml('#rp-digest', digestButton(r.mark_for_email));
      wireDigest(id);
      toast(r.mark_for_email ? 'Added to the next digest' : 'Removed from the digest',
            'ok', 2500);
      load();
    } catch {}
  };
}


async function openRole(id) {
  openPanel('role-pane');
  setHtml('#rp-body', `<div class="ghost" style="width:70%;height:14px"></div>
                       <div class="ghost" style="width:90%;margin-top:12px"></div>`);
  $('#rp-foot').innerHTML = '';
  try {
    const j = await api(`/jobs/${encodeURIComponent(id)}`);
    if (j.error) throw new Error(j.error);

    $('#rp-title').textContent = j.title;
    $('#rp-sub').textContent = [j.company, j.location].filter(Boolean).join(' · ');

    setHtml('#rp-body', `
      <div class="row wrap" style="margin-bottom:var(--s5)">
        ${fitTag(j.india_friendly, j.location_note)}
        <span class="tag">${text(j.source)}</span>
        <span class="tag">${text(j.experience_level || 'level unclear')}</span>
        ${j.salary ? `<span class="tag tag-good">${text(j.salary)}</span>` : ''}
        <span class="quiet push">Score ${text(j.relevance_score)}</span>
      </div>

      <div class="facts" style="margin-bottom:var(--s6)">
        ${j.location_note ? `<div class="fact"><span class="fact-k">Availability</span>
          <span class="fact-v">${text(j.location_note)}</span></div>` : ''}
        <div class="fact"><span class="fact-k">Posted</span>
          <span class="fact-v">${text(j.posted_date ? fmt.date(j.posted_date) : 'not stated')}</span></div>
        <div class="fact"><span class="fact-k">Last seen</span>
          <span class="fact-v">${text(fmt.ago(j.last_seen || j.discovered_at))}</span></div>
        ${j.tech_stack ? `<div class="fact"><span class="fact-k">Mentions</span>
          <span class="fact-v">${text(j.tech_stack)}</span></div>` : ''}
      </div>

      <div class="eyebrow" style="margin-bottom:var(--s3)">Description</div>
      <div style="white-space:pre-wrap;color:var(--ink-2);line-height:var(--lh-body)">${
        text(stripHtml(j.description)) || '<span class="quiet">No description was provided.</span>'}</div>`);

    $('#rp-foot').innerHTML = `
      <div class="btns">
        <button class="btn btn-sm" data-mark="reviewed">Mark read</button>
        <button class="btn btn-sm" data-mark="applied">Applied</button>
        <button class="btn btn-quiet btn-sm" data-mark="stale">Set aside</button>
        <span id="rp-digest">${digestButton(j.mark_for_email)}</span>
      </div>
      ${j.url ? `<a class="btn btn-primary btn-sm push" target="_blank" rel="noopener noreferrer"
          href="${escapeHtml(safeUrl(j.url))}">Open posting
          ${icon('external', 'ico ico-sm')}</a>` : ''}`;

    wireDigest(id);

    $$('#rp-foot [data-mark]').forEach(b => b.onclick = async () => {
      try {
        await withBusy(b, '…', () =>
          api(`/jobs/${encodeURIComponent(id)}/status?status=${b.dataset.mark}`, { method: 'PATCH' }));
        toast(`Marked ${b.dataset.mark === 'stale' ? 'set aside' : b.dataset.mark}`, 'ok', 2500);
        closePanel('role-pane');
        load();
      } catch {}
    });
  } catch (e) {
    setHtml('#rp-body', failed(e.message));
  }
}

async function loadSources() {
  try {
    const d = await api('/sources');
    $('#f-src').innerHTML = '<option value="">Any</option>' +
      d.sources.filter(Boolean).map(s =>
        `<option value="${escapeHtml(s)}">${text(s)}</option>`).join('');
  } catch {}
}

function clearFilters() {
  $('#f-q').value = ''; $('#f-open').value = 'maybe'; $('#f-score').value = '45';
  $('#f-state').value = ''; $('#f-src').value = '';
  view.offset = 0;
  load();
}

function renderLive(run) {
  const host = $('#live');
  if (!run) { host.innerHTML = ''; return; }
  const total = run.progress_total || 0, cur = run.progress_current || 0;
  host.innerHTML = `<div class="panel"><div class="panel-bd">
    <div class="split" style="margin-bottom:var(--s3)">
      <div class="row">${runTag(run.status)}<strong>${text(runName(run.kind))}</strong>
        <span class="quiet">${text(run.progress_label || 'starting')}</span></div>
      <span class="quiet nums">${total ? `${cur} of ${total}` : ''}</span>
    </div>
    <div class="meter"><div class="meter-fill ${total ? '' : 'unknown'}"
      style="width:${total ? Math.round(cur / total * 100) : 32}%"></div></div>
  </div></div>`;
}

function watch() {
  if (view.watcher && !view.watcher.stopped) return;
  let wasRunning = false;
  view.watcher = poll(async () => {
    const d = await api('/runs?limit=1');
    window.__kinds = d.kinds;
    renderLive(d.active);
    if (d.active) { wasRunning = true; return true; }
    if (wasRunning) {
      wasRunning = false;
      const last = d.runs[0];
      if (last) {
        const s = last.stats || {};
        toast(last.status === 'success'
          ? `Found ${fmt.num(s.new || 0)} new ${s.new === 1 ? 'role' : 'roles'}`
          : `${runName(last.kind)} ${last.status}`,
          last.status === 'success' ? 'ok' : 'error');
      }
      load(); loadSources();
    }
    return true;
  }, 1500);
}

document.addEventListener('system', e => { if (e.detail.active_run) renderLive(e.detail.active_run); });

document.addEventListener('DOMContentLoaded', () => {
  $('#btn-find').onclick = async function () {
    try {
      const res = await withBusy(this, 'Starting', () =>
        api('/runs', { method: 'POST', body: { kind: 'collect' } }));
      renderLive({ id: res.run_id, kind: 'collect', status: 'queued',
                   progress_current: 0, progress_total: 0, progress_label: 'queued' });
      toast('Looking for roles', 'ok');
      watch();
    } catch {}
  };

  $('#btn-export').onclick = async function () {
    try {
      const r = await withBusy(this, 'Exporting', () =>
        api('/export/sheets?' + params(), { method: 'POST' }));
      toast(r.error || `Exported ${r.rows || 0} rows`, r.error ? 'warn' : 'ok');
    } catch {}
  };

  $('#btn-clear').onclick = clearFilters;
  $('#btn-back').onclick = () => { view.offset = Math.max(0, view.offset - view.per); load(); };
  $('#btn-more').onclick = () => { view.offset += view.per; load(); };

  let t;
  $('#f-q').oninput = () => { clearTimeout(t); t = setTimeout(() => { view.offset = 0; load(); }, 350); };
  ['f-open', 'f-score', 'f-state', 'f-src'].forEach(id =>
    $('#' + id).onchange = () => { view.offset = 0; load(); });

  loadSources();
  load();
  watch();

  const wanted = new URLSearchParams(location.search).get('role');
  if (wanted) openRole(wanted);
  wired();
});
