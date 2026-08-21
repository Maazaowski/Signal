/* Shared runtime for every page.
   Previously app.js / outreach.js / profile.js each carried their own copy of
   the escaping helpers, and two of the three copies were wrong. There is now
   exactly one implementation of each. */

// ── Escaping & URLs ───────────────────────────────────────────

// Escapes quotes too — a textContent/innerHTML round-trip does not, which is
// what let feed-supplied values break out of href="" and title="" attributes.
function escapeHtml(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// Job URLs come from third-party feeds and can be `javascript:`.
function safeUrl(u) { return /^https?:\/\//i.test(u || '') ? u : '#'; }

// Strip tags without building live DOM. Assigning to .innerHTML — even on a
// detached node — starts image loads and fires inline handlers such as
// <img src=x onerror=…>. A DOMParser document is inert.
function stripHtml(html) {
  if (!html) return '';
  try {
    return new DOMParser().parseFromString(String(html), 'text/html').body.textContent || '';
  } catch (e) {
    return String(html).replace(/<[^>]*>/g, '');
  }
}

/** Escape a value for safe insertion as plain text, stripping any markup. */
function text(v) { return escapeHtml(stripHtml(v == null ? '' : String(v))); }

// ── API client ────────────────────────────────────────────────

class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

/**
 * Call the JSON API. Paths are relative to /api.
 * Throws ApiError with the server's `detail` as the message, so callers can
 * show something meaningful instead of "Failed to fetch".
 */
async function api(path, opts = {}) {
  const url = path.startsWith('/api') ? path : '/api' + path;
  const init = { headers: {}, ...opts };
  if (init.body && typeof init.body !== 'string') {
    init.body = JSON.stringify(init.body);
    init.headers['Content-Type'] = 'application/json';
  }

  let res;
  try {
    res = await fetch(url, init);
  } catch (e) {
    throw new ApiError('Cannot reach the server — is it still running?', 0, null);
  }

  const isJson = (res.headers.get('content-type') || '').includes('application/json');
  const body = isJson ? await res.json().catch(() => null) : await res.text();

  if (!res.ok) {
    const detail = (body && (body.detail || body.error)) || res.statusText || 'Request failed';
    throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail), res.status, body);
  }
  return body;
}

// ── Toasts ────────────────────────────────────────────────────

function toast(message, kind = 'info', ms = 5000) {
  let host = document.querySelector('.toasts');
  if (!host) {
    host = document.createElement('div');
    host.className = 'toasts';
    document.body.appendChild(host);
  }
  const el = document.createElement('div');
  const k = kind === 'error' ? 'danger' : kind;
  const glyph = { ok: 'check', warn: 'alert', danger: 'alert' }[k] || 'info';
  el.className = 'toast ' + k;
  el.setAttribute('role', k === 'danger' ? 'alert' : 'status');
  el.innerHTML =
    icon(glyph) +
    `<div style="flex:1">${text(message)}</div>` +
    `<button class="toast-x" aria-label="Dismiss">${icon('close', 'ico ico-sm')}</button>`;
  el.querySelector('.toast-x').onclick = () => el.remove();
  host.appendChild(el);
  if (ms) setTimeout(() => el.remove(), ms);
  return el;
}

/** Wrap an async action: disables the button, reports failures as a toast. */
async function withBusy(btn, label, fn) {
  const original = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = label || 'Working…'; }
  try {
    return await fn();
  } catch (e) {
    toast(e.message || String(e), 'error');
    throw e;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = original; }
  }
}

// ── Polling ───────────────────────────────────────────────────

/**
 * Poll `fn` every `ms` until it returns false or stop() is called.
 * Pauses while the tab is hidden so a backgrounded tab is not hammering
 * the server, and fires immediately when it becomes visible again.
 */
function poll(fn, ms = 2000) {
  let timer = null, stopped = false, running = false, first = true;

  async function tick() {
    if (stopped || running) return;
    // The first fetch always runs, even in a background tab — otherwise a page
    // opened via cmd-click or restored in a background tab renders blank
    // forever. Only repeat polls pause while hidden.
    if (document.hidden && !first) return schedule();
    first = false;
    running = true;
    try {
      const keepGoing = await fn();
      if (keepGoing === false) return stop();
    } catch (e) {
      /* transient errors should not kill the poll loop */
    } finally {
      running = false;
    }
    schedule();
  }
  function schedule() {
    if (stopped) return;
    clearTimeout(timer);
    timer = setTimeout(tick, ms);
  }
  function stop() { stopped = true; clearTimeout(timer); document.removeEventListener('visibilitychange', onVis); }
  function onVis() { if (!document.hidden) tick(); }

  document.addEventListener('visibilitychange', onVis);
  tick();
  return { stop, get stopped() { return stopped; } };
}

// ── Formatting ────────────────────────────────────────────────

const fmt = {
  num(n) { return (n == null ? 0 : n).toLocaleString(); },

  date(iso, withTime = false) {
    if (!iso) return '—';
    const d = new Date(/Z|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z');
    if (isNaN(d)) return String(iso);
    const opts = { day: 'numeric', month: 'short', year: 'numeric' };
    if (withTime) { opts.hour = '2-digit'; opts.minute = '2-digit'; }
    return d.toLocaleDateString(undefined, opts);
  },

  ago(iso) {
    if (!iso) return '—';
    const d = new Date(/Z|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z');
    if (isNaN(d)) return String(iso);
    const s = Math.round((Date.now() - d.getTime()) / 1000);
    if (s < 5) return 'just now';
    if (s < 60) return `${s}s ago`;
    const m = Math.round(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.round(m / 60);
    if (h < 24) return `${h}h ago`;
    const days = Math.round(h / 24);
    if (days < 30) return `${days}d ago`;
    return fmt.date(iso);
  },

  until(iso) {
    if (!iso) return '—';
    const diff = new Date(iso).getTime() - Date.now();
    if (diff <= 0) return 'due now';
    const m = Math.round(diff / 60000);
    if (m < 60) return `in ${m}m`;
    const h = Math.floor(m / 60);
    const rem = m % 60;
    if (h < 24) return rem ? `in ${h}h ${rem}m` : `in ${h}h`;
    return `in ${Math.round(h / 24)}d`;
  },

  duration(startIso, endIso) {
    if (!startIso) return '—';
    const a = new Date(startIso + (/(Z|[+-]\d\d:?\d\d)$/.test(startIso) ? '' : 'Z'));
    const b = endIso ? new Date(endIso + (/(Z|[+-]\d\d:?\d\d)$/.test(endIso) ? '' : 'Z')) : new Date();
    const s = Math.max(0, Math.round((b - a) / 1000));
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    return `${m}m ${s % 60}s`;
  },

  bytes(n) {
    if (!n) return '0 B';
    const u = ['B', 'KB', 'MB', 'GB'];
    const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
    return `${(n / Math.pow(1024, i)).toFixed(i ? 1 : 0)} ${u[i]}`;
  },
};

// ── Icons ─────────────────────────────────────────────────────

/** Reference a symbol from the sprite in templates/_icons.html. */
function icon(name, cls = 'ico') {
  return `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
}

// ── Shared vocabulary ─────────────────────────────────────────
// Every page labels the same state with the same word. Divergent wording for
// the same thing is what makes an interface feel assembled rather than designed.

const RUN_STATE = {
  queued:    { label: 'Waiting',  cls: 'tag' },
  running:   { label: 'Running',  cls: 'tag tag-accent' },
  success:   { label: 'Done',     cls: 'tag tag-good' },
  failed:    { label: 'Failed',   cls: 'tag tag-critical' },
  cancelled: { label: 'Stopped',  cls: 'tag tag-caution' },
};

function runTag(status) {
  const s = RUN_STATE[status] || { label: status || 'unknown', cls: 'tag' };
  const pip = status === 'running' ? '<span class="pip pip-live"></span>' : '';
  return `<span class="${s.cls}">${pip}${text(s.label)}</span>`;
}

// "Open to you" reads as a fact about the role, and stays true whatever country
// the user configured. "Location fit" is the internal name; it is engineer-speak
// and does not belong on screen.
const FIT = {
  yes:     { label: 'Open to you', cls: 'tag tag-good' },
  maybe:   { label: 'Possibly',    cls: 'tag tag-caution' },
  no:      { label: 'Not open',    cls: 'tag' },
  unknown: { label: 'Unclear',     cls: 'tag' },
};

function fitTag(value, why) {
  const f = FIT[value] || FIT.unknown;
  const title = why ? ` title="${escapeHtml(stripHtml(why))}"` : '';
  return `<span class="${f.cls}"${title}>${text(f.label)}</span>`;
}

/** Score as a quiet numeral. Weight, not colour, carries the emphasis. */
function score(n) {
  const v = Number(n) || 0;
  const cls = v >= 60 ? 'strong' : v >= 40 ? 'mid' : '';
  return `<span class="score ${cls}">${v}</span>`;
}

const RUN_VERB = {
  collect: 'Find roles', crawl: 'Crawl company boards', pipeline: 'Full run',
  email: 'Send digest', outreach: 'Write intros', rescore: 'Reapply scoring',
  discover: 'Discover companies', seed: 'Add company list',
  detect_ats: 'Find job boards',
};
function runName(kind) { return RUN_VERB[kind] || (window.__kinds || {})[kind] || kind; }

// ── Theme ─────────────────────────────────────────────────────

const theme = {
  get() { return localStorage.getItem('theme') || 'system'; },
  apply(mode) {
    const root = document.documentElement;
    if (mode === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', mode);
    localStorage.setItem('theme', mode);
    document.querySelectorAll('[data-theme-btn]').forEach(b => {
      b.setAttribute('aria-pressed', String(b.dataset.themeBtn === mode));
    });
  },
  cycle() {
    const order = ['system', 'light', 'dark'];
    const next = order[(order.indexOf(theme.get()) + 1) % order.length];
    theme.apply(next);
    return next;
  },
  init() { theme.apply(theme.get()); },
};
// Applied before first paint (this file is loaded in <head>) to avoid a flash.
theme.init();

// ── Panels (modal / drawer) ───────────────────────────────────

function openPanel(id) {
  const el = document.getElementById(id);
  if (!el) return;
  let ov = document.querySelector('.scrim');
  if (!ov) {
    ov = document.createElement('div');
    ov.className = 'scrim';
    document.body.appendChild(ov);
  }
  ov.classList.add('open');
  ov.onclick = () => closePanel(id);
  el.classList.add('open');
  document.body.style.overflow = 'hidden';
  const focusable = el.querySelector('input, select, textarea, button');
  if (focusable) setTimeout(() => focusable.focus(), 50);
}

function closePanel(id) {
  const el = id ? document.getElementById(id) : document.querySelector('.dialog.open, .aside.open');
  if (el) el.classList.remove('open');
  const ov = document.querySelector('.scrim');
  if (ov) ov.classList.remove('open');
  document.body.style.overflow = '';
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closePanel(); });

// ── Small DOM helpers ─────────────────────────────────────────

const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function setHtml(sel, html) { const el = $(sel); if (el) el.innerHTML = html; }

function ghostRows(cols, rows = 5) {
  return Array.from({ length: rows }, () =>
    `<tr>${Array.from({ length: cols }, () =>
      `<td><div class="ghost" style="width:${45 + Math.random() * 45}%"></div></td>`).join('')}</tr>`
  ).join('');
}

function ghostEntries(rows = 4) {
  return Array.from({ length: rows }, () => `
    <div class="entry">
      <div class="ghost" style="width:22px"></div>
      <div><div class="ghost" style="width:52%;height:14px"></div>
           <div class="ghost" style="width:32%;margin-top:7px"></div></div>
      <div class="ghost" style="width:64px"></div>
    </div>`).join('');
}

/** An empty state names what is missing and offers the thing that fixes it. */
function blank({ glyph = 'empty', title, body = '', action = '' }) {
  return `<div class="blank">
    ${icon(glyph)}
    <h3>${text(title)}</h3>
    ${body ? `<p>${text(body)}</p>` : ''}
    ${action || ''}
  </div>`;
}

function failed(message, retry) {
  const id = 'r' + Math.random().toString(36).slice(2);
  if (retry) setTimeout(() => { const b = document.getElementById(id); if (b) b.onclick = retry; }, 0);
  return `<div class="blank">
    ${icon('alert')}
    <h3>That didn't load</h3>
    <p>${text(message)}</p>
    ${retry ? `<button class="btn" id="${id}">${icon('refresh', 'ico ico-sm')} Try again</button>` : ''}
  </div>`;
}


/** Call at the end of a page module's init: enables the action buttons that
 *  start disabled in the markup, so a control is never clickable before its
 *  handler exists. Also marks the shell ready for tests and CSS. */
function wired() {
  document.querySelectorAll('[data-wire]').forEach(b => {
    b.disabled = false;
    b.removeAttribute('data-wire');
  });
  document.body.dataset.ready = '1';
}
