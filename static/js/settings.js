/* Settings.

   Two kinds of setting live here and they save differently:

   - Profile settings (targeting, scoring, places, pitch) are one JSON blob and
     save together, because they only make sense as a set.
   - App settings (schedule, email, integrations, data, appearance) come from
     core/settings_store.py and save per field the moment you leave it. The
     store fires each setting's on_change hook, so changing the schedule
     reschedules the live job — nothing here needs a restart.

   The app sections are generated from the schema the server returns, so adding
   a setting in Python makes it appear here with no markup change. */

const conf = { profile: null, profileId: null, dirty: false, watcher: null };

// ── path helpers for the profile blob ─────────────────────────

const at = (obj, path) => path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
function put(obj, path, value) {
  const keys = path.split('.');
  const last = keys.pop();
  keys.reduce((o, k) => (o[k] = o[k] || {}), obj)[last] = value;
}

function touched() {
  conf.dirty = true;
  const b = $('#profile-save');
  if (b) { b.disabled = false; b.textContent = 'Save changes'; }
}

// ── Chip editor ───────────────────────────────────────────────

function renderChips(host) {
  const path = host.dataset.path;
  const values = at(conf.profile, path) || [];
  const long = host.classList.contains('chips-long');

  host.innerHTML = `
    <div class="row wrap" style="gap:6px;margin-bottom:var(--s2)">
      ${values.map((v, i) => `
        <span class="tag" style="${long ? 'white-space:normal;text-align:left;max-width:100%;' : ''}padding:4px 8px">
          <span>${text(v)}</span>
          <button data-drop="${i}" aria-label="Remove"
                  style="border:0;background:none;cursor:pointer;padding:0 0 0 4px;color:inherit;display:flex">
            ${icon('close', 'ico ico-sm')}</button>
        </span>`).join('') || '<span class="quiet">Nothing yet</span>'}
    </div>
    <div class="row" style="gap:var(--s2)">
      ${long
        ? `<textarea class="in" data-new style="min-height:58px" placeholder="Add one and press Add"></textarea>`
        : `<input class="in" data-new placeholder="Type and press Enter">`}
      <button class="btn btn-sm" data-add>Add</button>
    </div>`;

  host.querySelectorAll('[data-drop]').forEach(b => b.onclick = () => {
    values.splice(Number(b.dataset.drop), 1);
    put(conf.profile, path, values);
    touched(); renderChips(host); preview();
  });

  const input = host.querySelector('[data-new]');
  const add = () => {
    const v = input.value.trim();
    if (!v) return;
    values.push(v);
    put(conf.profile, path, values);
    touched(); renderChips(host); preview();
    const next = host.querySelector('[data-new]');
    if (next) next.focus();
  };
  host.querySelector('[data-add]').onclick = add;
  input.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); add(); } };
}

// ── Profile ───────────────────────────────────────────────────

function bindProfile() {
  $$('[data-path]').forEach(el => {
    if (el.classList.contains('chips')) return renderChips(el);
    const v = at(conf.profile, el.dataset.path);
    el.value = v == null ? '' : v;
    el.oninput = el.onchange = () => {
      put(conf.profile, el.dataset.path, el.type === 'number' ? Number(el.value) : el.value);
      touched(); weights(); preview();
    };
  });
  weights(); preview();
}

function weights() {
  const w = at(conf.profile, 'scoring.weights') || {};
  const sum = ['title', 'tech', 'experience', 'signal'].reduce((a, k) => a + (Number(w[k]) || 0), 0);
  const el = $('#weight-total');
  if (!el) return;
  el.textContent = sum === 100 ? '— totals 100' : `— totals ${sum}`;
  el.style.color = sum === 100 ? 'var(--ink-3)' : 'var(--caution)';
}

function preview() {
  const o = (conf.profile || {}).outreach || {};
  const nice = { fastapi: 'FastAPI', postgresql: 'PostgreSQL', nodejs: 'Node.js', aws: 'AWS',
                 drf: 'DRF', graphql: 'GraphQL', mysql: 'MySQL' };
  const stack = (o.candidate_core_tech || ['your stack']).slice(0, 2)
    .map(t => nice[t] || t.charAt(0).toUpperCase() + t.slice(1)).join('/');
  const tok = {
    greeting: 'Hi there', company: 'Acme', title: 'Senior Backend Engineer', stack,
    bio_short: (o.bio_short || '').replace('{stack}', stack),
    achievements: (o.achievements || []).join('\n\n'),
    candidate_name: o.candidate_name || 'your name',
  };
  const fill = t => (t || '').replace(/\{(\w+)\}/g, (_, k) => tok[k] ?? '');
  const short = fill(o.dm_short_template);

  const len = $('#note-len');
  if (len) {
    len.textContent = short.length > 300
      ? `— ${short.length} characters, will be cut at 300`
      : `— ${short.length} of 300 characters`;
    len.style.color = short.length > 300 ? 'var(--critical)' : 'var(--ink-3)';
  }
  const pv = $('#pitch-preview');
  if (pv) pv.textContent = short + '\n\n· · ·\n\n' + fill(o.dm_long_template);
}

async function loadProfile() {
  try {
    const d = await api('/profiles/active');
    conf.profile = d.config;
    conf.profileId = d.id;
    const w = $('#set-where');
    if (w) w.textContent = d.name;
    bindProfile();
  } catch (e) {
    toast(`Could not load the profile: ${e.message}`, 'error');
  }
}

async function saveProfile(btn) {
  try {
    await withBusy(btn, 'Saving', () =>
      api(`/profiles/${conf.profileId}`, { method: 'PUT', body: { config: conf.profile } }));
    conf.dirty = false;
    btn.textContent = 'Saved';
    btn.disabled = true;
    toast('Saved. Reapply scoring to update roles already collected.', 'ok', 6000);
  } catch {}
}

// ── App settings, generated from the schema ───────────────────

function fieldMarkup(f) {
  const id = `set-${f.key}`;
  let control;

  if (f.type === 'bool') {
    control = `<label class="toggle"><input type="checkbox" id="${id}" data-setting="${escapeHtml(f.key)}"
                 ${f.value ? 'checked' : ''}> <span>${f.value ? 'On' : 'Off'}</span></label>`;
  } else if (f.type === 'choice') {
    control = `<select class="in" id="${id}" data-setting="${escapeHtml(f.key)}">
      ${(f.choices || []).map(c =>
        `<option value="${escapeHtml(c)}" ${c === f.value ? 'selected' : ''}>${text(c)}</option>`).join('')}
    </select>`;
  } else if (f.secret) {
    control = `<input class="in" type="password" id="${id}" data-setting="${escapeHtml(f.key)}"
      value="${escapeHtml(f.value || '')}" autocomplete="new-password"
      placeholder="${f.configured ? 'Saved — type to replace' : 'Not set'}">`;
  } else if (f.type === 'int') {
    control = `<input class="in" type="number" id="${id}" data-setting="${escapeHtml(f.key)}"
      value="${escapeHtml(f.value)}" ${f.min != null ? `min="${f.min}"` : ''} ${f.max != null ? `max="${f.max}"` : ''}>`;
  } else {
    control = `<input class="in" id="${id}" data-setting="${escapeHtml(f.key)}"
      value="${escapeHtml(f.value || '')}">`;
  }

  const test = { sender_password: 'email', rapidapi_key: 'jsearch' }[f.key];

  return `<div class="field">
    <label for="${id}">${text(f.label)}
      ${f.secret && f.configured ? '<span class="tag tag-good" style="margin-left:6px">Saved</span>' : ''}</label>
    ${f.help ? `<span class="note">${text(f.help)}</span>` : ''}
    <div class="row" style="gap:var(--s2)">
      <div class="grow">${control}</div>
      ${test ? `<button class="btn btn-sm" data-test="${test}">Test</button>` : ''}
    </div>
    <div class="note" data-result="${escapeHtml(f.key)}"></div>
  </div>`;
}

async function loadSettings() {
  try {
    const d = await api('/settings');
    const byId = Object.fromEntries(d.groups.map(g => [g.id, g]));

    $$('[data-group]').forEach(sec => {
      const groups = sec.dataset.group.split(',').map(g => byId[g]).filter(Boolean);
      sec.innerHTML = groups.map((g, i) => `
        ${i === 0 ? `<div>
          <h2 class="display" style="font-size:var(--t-xl)">${text(g.label)}</h2>
          <p class="quiet" style="margin-top:var(--s2)">${text(g.help)}</p>
        </div>` : `<h3 class="card-title" style="margin-top:var(--s6)">${text(g.label)}</h3>`}
        <div class="panel"><div class="panel-bd stack-6">
          ${g.fields.map(fieldMarkup).join('')}
        </div></div>`).join('');
    });

    wireSettings();
  } catch (e) {
    $$('[data-group]').forEach(sec => sec.innerHTML = failed(e.message, loadSettings));
  }
}

function wireSettings() {
  // Save on leaving the field rather than on every keystroke: each save fires
  // server-side hooks (rescheduling the cron, for one), so per-character
  // saving would be both noisy and wasteful.
  $$('[data-setting]').forEach(el => {
    const commit = async () => {
      const key = el.dataset.setting;
      const value = el.type === 'checkbox' ? el.checked
                  : el.type === 'number' ? Number(el.value) : el.value;
      const out = el.parentElement.parentElement.parentElement.querySelector(`[data-result="${key}"]`);
      try {
        await api('/settings', { method: 'PUT', body: { [key]: value } });
        if (out) {
          out.textContent = 'Saved';
          out.style.color = 'var(--good)';
          setTimeout(() => { out.textContent = ''; }, 2200);
        }
        if (el.type === 'checkbox') {
          const label = el.nextElementSibling;
          if (label) label.textContent = el.checked ? 'On' : 'Off';
        }
        if (['schedule_hour', 'timezone', 'schedule_enabled'].includes(key)) {
          toast('Schedule updated', 'ok', 2500);
        }
        if (key === 'product_name') setTimeout(() => location.reload(), 600);
      } catch (e) {
        if (out) { out.textContent = e.message; out.style.color = 'var(--critical)'; }
      }
    };
    if (el.type === 'checkbox' || el.tagName === 'SELECT') el.onchange = commit;
    else el.onblur = commit;
  });

  $$('[data-test]').forEach(b => b.onclick = async () => {
    const what = b.dataset.test;
    const key = what === 'email' ? 'sender_password' : 'rapidapi_key';
    const out = document.querySelector(`[data-result="${key}"]`);
    // Save whatever is typed before testing, otherwise the test checks the old value.
    const input = document.querySelector(`[data-setting="${key}"]`);
    try {
      if (input && input.value && !input.value.startsWith('•')) {
        await api('/settings', { method: 'PUT', body: { [key]: input.value } });
      }
      const r = await withBusy(b, 'Testing', () =>
        api(`/settings/test/${what}`, { method: 'POST' }));
      if (out) {
        out.textContent = r.detail;
        out.style.color = r.ok ? 'var(--good)' : 'var(--critical)';
      }
      toast(r.detail, r.ok ? 'ok' : 'error', 8000);
      if (r.ok && r.limit) await api('/settings', { method: 'PUT', body: { jsearch_limit: r.limit } });
    } catch (e) {
      if (out) { out.textContent = e.message; out.style.color = 'var(--critical)'; }
    }
  });
}

// ── Saved searches ────────────────────────────────────────────

async function loadSearches() {
  try {
    const d = await api('/search-queries');
    const qs = d.queries || [];
    const on = qs.filter(q => q.enabled !== false && q.enabled !== 0).length;
    const limit = (window.__system || {}).jsearch?.limit || 200;
    const cost = on * 30;
    const el = $('#search-cost');
    el.innerHTML = `Each enabled search uses one request per run, so these cost about
      <strong>${cost}</strong> of your ${fmt.num(limit)} monthly requests.`;
    el.style.color = cost > limit ? 'var(--critical)' : '';

    if (!qs.length) {
      setHtml('#search-rows', `<tr><td colspan="5">${blank({
        glyph: 'search', title: 'No saved searches',
        body: 'Without these, results come only from the free boards and your company list.',
      })}</td></tr>`);
      return;
    }

    setHtml('#search-rows', qs.map(q => `<tr>
      <td><strong>${text(q.query)}</strong></td>
      <td><span class="tag">${text(q.country)}</span></td>
      <td class="quiet">${text(q.date_posted)}</td>
      <td>${q.remote_jobs_only ? '<span class="tag tag-accent">Remote</span>' : '<span class="quiet">—</span>'}</td>
      <td class="right"><div class="btns">
        <button class="btn btn-sm" data-flip="${q.id}" data-on="${q.enabled ? 1 : 0}">${q.enabled ? 'Disable' : 'Enable'}</button>
        <button class="btn btn-quiet btn-sm" data-drop-q="${q.id}">Remove</button>
      </div></td></tr>`).join(''));

    $$('[data-flip]').forEach(b => b.onclick = async () => {
      try {
        await withBusy(b, '…', () => api(`/search-queries/${b.dataset.flip}`,
          { method: 'PATCH', body: { enabled: b.dataset.on !== '1' } }));
        loadSearches();
      } catch {}
    });
    $$('[data-drop-q]').forEach(b => b.onclick = async () => {
      try {
        await withBusy(b, '…', () => api(`/search-queries/${b.dataset.dropQ}`, { method: 'DELETE' }));
        toast('Search removed', 'ok', 2500); loadSearches();
      } catch {}
    });
  } catch (e) {
    setHtml('#search-rows', `<tr><td colspan="5">${failed(e.message, loadSearches)}</td></tr>`);
  }
}

// ── Profiles ──────────────────────────────────────────────────

async function loadProfiles() {
  try {
    const d = await api('/profiles');
    setHtml('#profile-list', (d.profiles || []).map(p => `
      <div class="fact">
        <span class="fact-k" style="color:var(--ink)">${text(p.name)}
          ${p.is_active ? '<span class="tag tag-good" style="margin-left:6px">In use</span>' : ''}</span>
        <span class="btns">
          ${p.is_active ? '' : `<button class="btn btn-sm" data-use="${p.id}">Use this</button>`}
          <a class="btn btn-quiet btn-sm" href="/api/profiles/${p.id}/export">Export</a>
        </span>
      </div>`).join('') || '<span class="quiet">None saved.</span>');

    setHtml('#preset-list', (d.presets || []).map(p => `
      <div class="fact" style="align-items:flex-start">
        <span class="fact-k" style="color:var(--ink)">${text(p.name || p.slug)}
          <div class="quiet" style="font-weight:400">${text(p.description || '')}</div></span>
        <button class="btn btn-sm" data-load="${escapeHtml(p.slug)}">Load</button>
      </div>`).join('') || '<span class="quiet">None found.</span>');

    $$('[data-use]').forEach(b => b.onclick = async () => {
      try {
        await withBusy(b, '…', () => api(`/profiles/${b.dataset.use}/activate`, { method: 'POST' }));
        toast('Profile switched', 'ok');
        loadProfile(); loadProfiles(); loadSearches();
      } catch {}
    });
    $$('[data-load]').forEach(b => b.onclick = async () => {
      try {
        await withBusy(b, 'Loading', () => api('/profiles/import', {
          method: 'POST', body: { preset_slug: b.dataset.load, activate: true, overwrite: true },
        }));
        toast('Loaded and now in use', 'ok');
        loadProfile(); loadProfiles(); loadSearches();
      } catch {}
    });
  } catch (e) {
    setHtml('#profile-list', failed(e.message, loadProfiles));
  }
}

// ── Runs ──────────────────────────────────────────────────────

function watch() {
  if (conf.watcher && !conf.watcher.stopped) return;
  let wasRunning = false;
  conf.watcher = poll(async () => {
    const d = await api('/runs?limit=1');
    window.__kinds = d.kinds;
    const host = $('#live');
    if (d.active) {
      wasRunning = true;
      const t = d.active.progress_total || 0, c = d.active.progress_current || 0;
      host.innerHTML = `<div class="panel"><div class="panel-bd">
        <div class="split" style="margin-bottom:var(--s3)">
          <div class="row">${runTag(d.active.status)}<strong>${text(runName(d.active.kind))}</strong>
            <span class="quiet">${text(d.active.progress_label || '')}</span></div>
          <span class="quiet nums">${t ? `${c} of ${t}` : ''}</span></div>
        <div class="meter"><div class="meter-fill ${t ? '' : 'unknown'}"
          style="width:${t ? Math.round(c / t * 100) : 32}%"></div></div>
      </div></div>`;
      return true;
    }
    host.innerHTML = '';
    if (wasRunning) {
      wasRunning = false;
      const last = d.runs[0];
      if (last && last.status === 'success') {
        const s = last.stats || {};
        toast(s.updated !== undefined
          ? `Rescored ${fmt.num(s.updated)} roles${s.deleted ? `, removed ${s.deleted}` : ''}`
          : 'Finished', 'ok');
      } else if (last) toast(`${runName(last.kind)} ${last.status}`, 'error');
    }
    return true;
  }, 1500);
}

// ── Init ──────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // A save bar that only appears for the profile sections, since app settings
  // save themselves and a global Save button would imply otherwise.
  const bar = document.createElement('div');
  bar.className = 'panel';
  bar.style.cssText = 'position:sticky;bottom:var(--s5);margin-top:var(--s6)';
  bar.innerHTML = `<div class="panel-ft" style="border-top:0;border-radius:var(--r)">
      <span class="quiet" id="profile-hint">These settings save together.</span>
      <button class="btn btn-primary push" id="profile-save" disabled>Saved</button>
    </div>`;
  const profileSections = ['targeting', 'scoring', 'places', 'pitch'];
  document.querySelector('[data-sec-body="pitch"]').after(bar);

  function showSection(name) {
    $$('#sections button').forEach(b => b.classList.toggle('active', b.dataset.sec === name));
    $$('[data-sec-body]').forEach(s => s.hidden = s.dataset.secBody !== name);
    bar.hidden = !profileSections.includes(name);
  }
  $$('#sections button').forEach(b => b.onclick = () => showSection(b.dataset.sec));
  showSection('targeting');

  $('#profile-save').onclick = function () { saveProfile(this); };

  $('#btn-rescore').onclick = async function () {
    try {
      await withBusy(this, 'Starting', () => api('/runs', { method: 'POST', body: { kind: 'rescore' } }));
      toast('Reapplying scoring to every stored role', 'ok');
      watch();
    } catch {}
  };

  $('#btn-add-q').onclick = async function () {
    const q = $('#q-new').value.trim();
    if (!q) { toast('Type a search first', 'warn'); return; }
    try {
      await withBusy(this, 'Adding', () => api('/search-queries', {
        method: 'POST',
        body: { query: q, country: $('#q-country').value, date_posted: $('#q-when').value,
                remote_jobs_only: $('#q-remote').checked },
      }));
      $('#q-new').value = '';
      toast('Search added', 'ok', 2500);
      loadSearches();
    } catch {}
  };

  window.addEventListener('beforeunload', e => {
    if (conf.dirty) { e.preventDefault(); e.returnValue = ''; }
  });

  loadProfile();
  loadSettings();
  loadSearches();
  loadProfiles();
  watch();
  wired();
});
