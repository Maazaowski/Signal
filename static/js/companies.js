/* Companies — the job boards crawled directly, at no cost to your search allowance.
   The job this page must do well: make it obvious when a company cannot be
   crawled, and why. Companies arrive paused with no known board, and until that
   is resolved they contribute nothing — which is invisible everywhere else. */

const co = { rows: [], editing: null, watcher: null };

const BOARD = {
  greenhouse: 'Greenhouse', lever: 'Lever', ashby: 'Ashby',
  html: 'Career page', unknown: 'None found',
};

const boardTag = p =>
  `<span class="tag ${p && p !== 'unknown' ? 'tag-accent' : ''}">${text(BOARD[p] || p || 'None found')}</span>`;

const stateTag = s =>
  s === 'active' ? '<span class="tag tag-good">Being crawled</span>'
  : s === 'failed' ? '<span class="tag tag-critical">Failing</span>'
  : '<span class="tag">Paused</span>';

async function loadFigures() {
  try {
    const s = await api('/companies/stats');
    const total = s.total || 0;
    const active = (s.by_status || {}).active || 0;
    const none = (s.by_platform || {}).unknown || 0;
    const failing = (s.by_status || {}).failed || 0;

    setHtml('#co-figures', `
      <div class="panel"><div class="panel-bd"><div class="figure">
        <span class="figure-n ${active ? '' : 'caution'}">${fmt.num(active)}</span>
        <span class="figure-l">being crawled, of ${fmt.num(total)}</span></div></div></div>
      <div class="panel"><div class="panel-bd"><div class="figure">
        <span class="figure-n ${none ? 'caution' : ''}">${fmt.num(none)}</span>
        <span class="figure-l">with no job board found</span></div></div></div>
      <div class="panel"><div class="panel-bd"><div class="figure">
        <span class="figure-n ${failing ? 'critical' : ''}">${fmt.num(failing)}</span>
        <span class="figure-l">failing on the last crawl</span></div></div></div>`);

    const w = $('#co-where');
    if (w) w.textContent = total ? `${fmt.num(active)} of ${fmt.num(total)} active` : '';
    const nav = $('#tally-companies');
    if (nav) nav.textContent = total ? fmt.num(total) : '';

    // State the problem plainly, and name the button that resolves it.
    const notice = $('#board-notice');
    if (total && !active) {
      notice.innerHTML = `<div class="notice notice-caution">${icon('alert')}
        <div><strong>None of these ${fmt.num(total)} companies can be crawled yet</strong>
        They arrive paused because we don't yet know where they publish jobs.
        <strong>Find job boards</strong> checks each one for a Greenhouse, Lever or Ashby
        board; those that have one start contributing roles straight away.</div></div>`;
    } else if (none > 0) {
      notice.innerHTML = `<div class="notice notice-info">${icon('info')}
        <div><strong>${fmt.num(none)} companies have no job board we can read</strong>
        They are skipped when crawling. Run <strong>Find job boards</strong> to check them
        again, or add a career page to one directly.</div></div>`;
    } else {
      notice.innerHTML = '';
    }
  } catch (e) {
    setHtml('#co-figures', `<div class="panel"><div class="panel-bd">
      <span class="quiet">Couldn't read the summary — ${text(e.message)}</span></div></div>`);
  }
}

async function load() {
  const p = new URLSearchParams({ limit: '500' });
  const q = $('#f-q').value.trim();
  const board = $('#f-board').value;
  const state = $('#f-state').value;
  if (q) p.set('search', q);
  if (board) p.set('ats_platform', board);
  if (state) p.set('crawl_status', state);

  setHtml('#co-rows', ghostRows(6, 6));
  try {
    const d = await api('/companies?' + p);
    co.rows = d.companies;

    if (!d.companies.length) {
      const narrowed = q || board || state;
      setHtml('#co-rows', `<tr><td colspan="6">${blank({
        glyph: 'companies',
        title: narrowed ? 'Nothing matches those filters' : 'No companies yet',
        body: narrowed
          ? 'Try clearing the search or filters.'
          : 'Company job boards are read directly, so they cost nothing against your search allowance. Add the curated list to begin.',
        action: narrowed
          ? `<button class="btn" onclick="clearFilters()">Clear filters</button>`
          : `<button class="btn btn-primary" onclick="document.getElementById('btn-seed').click()">Add curated list</button>`,
      })}</td></tr>`);
      $('#co-count').textContent = '';
      return;
    }

    setHtml('#co-rows', d.companies.map(c => `
      <tr>
        <td><strong>${text(c.name)}</strong>
          ${c.domain ? `<div class="quiet mono">${text(c.domain)}</div>` : ''}</td>
        <td>${boardTag(c.ats_platform)}
          ${c.ats_slug ? `<div class="quiet mono">${text(c.ats_slug)}</div>` : ''}</td>
        <td>${stateTag(c.crawl_status)}</td>
        <td class="right nums quiet" data-roles="${escapeHtml(c.domain || '')}">—</td>
        <td class="quiet">${text(c.last_crawled ? fmt.ago(c.last_crawled) : 'never')}</td>
        <td class="right"><div class="btns">
          <button class="btn btn-sm" data-crawl="${escapeHtml(c.id)}"
            ${c.ats_platform === 'unknown'
              ? 'disabled title="No job board found for this company yet — run Find job boards"' : ''}>Crawl</button>
          <button class="btn btn-quiet btn-sm" data-edit="${escapeHtml(c.id)}">Edit</button>
          <button class="btn btn-quiet btn-sm" data-toggle="${escapeHtml(c.id)}"
            data-state="${escapeHtml(c.crawl_status)}">${c.crawl_status === 'active' ? 'Pause' : 'Resume'}</button>
        </div></td>
      </tr>`).join(''));

    $('#co-count').textContent = `${d.companies.length} compan${d.companies.length === 1 ? 'y' : 'ies'}`;
    wireRows();
    fillRoleCounts();
  } catch (e) {
    setHtml('#co-rows', `<tr><td colspan="6">${failed(e.message, load)}</td></tr>`);
  }
}

/** Role counts resolve lazily so the table paints immediately. */
async function fillRoleCounts() {
  const cells = $$('#co-rows td[data-roles]').filter(td => td.dataset.roles);
  for (const td of cells.slice(0, 60)) {
    try {
      const d = await api(`/jobs?company_domain=${encodeURIComponent(td.dataset.roles)}&limit=1&min_score=0`);
      td.textContent = d.count ? fmt.num(d.count) : '0';
      if (d.count) td.classList.remove('quiet');
    } catch { td.textContent = '—'; }
  }
}

function wireRows() {
  $$('#co-rows [data-crawl]').forEach(b => b.onclick = () =>
    start('crawl', b, { company_ids: [b.dataset.crawl] }));

  $$('#co-rows [data-edit]').forEach(b => b.onclick = () => {
    const c = co.rows.find(x => x.id === b.dataset.edit);
    if (c) openEditor(c);
  });

  $$('#co-rows [data-toggle]').forEach(b => b.onclick = async () => {
    const id = b.dataset.toggle;
    const isActive = b.dataset.state === 'active';
    try {
      await withBusy(b, '…', () => api(
        isActive ? `/companies/${encodeURIComponent(id)}` : `/companies/${encodeURIComponent(id)}/activate`,
        { method: isActive ? 'DELETE' : 'POST' }));
      toast(isActive ? 'Paused — it will be skipped when crawling' : 'Resumed', 'ok', 2500);
      load(); loadFigures();
    } catch {}
  });
}

// ── Editor ────────────────────────────────────────────────────

function openEditor(c) {
  co.editing = c ? c.id : null;
  $('#co-editor-title').textContent = c ? `Edit ${c.name}` : 'Add a company';
  $('#c-name').value = c ? c.name : '';
  $('#c-domain').value = c ? (c.domain || '') : '';
  $('#c-board').value = c ? (c.ats_platform || 'unknown') : 'unknown';
  $('#c-slug').value = c ? (c.ats_slug || '') : '';
  $('#c-careers').value = c ? (c.careers_url || '') : '';
  $('#c-tags').value = c ? (c.tags || '') : '';
  openPanel('co-editor');
}

async function save(btn) {
  const body = {
    name: $('#c-name').value.trim(),
    domain: $('#c-domain').value.trim(),
    ats_platform: $('#c-board').value,
    ats_slug: $('#c-slug').value.trim(),
    careers_url: $('#c-careers').value.trim(),
    tags: $('#c-tags').value.trim(),
  };
  if (!body.name) { toast('Give the company a name first', 'warn'); return; }
  try {
    await withBusy(btn, 'Saving', () => co.editing
      ? api(`/companies/${encodeURIComponent(co.editing)}`, { method: 'PATCH', body })
      : api('/companies', { method: 'POST', body }));
    toast('Saved', 'ok', 2500);
    closePanel('co-editor');
    load(); loadFigures();
  } catch {}
}

// ── Runs ──────────────────────────────────────────────────────

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

async function start(kind, btn, opts = {}) {
  try {
    const res = await withBusy(btn, 'Starting', () =>
      api('/runs', { method: 'POST', body: { kind, ...opts } }));
    renderLive({ id: res.run_id, kind, status: 'queued',
                 progress_current: 0, progress_total: 0, progress_label: 'queued' });
    toast(`${runName(kind)} started`, 'ok');
    watch();
  } catch {}
}

function watch() {
  if (co.watcher && !co.watcher.stopped) return;
  let wasRunning = false;
  co.watcher = poll(async () => {
    const d = await api('/runs?limit=1');
    window.__kinds = d.kinds;
    renderLive(d.active);
    if (d.active) { wasRunning = true; return true; }
    if (wasRunning) {
      wasRunning = false;
      const last = d.runs[0];
      if (last) {
        const s = last.stats || {};
        let msg = `${runName(last.kind)} ${last.status}`;
        if (last.status === 'success') {
          if (s.detected !== undefined)
            msg = `${s.detected} of ${s.checked} companies now have a readable job board`;
          else if (s.added !== undefined) msg = `${fmt.num(s.added)} companies added`;
          else if (s.new !== undefined)
            msg = `${fmt.num(s.new)} new roles from ${s.companies_crawled || 0} companies`;
        }
        toast(msg, last.status === 'success' ? 'ok' : 'error', 8000);
      }
      load(); loadFigures();
    }
    return true;
  }, 1500);
}

function clearFilters() {
  $('#f-q').value = ''; $('#f-board').value = ''; $('#f-state').value = '';
  load();
}

document.addEventListener('system', e => { if (e.detail.active_run) renderLive(e.detail.active_run); });

document.addEventListener('DOMContentLoaded', () => {
  $('#btn-seed').onclick    = function () { start('seed', this, { mega: true }); };
  $('#btn-detect').onclick  = function () { start('detect_ats', this, { only_unknown: true }); };
  $('#btn-crawl').onclick   = function () { start('crawl', this); };
  $('#btn-add').onclick     = () => openEditor(null);
  $('#btn-save-co').onclick = function () { save(this); };
  $('#btn-clear').onclick   = clearFilters;

  let t;
  $('#f-q').oninput = () => { clearTimeout(t); t = setTimeout(load, 350); };
  $('#f-board').onchange = load;
  $('#f-state').onchange = load;

  loadFigures();
  load();
  watch();
  wired();
});
