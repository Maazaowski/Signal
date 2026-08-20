/* Intros — the working queue.
   One card per role: who to contact, the note to send, and where you got to.
   Copy is the primary action, so it sits closest to the text it copies. */

const queue = { items: [], watcher: null };

const STAGE = {
  pending:     { label: 'Not sent yet',    cls: 'tag tag-accent' },
  emailed:     { label: 'In the digest',   cls: 'tag' },
  messaged:    { label: 'Sent',            cls: 'tag tag-caution' },
  replied:     { label: 'Replied',         cls: 'tag tag-good' },
  followed_up: { label: 'Followed up',     cls: 'tag' },
};

function contacts(item) {
  let searches = [];
  try { searches = JSON.parse(item.notes || '[]') || []; } catch {}
  if (!searches.length && item.contact_linkedin) {
    searches = [{ label: 'Search LinkedIn', url: item.contact_linkedin, category: 'engineering' }];
  }
  if (!searches.length) return '<span class="quiet">No contact searches were generated.</span>';

  const groups = { engineering: [], executive: [], hr: [] };
  searches.forEach(s => (groups[s.category] || groups.engineering).push(s));
  const heading = { engineering: 'Engineering', executive: 'Leadership', hr: 'Recruiting' };

  return Object.entries(groups).filter(([, v]) => v.length).map(([k, v]) => `
    <div style="margin-bottom:var(--s3)">
      <div class="eyebrow" style="margin-bottom:var(--s2)">${text(heading[k])}</div>
      <div class="row wrap" style="gap:var(--s2)">
        ${v.map(s => `<a class="btn btn-sm" target="_blank" rel="noopener noreferrer"
           href="${escapeHtml(safeUrl(s.url))}">${text(s.label || 'Search')}
           ${icon('external', 'ico ico-sm')}</a>`).join('')}
      </div>
    </div>`).join('');
}

function card(item) {
  const st = STAGE[item.status] || { label: item.status, cls: 'tag' };
  const len = (item.dm_short || '').length;
  return `<article class="panel" style="margin-bottom:var(--s5)">
    <div class="panel-hd">
      <div class="grow">
        <div class="row" style="gap:var(--s2)">
          ${item.relevance_score != null ? score(item.relevance_score) : ''}
          <h2 class="card-title clip">${text(item.job_title)}</h2>
        </div>
        <div class="quiet" style="font-size:var(--t-sm);margin-top:2px">
          ${text(item.company)}${item.location ? ' · ' + text(item.location) : ''}
          · written ${text(fmt.ago(item.created_at))}
        </div>
      </div>
      <span class="${st.cls}">${text(st.label)}</span>
    </div>

    <div class="panel-bd stack-6">
      <div>
        <div class="eyebrow" style="margin-bottom:var(--s3)">Who to contact at ${text(item.company)}</div>
        ${contacts(item)}
      </div>

      <div>
        <div class="split" style="margin-bottom:var(--s2)">
          <div class="eyebrow">Connection note
            <span style="text-transform:none;letter-spacing:0;font-weight:400;color:var(--ink-3)">
              — ${len} of 300 characters</span></div>
          <button class="btn btn-sm" data-copy="${escapeHtml(item.id)}" data-part="short">
            ${icon('copy', 'ico ico-sm')} Copy</button>
        </div>
        <div class="log" style="max-height:none" id="note-short-${escapeHtml(item.id)}">${text(item.dm_short)}</div>
      </div>

      <details>
        <summary style="cursor:pointer;color:var(--ink-2);font-weight:550">Longer message</summary>
        <div class="split" style="margin:var(--s4) 0 var(--s2)">
          <span class="quiet" style="font-size:var(--t-sm)">For InMail, or a follow-up</span>
          <button class="btn btn-sm" data-copy="${escapeHtml(item.id)}" data-part="long">
            ${icon('copy', 'ico ico-sm')} Copy</button>
        </div>
        <div class="log" style="max-height:none" id="note-long-${escapeHtml(item.id)}">${text(item.dm_long)}</div>
      </details>
    </div>

    <div class="panel-ft">
      ${item.job_url ? `<a class="btn btn-sm" target="_blank" rel="noopener noreferrer"
          href="${escapeHtml(safeUrl(item.job_url))}">The posting ${icon('external', 'ico ico-sm')}</a>` : ''}
      <div class="btns push">
        <button class="btn btn-sm" data-stage="${escapeHtml(item.id)}" data-to="messaged" data-field="messaged">
          ${icon('check', 'ico ico-sm')} I sent this</button>
        <button class="btn btn-sm" data-stage="${escapeHtml(item.id)}" data-to="replied" data-field="replied">
          They replied</button>
      </div>
    </div>
  </article>`;
}

async function loadStats() {
  try {
    const s = await api('/outreach/stats');
    const by = s.by_status || {};
    const ready = by.pending || 0;
    $('#intros-where').textContent = ready
      ? `${ready} not sent yet` : `${s.total || 0} total`;
    const nav = $('#tally-intros');
    if (nav) nav.textContent = ready ? fmt.num(ready) : '';
  } catch {}
}

async function load() {
  setHtml('#intros', `<div class="panel"><div class="panel-bd">
    <div class="ghost" style="width:44%;height:14px"></div>
    <div class="ghost" style="width:74%;margin-top:14px"></div></div></div>`);

  const p = new URLSearchParams({ limit: '50' });
  const q = $('#f-q').value.trim();
  const stage = $('#f-stage').value;
  if (q) p.set('search', q);
  if (stage) p.set('status', stage);

  try {
    const d = await api('/outreach?' + p);   // endpoint name predates the rename
    queue.items = d.outreach || [];
    if (!queue.items.length) {
      setHtml('#intros', `<div class="panel">${blank({
        glyph: 'intros',
        title: q || stage ? 'Nothing at this stage' : 'No intros written yet',
        body: q || stage
          ? 'Try clearing the stage filter.'
          : 'Each intro pairs a role with people to contact and a note ready to send. Write some from the roles already collected.',
        action: q || stage
          ? `<button class="btn" onclick="clearFilters()">Clear filters</button>`
          : `<button class="btn btn-primary" onclick="document.getElementById('btn-write').click()">
               ${icon('plus', 'ico ico-sm')} Write intros</button>`,
      })}</div>`);
      return;
    }
    setHtml('#intros', queue.items.map(card).join(''));
    wire();
  } catch (e) {
    setHtml('#intros', `<div class="panel">${failed(e.message, load)}</div>`);
  }
}

function wire() {
  $$('#intros [data-copy]').forEach(b => b.onclick = async () => {
    const el = document.getElementById(`note-${b.dataset.part}-${b.dataset.copy}`);
    if (!el) return;
    try {
      await navigator.clipboard.writeText(el.textContent);
      const was = b.innerHTML;
      b.innerHTML = icon('check', 'ico ico-sm') + ' Copied';
      setTimeout(() => (b.innerHTML = was), 1600);
    } catch {
      toast('Copy was blocked — select the text and copy it manually', 'warn');
    }
  });

  $$('#intros [data-stage]').forEach(b => b.onclick = async () => {
    try {
      await withBusy(b, '…', () => api(
        `/outreach/${encodeURIComponent(b.dataset.stage)}/status?status=${b.dataset.to}&field=${b.dataset.field}`,
        { method: 'PATCH' }));
      toast(b.dataset.to === 'replied' ? 'Nice — marked as replied' : 'Marked as sent', 'ok', 2500);
      load(); loadStats();
    } catch {}
  });
}

function clearFilters() {
  $('#f-q').value = ''; $('#f-stage').value = '';
  load();
}

function renderLive(run) {
  const host = $('#live');
  if (!run) { host.innerHTML = ''; return; }
  host.innerHTML = `<div class="panel"><div class="panel-bd">
    <div class="row" style="margin-bottom:var(--s3)">${runTag(run.status)}
      <strong>${text(runName(run.kind))}</strong>
      <span class="quiet">${text(run.progress_label || 'working')}</span></div>
    <div class="meter"><div class="meter-fill unknown" style="width:32%"></div></div>
  </div></div>`;
}

function watch() {
  if (queue.watcher && !queue.watcher.stopped) return;
  let wasRunning = false;
  queue.watcher = poll(async () => {
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
          if (s.generated !== undefined) msg = `${s.generated} ${s.generated === 1 ? 'intro' : 'intros'} written`;
          else if (s.skipped) msg = `Digest not sent — ${s.reason || 'email is not set up'}`;
          else if (s.sent !== undefined) msg = s.sent ? 'Digest sent' : 'Digest not sent';
        }
        toast(msg, last.status === 'success' ? 'ok' : 'error', 8000);
      }
      load(); loadStats();
    }
    return true;
  }, 1500);
}

document.addEventListener('system', e => { if (e.detail.active_run) renderLive(e.detail.active_run); });

document.addEventListener('DOMContentLoaded', () => {
  const startRun = async (btn, kind, msg) => {
    try {
      const res = await withBusy(btn, 'Starting', () =>
        api('/runs', { method: 'POST', body: { kind } }));
      renderLive({ id: res.run_id, kind, status: 'queued', progress_label: 'queued' });
      toast(msg, 'ok');
      watch();
    } catch {}
  };

  $('#btn-write').onclick = function () { startRun(this, 'outreach', 'Writing intros'); };
  $('#btn-send').onclick  = function () { startRun(this, 'email', 'Sending the digest'); };

  $('#btn-preview').onclick = async () => {
    openPanel('preview');
    setHtml('#pv-body', '<div class="ghost" style="width:60%;height:14px"></div>');
    try {
      const r = await api('/email/send-now?dry_run=true', { method: 'POST' });
      if (r.error) {
        setHtml('#pv-body', `<div class="notice notice-caution">${icon('alert')}
          <div>${text(r.error)}</div></div>`);
        return;
      }
      setHtml('#pv-body', `
        <div class="facts" style="margin-bottom:var(--s5)">
          <div class="fact"><span class="fact-k">To</span><span class="fact-v">${text(r.recipient || '—')}</span></div>
          <div class="fact"><span class="fact-k">Subject</span><span class="fact-v">${text(r.subject || '—')}</span></div>
          <div class="fact"><span class="fact-k">Roles included</span><span class="fact-v">${text(r.items ?? r.count ?? 0)}</span></div>
        </div>
        <div class="notice notice-info">${icon('info')}
          <div>Nothing was sent. Use <strong>Send digest</strong> when you are ready.</div></div>`);
    } catch (e) {
      setHtml('#pv-body', failed(e.message));
    }
  };

  $('#btn-clear').onclick = clearFilters;
  $('#f-stage').onchange = load;
  let t;
  $('#f-q').oninput = () => { clearTimeout(t); t = setTimeout(load, 350); };

  loadStats();
  load();
  watch();
  wired();
});
