const API = '';

(function initStars() {
  const container = document.getElementById('stars');
  if (!container) return;
  for (let i = 0; i < 90; i++) {
    const s = document.createElement('div');
    s.className = 'star';
    const size = Math.random() * 2 + 0.5;
    s.style.cssText = `
      left:${Math.random()*100}%;
      top:${Math.random()*100}%;
      width:${size}px;
      height:${size}px;
      --d:${2 + Math.random()*4}s;
      --o:${0.3 + Math.random()*0.6};
      animation-delay:${Math.random()*5}s
    `;
    container.appendChild(s);
  }
})();

function toast(msg, duration = 2200) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), duration);
}

function copyText(text, label = 'Copied') {
  navigator.clipboard.writeText(text)
    .then(() => toast(`\u2713 ${label}`))
    .catch(() => toast('Copy failed'));
}

/* ── INDEX PAGE — Create paste ─────────────────────── */

let _createdSlug = '';
let _createdUrl  = '';

async function submitPaste() {
  const content  = document.getElementById('content')?.value?.trim();
  const language = document.getElementById('language')?.value;
  const ttlRaw   = document.getElementById('ttl')?.value;
  const password = document.getElementById('password')?.value || null;
  const burn     = document.getElementById('burn')?.checked;

  if (!content) { toast('\u26a0 Content is required'); return; }

  const contentBytes = new TextEncoder().encode(content).length;
  if (contentBytes > 500_000) { toast('\u26a0 Content exceeds 500KB limit'); return; }

  const btn     = document.getElementById('submit-btn');
  const btnText = document.getElementById('btn-text');
  btn.disabled  = true;
  btnText.innerHTML = '<span class="spinner"></span>&nbsp;Encrypting\u2026';

  const body = {
    content,
    language:        language || 'plaintext',
    burn_after_read: burn,
    password,
    ttl_seconds:     ttlRaw ? parseInt(ttlRaw) : null,
  };

  try {
    const res  = await fetch(`${API}/pastes/`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Unknown error');
    }

    const data = await res.json();

    _createdSlug = data.slug;
    _createdUrl  = data.url;

    document.getElementById('url-text').textContent      = data.url;
    document.getElementById('delete-token').textContent  = data.delete_token;

    document.getElementById('result').classList.add('visible');
    document.getElementById('result').scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    toast('\u2713 Paste vaulted');
  } catch (e) {
    toast(`\u2717 ${e.message}`);
  } finally {
    btn.disabled  = false;
    btnText.textContent = 'Encrypt & Vault It';
  }
}

function copyUrl() {
  const url = document.getElementById('url-text')?.textContent || _createdUrl;
  copyText(url, 'URL copied');
}

function goToView() {
  if (_createdSlug) window.location.href = `view.html?slug=${_createdSlug}`;
}

function resetForm() {
  document.getElementById('content').value  = '';
  document.getElementById('password').value = '';
  document.getElementById('burn').checked   = false;
  document.getElementById('ttl').value      = '';
  document.getElementById('result').classList.remove('visible');
  document.getElementById('content').focus();
  _createdSlug = '';
  _createdUrl  = '';
}

/* ── VIEW PAGE — Fetch + display paste ────────────── */

let _currentSlug      = '';
let _requiresPassword = false;

function show(id)   { const el = document.getElementById(id); if (el) el.style.display = ''; }
function hide(id)   { const el = document.getElementById(id); if (el) el.style.display = 'none'; }
function hideAll()  {
  ['slug-lookup','pw-gate','loading-card','paste-card','error-card'].forEach(hide);
}

if (document.getElementById('paste-card') !== null) {
  window.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    const slug   = extractSlug(params.get('slug') || '');
    if (slug) {
      _currentSlug = slug;
      fetchPaste(slug, null);
    } else {
      hideAll();
      show('slug-lookup');
    }
  });
}

function extractSlug(input) {
  if (!input) return '';
  try {
    const url = new URL(input);
    const p   = new URLSearchParams(url.search);
    return p.get('slug') || input;
  } catch {
    return input.trim().split('/').pop();
  }
}

function lookupFromInput() {
  const raw  = document.getElementById('slug-input')?.value?.trim();
  const slug = extractSlug(raw);
  if (!slug) { toast('\u26a0 Enter a slug or URL'); return; }
  _currentSlug = slug;
  history.replaceState(null, '', `?slug=${slug}`);
  fetchPaste(slug, null);
}

async function fetchPaste(slug, password) {
  hideAll();
  show('loading-card');

  let url = `${API}/pastes/${slug}`;
  let fetchOptions = { method: 'GET' };

  if (password) {
    fetchOptions = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    };
    url = `${API}/pastes/${slug}/read`;
  }

  try {
    const res = await fetch(url, fetchOptions);

    if (res.status === 403) {
      hideAll();
      _requiresPassword = true;
      show('pw-gate');
      if (password) toast('\u2717 Wrong password');
      return;
    }

    if (res.status === 410) {
      showError('\U0001f4a8', 'This Paste is Gone',
        'It has either been burned after reading, expired, or never existed.');
      return;
    }

    if (res.status === 404) {
      showError('\U0001f30c', 'Not Found', 'No paste with that slug exists in the vault.');
      return;
    }

    if (!res.ok) {
      const err = await res.json();
      showError('\u26a0', 'Error', err.detail || 'Something went wrong.');
      return;
    }

    const data = await res.json();
    renderPaste(slug, data);
  } catch (e) {
    showError('\u26a1', 'Connection Error', e.message);
  }
}

function fetchWithPassword() {
  const pw = document.getElementById('pw-input')?.value;
  if (!pw) { toast('\u26a0 Enter password'); return; }
  fetchPaste(_currentSlug, pw);
}

function renderPaste(slug, data) {
  hideAll();

  const badges = document.getElementById('badges');
  badges.innerHTML = '';
  badges.appendChild(makeBadge(data.language, 'badge-cyan'));
  if (data.burn_after_read) badges.appendChild(makeBadge('\U0001f525 Burn After Read', 'badge-red'));
  if (data.burned)          badges.appendChild(makeBadge('Destroyed', 'badge-red'));
  if (data.expires_at)      badges.appendChild(makeBadge(`Expires ${formatDate(data.expires_at)}`, 'badge-muted'));
  if (data.view_count !== undefined) badges.appendChild(makeBadge(`${data.view_count} view${data.view_count!==1?'s':''}`, 'badge-muted'));

  if (data.burned) {
    show('burn-warning');
  } else {
    hide('burn-warning');
  }

  document.getElementById('lang-label').textContent  = data.language;
  document.getElementById('paste-content').textContent = data.content;

  show('paste-card');
}

function makeBadge(text, cls) {
  const span = document.createElement('span');
  span.className = `badge ${cls}`;
  span.textContent = text;
  return span;
}

function formatDate(iso) {
  if (!iso || iso === 'never') return 'never';
  try {
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return iso; }
}

function showError(icon, title, msg) {
  hideAll();
  document.getElementById('error-icon').textContent  = icon;
  document.getElementById('error-title').textContent = title;
  document.getElementById('error-msg').textContent   = msg;
  show('error-card');
}

function copyContent() {
  const content = document.getElementById('paste-content')?.textContent;
  if (content) copyText(content, 'Content copied');
}

/* ── Delete dialog ────────────────────────────────── */
function showDeleteDialog()  { show('delete-overlay'); document.getElementById('delete-token-input').focus(); }
function closeDeleteDialog() { hide('delete-overlay'); }

async function confirmDelete() {
  const token = document.getElementById('delete-token-input')?.value?.trim();
  if (!token) { toast('\u26a0 Enter delete token'); return; }

  try {
    const res = await fetch(`${API}/pastes/${_currentSlug}?token=${encodeURIComponent(token)}`, {
      method: 'DELETE',
    });

    if (res.status === 204) {
      closeDeleteDialog();
      showError('\U0001f4a5', 'Paste Destroyed', 'It has been permanently deleted from the vault.');
      toast('\u2713 Paste deleted');
    } else if (res.status === 403) {
      toast('\u2717 Invalid delete token');
    } else {
      toast('\u2717 Delete failed');
    }
  } catch (e) {
    toast(`\u2717 ${e.message}`);
  }
}
