const API = '';

// --- Navigation ---
document.querySelectorAll('.nav-item[data-page]').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    item.classList.add('active');
    document.querySelectorAll('main > section').forEach(s => s.style.display = 'none');
    document.getElementById('page-' + item.dataset.page).style.display = '';
    stopObs();
    if      (item.dataset.page === 'dashboard')  loadDashboard();
    else if (item.dataset.page === 'assets')     loadAssets();
    else if (item.dataset.page === 'discovery')  loadDiscovery();
    else if (item.dataset.page === 'plans')      loadPlans();
    else if (item.dataset.page === 'reports')    loadReports();
    else if (item.dataset.page === 'obs')        startObs();
  });
});

// --- Toast ---
function toast(msg, type = 'success') {
  const el = document.createElement('div');
  el.className = 'toast toast-' + type;
  el.textContent = msg;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// --- Modal ---
function showModal(id) { document.getElementById(id).classList.add('show'); }
function closeModal(id) { document.getElementById(id).classList.remove('show'); }
function showAddAsset() { showModal('addAssetModal'); }
function showGeneratePlan() {
  const today = new Date().toISOString().split('T')[0];
  document.getElementById('planDate').value = today;
  showModal('genPlanModal');
}

// --- Helpers ---
function badge(text, color) {
  return `<span class="badge badge-${color}">${text}</span>`;
}

function formatDuration(sec) {
  if (!sec && sec !== 0) return '—';
  if (sec < 60) return sec + 's';
  if (sec < 3600) {
    const m = Math.floor(sec / 60), s = sec % 60;
    return s ? `${m}m ${s}s` : `${m}m`;
  }
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
  return m ? `${h}h ${m}m` : `${h}h`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function rightsBadge(status) {
  if (status === 'approved_for_stream') return badge('approved', 'green');
  if (status === 'blocked') return badge('blocked', 'red');
  return badge('pending', 'yellow');
}

function statusBadge(status) {
  const colors = {
    registered: 'grey', approved: 'green', blocked: 'red',
    downloaded: 'blue', prepared: 'pink', deleted: 'grey',
    draft: 'yellow', preparing: 'blue', ready: 'green',
    streaming: 'pink', completed: 'green', failed: 'red',
    queued: 'grey', skipped: 'yellow',
    found: 'blue', inspected: 'yellow', accepted: 'green', rejected: 'red',
    authorized_direct: 'green', authorized_official: 'green', metadata_only: 'yellow',
    unavailable: 'red', none: 'grey', blocked: 'red',
    pending_review: 'yellow', approved_for_stream: 'green',
  };
  return badge(status, colors[status] || 'grey');
}

async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  if (res.status === 204) return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

// --- Dashboard ---
async function loadDashboard() {
  try {
    const [assets, obs] = await Promise.all([
      api('GET', '/assets?limit=1000'),
      api('GET', '/obs/snapshot').catch(() => null),
    ]);
    const videos  = assets.filter(a => a.kind === 'video');
    const approved = assets.filter(a => a.rights_status === 'approved_for_stream');
    const pending  = assets.filter(a => a.rights_status === 'pending_review');
    const blocked  = assets.filter(a => a.rights_status === 'blocked');

    document.getElementById('dashStats').innerHTML = `
      <div class="stat-card"><div class="stat-label">Videos</div><div class="stat-value accent">${videos.length}</div></div>
      <div class="stat-card"><div class="stat-label">Approved</div><div class="stat-value green">${approved.length}</div></div>
      <div class="stat-card"><div class="stat-label">Pending Review</div><div class="stat-value yellow">${pending.length}</div></div>
      <div class="stat-card"><div class="stat-label">Blocked</div><div class="stat-value red">${blocked.length}</div></div>
    `;

    // Stream status from obs snapshot (richer than /stream/status)
    if (obs) {
      const sig = obs.signal;
      const dot = sig.status === 'streaming' ? 'green' : sig.status === 'fallback' ? 'amber' : 'red';
      const label = sig.status === 'streaming' ? 'LIVE' : sig.status === 'fallback' ? 'FALLBACK' : 'OFF';
      const hb = sig.heartbeat_stale_sec !== null ? _fmtAgo(sig.heartbeat_stale_sec) : '—';
      const playing = sig.current ? escapeHtml(sig.current.title || '—') : '—';
      const qh = obs.pipeline.queued_hours || 0;
      document.getElementById('streamStatus').innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;padding:4px 0 12px">
          <span class="dot ${dot}"></span>
          <strong style="font-size:16px">${label}</strong>
          <span class="muted" style="font-size:12px">heartbeat ${hb}</span>
        </div>
        <div class="obs-stat-row"><strong>Tocando</strong><span class="v">${playing}</span></div>
        <div class="obs-stat-row"><strong>Fila</strong><span class="v">${qh.toFixed(1)}h</span></div>
        ${obs.director.last_run_at ? `<div class="obs-stat-row"><strong>Diretor</strong><span class="v">rodou ${_fmtAgo(_agoSec(obs.director.last_run_at))}</span></div>` : ''}
      `;
    } else {
      const streamStatus = await api('GET', '/stream/status').catch(() => ({ running: false }));
      document.getElementById('streamStatus').innerHTML = streamStatus.running
        ? '<span class="badge badge-pink">LIVE</span> Stream is running'
        : '<span class="badge badge-grey">OFF</span> Stream is stopped';
    }

    // Pending candidates (quick check)
    const pending_cands = await api('GET', '/candidates?limit=5&rights_status=pending_review').catch(() => []);
    document.getElementById('recentAssetsTable').innerHTML = pending_cands.length
      ? `<div class="muted" style="margin-bottom:8px;font-size:12px">${pending_cands.length} candidate(s) waiting for Director review</div>` + candidateTable(pending_cands)
      : '<div class="empty-state compact"><p>Nenhum candidato pendente — tudo em dia</p></div>';
  } catch (e) {
    toast('Failed to load dashboard: ' + e.message, 'error');
  }
}

// --- Assets ---
async function loadAssets() {
  try {
    let params = [];
    const kind = document.getElementById('filterKind').value;
    const rights = document.getElementById('filterRights').value;
    if (kind) params.push('kind=' + kind);
    if (rights) params.push('rights_status=' + rights);
    const qs = params.length ? '?' + params.join('&') : '';
    const assets = await api('GET', '/assets' + qs);
    document.getElementById('assetsTable').innerHTML = assets.length
      ? assetTable(assets, false)
      : '<div class="empty-state"><p>No assets match your filters</p></div>';
  } catch (e) {
    toast('Failed to load assets: ' + e.message, 'error');
  }
}

function assetTable(assets, compact) {
  let html = '<table><thead><tr>';
  html += '<th>Title</th><th>Kind</th><th>Rights</th><th>Status</th>';
  if (!compact) html += '<th>Duration</th><th>Streamed</th><th>Health</th>';
  html += '<th>Actions</th></tr></thead><tbody>';
  for (const a of assets) {
    html += '<tr>';
    html += `<td><strong>${escapeHtml(a.title)}</strong></td>`;
    html += `<td>${badge(a.kind, a.kind === 'video' ? 'blue' : a.kind === 'music' ? 'pink' : 'yellow')}</td>`;
    html += `<td>${rightsBadge(a.rights_status)}</td>`;
    html += `<td>${statusBadge(a.status)}</td>`;
    if (!compact) {
      html += `<td>${formatDuration(a.duration_sec)}</td>`;
      html += `<td>${(a.times_streamed || 0)}×</td>`;
      const hs = a.health_score;
      const hColor = hs === null || hs === undefined ? 'grey' : hs >= 0.7 ? 'green' : hs >= 0.4 ? 'yellow' : 'red';
      html += `<td>${badge(hs !== null && hs !== undefined ? hs.toFixed(2) : '—', hColor)}</td>`;
    }
    html += '<td>';
    if (a.rights_status === 'pending_review') {
      html += `<button class="btn btn-primary btn-sm" onclick="approveAsset('${a.id}')">Approve</button> `;
      html += `<button class="btn btn-danger btn-sm" onclick="blockAsset('${a.id}')">Block</button>`;
    } else if (a.rights_status === 'approved_for_stream') {
      html += `<button class="btn btn-danger btn-sm" onclick="blockAsset('${a.id}')">Block</button>`;
    } else {
      html += `<button class="btn btn-primary btn-sm" onclick="approveAsset('${a.id}')">Approve</button>`;
    }
    html += '</td></tr>';
  }
  html += '</tbody></table>';
  return html;
}

async function approveAsset(id) {
  try {
    await api('PATCH', '/assets/' + id, { rights_status: 'approved_for_stream' });
    toast('Asset approved');
    loadAssets();
    loadDashboard();
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function blockAsset(id) {
  try {
    await api('PATCH', '/assets/' + id, { rights_status: 'blocked' });
    toast('Asset blocked');
    loadAssets();
    loadDashboard();
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function createAsset() {
  try {
    const body = {
      kind: document.getElementById('newKind').value,
      title: document.getElementById('newTitle').value,
      source_type: document.getElementById('newSourceType').value,
    };
    const url = document.getElementById('newSourceUrl').value;
    const path = document.getElementById('newLocalPath').value;
    const dur = document.getElementById('newDuration').value;
    const notes = document.getElementById('newNotes').value;
    if (url) body.source_url = url;
    if (path) body.local_source_path = path;
    if (dur) body.duration_sec = parseInt(dur);
    if (notes) body.notes = notes;
    if (!body.title) { toast('Title is required', 'error'); return; }
    await api('POST', '/assets', body);
    toast('Asset created');
    closeModal('addAssetModal');
    document.getElementById('newTitle').value = '';
    document.getElementById('newSourceUrl').value = '';
    document.getElementById('newLocalPath').value = '';
    document.getElementById('newDuration').value = '';
    document.getElementById('newNotes').value = '';
    loadAssets();
    loadDashboard();
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

// --- Discovery ---
async function loadDiscovery() {
  await Promise.all([
    loadKeywords(),
    loadDomainPolicies(),
    loadDiscoveryRuns(),
    loadCandidates(),
  ]);
}

async function loadKeywords() {
  try {
    const keywords = await api('GET', '/keywords');
    document.getElementById('keywordCount').textContent = keywords.length;
    const active = keywords.filter(k => k.active);
    const inactive = keywords.length - active.length;
    let html = `
      <div class="mini-summary">
        <span>${active.length} active</span>
        <span>${inactive} paused</span>
      </div>
    `;
    if (!keywords.length) {
      html += '<div class="empty-state compact"><p>No keywords yet</p></div>';
    } else {
      html += '<div class="stack-list">';
      for (const k of keywords) {
        html += `
          <div class="stack-item">
            <div>
              <strong>${escapeHtml(k.keyword)}</strong>
              <div class="muted">${escapeHtml(k.category || 'uncategorized')} · weight ${k.weight}</div>
            </div>
            <div class="inline-actions">
              ${badge(k.include ? 'include' : 'exclude', k.include ? 'green' : 'red')}
              ${badge(k.active ? 'active' : 'paused', k.active ? 'blue' : 'grey')}
              <button class="btn btn-secondary btn-sm" onclick="toggleKeyword('${k.id}', ${!k.active})">${k.active ? 'Pause' : 'Enable'}</button>
            </div>
          </div>
        `;
      }
      html += '</div>';
    }
    document.getElementById('keywordsList').innerHTML = html;
  } catch (e) {
    toast('Failed to load keywords: ' + e.message, 'error');
  }
}

async function createKeyword() {
  const keyword = document.getElementById('keywordText').value.trim();
  if (!keyword) { toast('Keyword is required', 'error'); return; }
  const include = document.querySelector('input[name="keywordInclude"]:checked').value === 'true';
  const body = {
    keyword,
    category: document.getElementById('keywordCategory').value.trim() || null,
    weight: parseFloat(document.getElementById('keywordWeight').value || '1'),
    include,
    active: true,
  };
  try {
    await api('POST', '/keywords', body);
    toast(include ? 'Keyword added' : 'Exclude term added');
    document.getElementById('keywordText').value = '';
    document.getElementById('keywordCategory').value = '';
    document.getElementById('keywordWeight').value = '1';
    loadKeywords();
  } catch (e) {
    toast('Keyword error: ' + e.message, 'error');
  }
}

async function toggleKeyword(id, active) {
  try {
    await api('PATCH', '/keywords/' + id, { active });
    toast(active ? 'Keyword enabled' : 'Keyword paused');
    loadKeywords();
  } catch (e) {
    toast('Keyword error: ' + e.message, 'error');
  }
}

async function loadDomainPolicies() {
  try {
    const domains = await api('GET', '/domain-policies');
    document.getElementById('domainCount').textContent = domains.length;
    let html = '';
    if (!domains.length) {
      html = '<div class="empty-state compact"><p>Nenhum site cadastrado ainda. Clique em + Add Site.</p></div>';
    } else {
      html = '<div class="stack-list">';
      for (const d of domains) {
        const adultIcon = d.is_adult ? '<span class="adult-icon">🔞</span> ' : '';
        const loginLabel = d.requires_login ? (d.credential_email ? '🔑 logged' : '🔑 no creds') : '';
        const hasTpl = d.search_url_template || d.user_url_template;
        html += `
          <div class="stack-item">
            <div>
              <strong>${adultIcon}${escapeHtml(d.domain)}</strong>
              <div class="muted">
                ${d.max_pages_per_run} pages/run
                ${hasTpl ? '· tpl ok' : '· <span style="color:#c33">no template</span>'}
                ${loginLabel ? '· ' + loginLabel : ''}
              </div>
            </div>
            <div class="inline-actions">
              ${badge(d.is_enabled ? 'enabled' : 'off', d.is_enabled ? 'green' : 'grey')}
              <button class="btn btn-secondary btn-sm" onclick="toggleDomain('${d.id}', ${!d.is_enabled})">${d.is_enabled ? 'Pause' : 'Enable'}</button>
              <button class="btn btn-secondary btn-sm" onclick="openDomainModalEdit('${d.id}')">Edit</button>
            </div>
          </div>
        `;
      }
      html += '</div>';
    }
    document.getElementById('domainsList').innerHTML = html;
  } catch (e) {
    toast('Failed to load domains: ' + e.message, 'error');
  }
}

function _clearDomainModal() {
  const ids = [
    'domainEditId', 'domainName', 'domainPages',
    'domainSearchTpl', 'domainUserTpl',
    'domainResultSel', 'domainTitleSel',
    'domainExts', 'domainTitleStrips',
    'domainLoginUrl', 'domainLoginEmailSel', 'domainLoginPassSel',
    'domainLoginSubmitSel', 'domainLoginSuccessSel',
    'domainCredEmail', 'domainCredPass',
  ];
  for (const id of ids) document.getElementById(id).value = '';
  document.getElementById('domainEnabled').checked = true;
  document.getElementById('domainIsAdult').checked = false;
  document.getElementById('domainRequiresLogin').checked = false;
  document.getElementById('domainNeedsIntercept').checked = false;
  document.getElementById('domainPages').value = '5';
  document.getElementById('domainExts').value = 'mp4, webm, m3u8';
}

function openDomainModal() {
  _clearDomainModal();
  document.getElementById('domainModalTitle').textContent = 'Add Site';
  document.getElementById('domainDeleteBtn').style.display = 'none';
  showModal('domainModal');
}

async function openDomainModalEdit(id) {
  _clearDomainModal();
  try {
    const d = await api('GET', '/domain-policies/' + id);
    document.getElementById('domainModalTitle').textContent = 'Edit Site — ' + d.domain;
    document.getElementById('domainEditId').value = d.id;
    document.getElementById('domainName').value = d.domain;
    document.getElementById('domainPages').value = d.max_pages_per_run || 5;
    document.getElementById('domainEnabled').checked = !!d.is_enabled;
    document.getElementById('domainIsAdult').checked = !!d.is_adult;
    document.getElementById('domainRequiresLogin').checked = !!d.requires_login;
    document.getElementById('domainNeedsIntercept').checked = !!d.needs_media_interception;
    document.getElementById('domainSearchTpl').value = d.search_url_template || '';
    document.getElementById('domainUserTpl').value = d.user_url_template || '';
    document.getElementById('domainResultSel').value = d.result_selector || '';
    document.getElementById('domainTitleSel').value = d.title_selector || '';
    document.getElementById('domainExts').value = (d.accepted_extensions || []).join(', ');
    document.getElementById('domainTitleStrips').value = (d.title_suffix_strips || []).join(', ');
    document.getElementById('domainLoginUrl').value = d.login_url || '';
    document.getElementById('domainLoginEmailSel').value = d.login_email_selector || '';
    document.getElementById('domainLoginPassSel').value = d.login_password_selector || '';
    document.getElementById('domainLoginSubmitSel').value = d.login_submit_selector || '';
    document.getElementById('domainLoginSuccessSel').value = d.login_success_selector || '';
    document.getElementById('domainCredEmail').value = d.credential_email || '';
    // password is never returned by API — leave blank
    document.getElementById('domainDeleteBtn').style.display = '';
    showModal('domainModal');
  } catch (e) {
    toast('Failed to load site: ' + e.message, 'error');
  }
}

function _parseCsvList(value) {
  return (value || '')
    .split(',')
    .map(s => s.trim())
    .filter(s => s.length > 0);
}

async function saveDomain() {
  const id = document.getElementById('domainEditId').value;
  const domain = document.getElementById('domainName').value.trim()
    .replace(/^https?:\/\//, '').replace(/\/.*$/, '');
  if (!domain) { toast('Domain é obrigatório', 'error'); return; }

  const exts = _parseCsvList(document.getElementById('domainExts').value);
  const strips = _parseCsvList(document.getElementById('domainTitleStrips').value);
  const pass = document.getElementById('domainCredPass').value;

  const body = {
    domain,
    is_enabled: document.getElementById('domainEnabled').checked,
    is_adult: document.getElementById('domainIsAdult').checked,
    requires_login: document.getElementById('domainRequiresLogin').checked,
    needs_media_interception: document.getElementById('domainNeedsIntercept').checked,
    max_pages_per_run: parseInt(document.getElementById('domainPages').value || '5'),
    search_url_template: document.getElementById('domainSearchTpl').value.trim() || null,
    user_url_template: document.getElementById('domainUserTpl').value.trim() || null,
    result_selector: document.getElementById('domainResultSel').value.trim() || null,
    title_selector: document.getElementById('domainTitleSel').value.trim() || null,
    accepted_extensions: exts.length ? exts : ['mp4', 'webm', 'm3u8', 'mpd'],
    title_suffix_strips: strips,
    login_url: document.getElementById('domainLoginUrl').value.trim() || null,
    login_email_selector: document.getElementById('domainLoginEmailSel').value.trim() || null,
    login_password_selector: document.getElementById('domainLoginPassSel').value.trim() || null,
    login_submit_selector: document.getElementById('domainLoginSubmitSel').value.trim() || null,
    login_success_selector: document.getElementById('domainLoginSuccessSel').value.trim() || null,
    credential_email: document.getElementById('domainCredEmail').value.trim() || null,
  };
  // Only send password if user actually typed something (otherwise keeps old value)
  if (pass) body.credential_password = pass;

  try {
    if (id) {
      await api('PATCH', '/domain-policies/' + id, body);
      toast('Site atualizado');
    } else {
      await api('POST', '/domain-policies', body);
      toast('Site adicionado');
    }
    closeModal('domainModal');
    loadDomainPolicies();
  } catch (e) {
    toast('Erro ao salvar: ' + e.message, 'error');
  }
}

async function deleteDomainFromModal() {
  const id = document.getElementById('domainEditId').value;
  if (!id) return;
  if (!confirm('Apagar este site? Essa ação não tem volta.')) return;
  try {
    await api('DELETE', '/domain-policies/' + id);
    toast('Site removido');
    closeModal('domainModal');
    loadDomainPolicies();
  } catch (e) {
    toast('Erro ao apagar: ' + e.message, 'error');
  }
}

async function toggleDomain(id, isEnabled) {
  try {
    await api('PATCH', '/domain-policies/' + id, { is_enabled: isEnabled });
    toast(isEnabled ? 'Site ativado' : 'Site pausado');
    loadDomainPolicies();
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
}

async function runDiscovery(simulated) {
  try {
    toast(simulated ? 'Running test discovery...' : 'Running real discovery...');
    const run = await api('POST', '/discovery/run' + (simulated ? '?simulated=true' : ''));
    const found = run.output_summary?.total_found ?? 0;
    const accepted = run.output_summary?.total_accepted ?? 0;
    toast(`Discovery finished: ${found} found, ${accepted} downloadable`);
    await Promise.all([loadDiscoveryRuns(), loadCandidates()]);
  } catch (e) {
    toast('Discovery error: ' + e.message, 'error');
  }
}

async function loadDiscoveryRuns() {
  try {
    const runs = await api('GET', '/discovery/runs');
    if (!runs.length) {
      document.getElementById('discoveryRuns').innerHTML = '<div class="empty-state compact"><p>No discovery runs yet</p></div>';
      return;
    }
    let html = '<table><thead><tr><th>Date</th><th>Status</th><th>Keywords</th><th>Found</th><th>Downloadable</th></tr></thead><tbody>';
    for (const run of runs.slice(0, 8)) {
      const input = run.input_summary || {};
      const output = run.output_summary || {};
      html += `
        <tr>
          <td>${escapeHtml(run.run_date)}</td>
          <td>${statusBadge(run.status)}</td>
          <td>${escapeHtml((input.include_keywords || []).slice(0, 4).join(', '))}</td>
          <td>${output.total_found ?? 0}</td>
          <td>${output.total_accepted ?? 0}</td>
        </tr>
      `;
    }
    html += '</tbody></table>';
    document.getElementById('discoveryRuns').innerHTML = html;
  } catch (e) {
    toast('Failed to load discovery runs: ' + e.message, 'error');
  }
}

async function loadCandidates() {
  try {
    const params = ['limit=100'];
    const retrieval = document.getElementById('candidateRetrievalFilter')?.value;
    const rights = document.getElementById('candidateRightsFilter')?.value;
    if (retrieval) params.push('retrieval_status=' + encodeURIComponent(retrieval));
    if (rights) params.push('rights_status=' + encodeURIComponent(rights));
    const candidates = await api('GET', '/candidates?' + params.join('&'));
    document.getElementById('candidatesTable').innerHTML = candidates.length
      ? candidateTable(candidates)
      : '<div class="empty-state"><p>No candidates yet. Add keywords and run a search.</p></div>';
  } catch (e) {
    toast('Failed to load candidates: ' + e.message, 'error');
  }
}

function candidateTable(candidates) {
  let html = '<table><thead><tr><th>Title</th><th>Retrieval</th><th>Rights</th><th>Discovery</th><th>Duration</th><th>Actions</th></tr></thead><tbody>';
  for (const c of candidates) {
    const url = c.source_url || c.page_url || '';
    html += '<tr>';
    html += `
      <td>
        <strong>${escapeHtml(c.title)}</strong>
        <div class="muted url-text">${escapeHtml(url)}</div>
      </td>
    `;
    html += `<td>${statusBadge(c.retrieval_status)}</td>`;
    html += `<td>${rightsBadge(c.rights_status)}</td>`;
    html += `<td>${statusBadge(c.discovery_status)}</td>`;
    html += `<td>${formatDuration(c.duration_sec)}</td>`;
    html += '<td><div class="inline-actions">';
    if (c.rights_status !== 'approved_for_stream') {
      html += `<button class="btn btn-primary btn-sm" onclick="approveCandidate('${c.id}')">Approve</button>`;
    }
    html += `<button class="btn btn-secondary btn-sm" onclick="promoteCandidate('${c.id}')">Promote</button>`;
    html += `<button class="btn btn-danger btn-sm" onclick="blockCandidate('${c.id}')">Block</button>`;
    html += '</div></td></tr>';
  }
  html += '</tbody></table>';
  return html;
}

async function approveCandidate(id) {
  try {
    await approveCandidateRecord(id);
    toast('Candidate approved');
    loadCandidates();
  } catch (e) {
    toast('Candidate error: ' + e.message, 'error');
  }
}

async function approveCandidateRecord(id) {
  return api('PATCH', '/candidates/' + id, {
    rights_status: 'approved_for_stream',
    discovery_status: 'accepted',
  });
}

async function blockCandidate(id) {
  try {
    await api('PATCH', '/candidates/' + id, {
      rights_status: 'blocked',
      discovery_status: 'rejected',
      rejection_reason: 'Blocked by operator',
    });
    toast('Candidate blocked');
    loadCandidates();
  } catch (e) {
    toast('Candidate error: ' + e.message, 'error');
  }
}

async function promoteCandidate(id) {
  try {
    await approveCandidateRecord(id);
    const promoted = await api('POST', '/acq/candidates/' + id + '/promote');
    toast('Promoted to library: ' + promoted.title);
    await Promise.all([loadCandidates(), loadAssets(), loadDashboard()]);
  } catch (e) {
    toast('Promote error: ' + e.message, 'error');
  }
}

// --- Plans ---
async function loadPlans() {
  document.getElementById('plansContent').innerHTML =
    '<div class="empty-state"><p>Carregando planos...</p></div>';
  try {
    const plans = await api('GET', '/plans');
    let html = `
      <div class="card">
        <div class="card-header">
          <span class="card-title">Planos de transmissão</span>
          <button class="btn btn-primary btn-sm" onclick="showGeneratePlan()">+ Gerar plano</button>
        </div>`;
    if (!plans.length) {
      html += '<div class="empty-state"><p>Nenhum plano ainda — o Diretor gera automaticamente quando a fila cai abaixo de 4h</p></div>';
    } else {
      html += '<table><thead><tr><th>Data</th><th>Status</th><th>Duração</th><th>Itens</th><th>Prontos</th><th>Concluídos</th><th></th></tr></thead><tbody>';
      for (const p of plans) {
        const dur = formatDuration(p.total_duration_sec);
        html += `<tr style="cursor:pointer" onclick="loadPlanDetail('${p.id}')">
          <td><strong>${p.plan_date || '—'}</strong></td>
          <td>${statusBadge(p.status)}</td>
          <td>${dur}</td>
          <td>${p.items_total}</td>
          <td>${p.items_ready}</td>
          <td>${p.items_completed}</td>
          <td><button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();loadPlanDetail('${p.id}')">Ver</button></td>
        </tr>`;
      }
      html += '</tbody></table>';
    }
    html += '</div>';
    html += `
      <div class="card" id="planDetailCard" style="display:none">
        <div class="card-header">
          <span class="card-title" id="planDetailTitle"></span>
          <div id="planActions"></div>
        </div>
        <div id="planInfo"></div>
        <div class="table-wrap" id="planItemsTable" style="margin-top:12px;max-height:400px;overflow-y:auto"></div>
      </div>`;
    document.getElementById('plansContent').innerHTML = html;
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  }
}

async function loadPlanDetail(id) {
  try {
    const plan = await api('GET', '/plans/' + id);
    showPlanDetail(plan);
    document.getElementById('planDetailCard').scrollIntoView({ behavior: 'smooth' });
  } catch (e) { toast('Plano não encontrado: ' + e.message, 'error'); }
}

async function generatePlan() {
  try {
    const body = {
      plan_date: document.getElementById('planDate').value,
      hours: parseInt(document.getElementById('planHours').value),
      mix_music: document.getElementById('planMixMusic').checked,
    };
    if (!body.plan_date) { toast('Date is required', 'error'); return; }
    toast('Generating plan...');
    const plan = await api('POST', '/plans/generate', body);
    toast('Plan generated: ' + plan.items.length + ' items');
    closeModal('genPlanModal');
    showPlanDetail(plan);
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function loadPlanById() {
  const id = document.getElementById('planIdInput').value.trim();
  if (!id) { toast('Enter a plan ID', 'error'); return; }
  try {
    const plan = await api('GET', '/plans/' + id);
    showPlanDetail(plan);
  } catch (e) { toast('Plan not found: ' + e.message, 'error'); }
}

function showPlanDetail(plan) {
  const card = document.getElementById('planDetailCard');
  card.style.display = '';
  document.getElementById('planDetailTitle').textContent =
    'Plan: ' + plan.plan_date + ' — ' + plan.items.length + ' items';

  let actions = '';
  if (plan.status === 'draft') {
    actions = `<button class="btn btn-primary btn-sm" onclick="approvePlan('${plan.id}')">Approve Plan</button>`;
  }
  if (plan.status === 'approved') {
    actions = `<button class="btn btn-primary btn-sm" onclick="runPrep()">Run Prep</button>`;
  }
  document.getElementById('planActions').innerHTML = actions;

  const items = plan.items || [];
  const ready = items.filter(i => i.prep_status === 'ready').length;
  const queued = items.filter(i => i.prep_status === 'queued').length;
  const totalSec = items.reduce((s, i) => s + (i.target_duration_sec || 0), 0);

  document.getElementById('planInfo').innerHTML = `
    <div class="stats-grid">
      <div class="stat-card"><div class="stat-label">Status</div><div class="stat-value">${statusBadge(plan.status)}</div></div>
      <div class="stat-card"><div class="stat-label">Items</div><div class="stat-value">${items.length}</div></div>
      <div class="stat-card"><div class="stat-label">Duration</div><div class="stat-value">${(totalSec/3600).toFixed(1)}h</div></div>
      <div class="stat-card"><div class="stat-label">Prep Ready</div><div class="stat-value green">${ready}</div></div>
      <div class="stat-card"><div class="stat-label">Queued</div><div class="stat-value yellow">${queued}</div></div>
    </div>
  `;

  const shown = items.slice(0, 50);
  let html = '<table><thead><tr><th>#</th><th>Prep</th><th>Stream</th><th>Duration</th><th>Mix</th></tr></thead><tbody>';
  for (const it of shown) {
    html += '<tr>';
    html += `<td>${it.sequence_index}</td>`;
    html += `<td>${statusBadge(it.prep_status)}</td>`;
    html += `<td>${statusBadge(it.stream_status)}</td>`;
    html += `<td>${it.target_duration_sec ? it.target_duration_sec + 's' : '—'}</td>`;
    html += `<td>${it.mix_enabled ? '🎵' : '—'}</td>`;
    html += '</tr>';
  }
  if (items.length > 50) {
    html += `<tr><td colspan="5" style="text-align:center;color:var(--text2)">... and ${items.length - 50} more items</td></tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('planItemsTable').innerHTML = html;
}

async function approvePlan(id) {
  try {
    const plan = await api('POST', '/plans/' + id + '/approve');
    toast('Plan approved');
    showPlanDetail(plan);
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function runPrep() {
  try {
    toast('Running prep cycle...');
    const res = await api('POST', '/prep/run-once');
    toast('Prep processed: ' + res.processed + ' items');
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

// --- Reports ---
async function loadReports() {
  try {
    const reports = await api('GET', '/reports');
    const today = new Date().toISOString().split('T')[0];
    let html = `
      <div class="card">
        <div class="card-header">
          <span class="card-title">Relatórios diários</span>
          <div class="header-actions">
            <button class="btn btn-secondary btn-sm" onclick="generateReport('${today}')">Gerar hoje</button>
          </div>
        </div>`;
    if (!reports.length) {
      html += '<div class="empty-state"><p>Nenhum relatório ainda — o Diretor gera automaticamente todo dia</p></div>';
    } else {
      html += '<table><thead><tr><th>Data</th><th>Status</th><th>Planejadas</th><th>Transmitidas</th><th>Falhas</th><th></th></tr></thead><tbody>';
      for (const r of reports) {
        const s = r.summary || {};
        html += `<tr style="cursor:pointer" onclick="loadReportByDate('${r.report_date}')">
          <td><strong>${r.report_date || '—'}</strong></td>
          <td>${statusBadge(r.status)}</td>
          <td>${s.planned_hours || 0}h</td>
          <td>${s.streamed_hours || 0}h</td>
          <td>${s.failed_items || 0}</td>
          <td><button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();loadReportByDate('${r.report_date}')">Ver</button></td>
        </tr>`;
      }
      html += '</tbody></table>';
    }
    html += `</div>
      <div id="reportContent"></div>`;
    document.getElementById('reportsContent').innerHTML = html;
  } catch (e) {
    toast('Erro ao carregar relatórios: ' + e.message, 'error');
  }
}

async function loadReportByDate(date) {
  try {
    const report = await api('GET', '/reports/' + date);
    document.getElementById('reportContent').innerHTML = renderReport(report);
    document.getElementById('reportContent').scrollIntoView({ behavior: 'smooth' });
  } catch (e) {
    document.getElementById('reportContent').innerHTML =
      `<div class="empty-state"><p>Relatório de ${date} não encontrado</p></div>`;
  }
}

async function generateReport(date) {
  if (!date) { toast('Data necessária', 'error'); return; }
  try {
    toast('Gerando relatório...');
    await api('POST', '/reports/' + date + '/generate');
    toast('Relatório gerado');
    loadReports();
  } catch (e) { toast('Erro: ' + e.message, 'error'); }
}

function renderReport(report) {
  const s = report.summary || {};
  let html = `<div class="card" style="margin-top:12px">
    <div class="card-header"><span class="card-title">Relatório ${report.report_date || ''}</span></div>
    <div class="stats-grid">`;
  html += `<div class="stat-card"><div class="stat-label">Planejado</div><div class="stat-value">${s.planned_hours || 0}h</div></div>`;
  html += `<div class="stat-card"><div class="stat-label">Transmitido</div><div class="stat-value accent">${s.streamed_hours || 0}h</div></div>`;
  html += `<div class="stat-card"><div class="stat-label">Concluídos</div><div class="stat-value green">${s.completed_items || 0}</div></div>`;
  html += `<div class="stat-card"><div class="stat-label">Falhas</div><div class="stat-value red">${s.failed_items || 0}</div></div>`;
  html += `<div class="stat-card"><div class="stat-label">Fallbacks</div><div class="stat-value yellow">${s.fallback_events || 0}</div></div>`;
  html += `<div class="stat-card"><div class="stat-label">Pendentes</div><div class="stat-value">${s.pending_review_assets || 0}</div></div>`;
  html += '</div>';
  if (s.suggestions && s.suggestions.length) {
    html += '<div style="margin-top:12px"><strong style="font-size:12px">Sugestões</strong><ul style="padding-left:20px;margin-top:6px">';
    for (const sug of s.suggestions) {
      html += `<li style="margin-bottom:4px;color:var(--text2);font-size:13px">${escapeHtml(sug)}</li>`;
    }
    html += '</ul></div>';
  }
  if (report.markdown_text) {
    html += `<div style="margin-top:12px"><pre style="white-space:pre-wrap;color:var(--text2);font-size:12px">${escapeHtml(report.markdown_text)}</pre></div>`;
  }
  html += '</div>';
  return html;
}

// --- Stream ---
async function streamStart() {
  try {
    await api('POST', '/stream/start');
    toast('Stream start requested');
    loadDashboard();
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function streamStop() {
  try {
    await api('POST', '/stream/stop');
    toast('Stream stop requested');
    loadDashboard();
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

// --- Observabilidade ---
let _obsTimer = null;

function startObs() {
  stopObs();
  refreshObs();
  _obsTimer = setInterval(refreshObs, 10000);
}

function stopObs() {
  if (_obsTimer) { clearInterval(_obsTimer); _obsTimer = null; }
}

function _fmtGB(bytes) {
  if (!bytes && bytes !== 0) return '—';
  return (bytes / 1024 / 1024 / 1024).toFixed(1) + ' GB';
}

function _dot(state) {
  return `<span class="dot ${state}"></span>`;
}

function _agoSec(iso) {
  if (!iso) return null;
  return Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
}

function _fmtAgo(sec) {
  if (sec === null || sec === undefined) return '—';
  if (sec < 60) return sec + 's ago';
  if (sec < 3600) return Math.floor(sec / 60) + 'm ago';
  if (sec < 86400) return Math.floor(sec / 3600) + 'h ago';
  return Math.floor(sec / 86400) + 'd ago';
}

async function refreshObs() {
  try {
    const s = await api('GET', '/obs/snapshot');
    document.getElementById('obsClock').textContent =
      'atualizado ' + new Date(s.now).toLocaleTimeString();

    // ── Signal ──
    const sig = s.signal;
    let sigState = 'red', sigLabel = 'OFF';
    if (sig.running && sig.status === 'streaming') { sigState = 'green'; sigLabel = 'LIVE'; }
    else if (sig.running && sig.status === 'fallback') { sigState = 'amber'; sigLabel = 'FALLBACK'; }
    else if (sig.running) { sigState = 'amber'; sigLabel = sig.status.toUpperCase(); }
    document.getElementById('obsSignalBadge').innerHTML =
      `${_dot(sigState)} ${sigLabel}`;

    let sigHtml = '';
    sigHtml += `<div class="obs-stat-row"><strong>Status</strong><span class="v">${escapeHtml(sig.status || '—')}</span></div>`;
    sigHtml += `<div class="obs-stat-row"><strong>Tocando</strong><span class="v">${sig.current ? escapeHtml(sig.current.title || '—') : '—'}</span></div>`;
    sigHtml += `<div class="obs-stat-row"><strong>Heartbeat</strong><span class="v">${_fmtAgo(sig.heartbeat_stale_sec)}</span></div>`;
    if (sig.next_5.length) {
      sigHtml += `<div class="muted" style="margin-top:10px;font-size:12px">Próximos:</div>`;
      sigHtml += '<ul style="padding-left:18px;margin:4px 0;font-size:12px;color:var(--text2)">';
      for (const n of sig.next_5) {
        sigHtml += `<li>${escapeHtml(n.title || '—')} <span style="opacity:.6">(${n.prep_status})</span></li>`;
      }
      sigHtml += '</ul>';
    }
    document.getElementById('obsSignal').innerHTML = sigHtml;

    // ── Pipeline ──
    const p = s.pipeline;
    const q = p.queued_hours || 0;
    const qPct = Math.min(100, q / 24 * 100);
    const qBar = q < 4 ? 'alert' : (q < 8 ? 'warn' : '');
    const disk = p.disk || {};
    const dPct = disk.used_pct || 0;
    const dBar = dPct > 85 ? 'alert' : (dPct > 70 ? 'warn' : '');

    let pHtml = '';
    pHtml += `<div class="obs-stat-row"><strong>Fila</strong><span class="v">${q.toFixed(1)} h</span></div>`;
    pHtml += `<div class="obs-bar ${qBar}"><div style="width:${qPct}%"></div></div>`;
    pHtml += `<div class="obs-stat-row"><strong>Disco</strong><span class="v">${_fmtGB(disk.used_bytes)} / ${_fmtGB(disk.total_bytes)} (${dPct}%)</span></div>`;
    pHtml += `<div class="obs-bar ${dBar}"><div style="width:${dPct}%"></div></div>`;
    if (p.plan) {
      pHtml += `<div class="obs-stat-row" style="margin-top:8px"><strong>Plano ativo</strong><span class="v">${p.plan.status}</span></div>`;
      pHtml += `<div class="obs-stat-row"><strong>Itens</strong><span class="v">${p.plan.items_ready} ready / ${p.plan.items_queued} queued / ${p.plan.items_total} total</span></div>`;
    } else {
      pHtml += '<div class="muted" style="margin-top:8px">Nenhum plano ativo</div>';
    }
    document.getElementById('obsPipeline').innerHTML = pHtml;

    // ── Brain ──
    const d = s.director;
    const lastAgo = _agoSec(d.last_run_at);
    document.getElementById('obsBrainBadge').textContent =
      d.last_run_at ? `última rodada ${_fmtAgo(lastAgo)}` : 'sem rodadas ainda';

    let bHtml = '';
    if (!d.recent_actions || !d.recent_actions.length) {
      bHtml = '<div class="empty-state compact"><p>Nenhuma ação ainda</p></div>';
    } else {
      bHtml = '<table class="action-table"><thead><tr><th>hora</th><th>verbo</th><th>por quê</th><th>status</th></tr></thead><tbody>';
      for (const a of d.recent_actions.slice(0, 30)) {
        const t = a.at ? new Date(a.at).toLocaleTimeString() : '—';
        const txt = a.error || a.why || '';
        bHtml += `<tr class="s-${a.status}"><td>${t}</td><td class="verb">${escapeHtml(a.verb)}</td><td class="why" title="${escapeHtml(txt)}">${escapeHtml(txt)}</td><td>${a.status}</td></tr>`;
      }
      bHtml += '</tbody></table>';
    }
    document.getElementById('obsBrain').innerHTML = bHtml;

    // ── Health ──
    const h = s.health;
    let hHtml = '';
    hHtml += `<div class="obs-stat-row"><strong>${_dot(h.ollama_reachable ? 'green' : 'red')}Ollama</strong><span class="v">${h.ollama_reachable ? 'online' : 'offline'}</span></div>`;
    hHtml += `<div class="obs-stat-row"><strong>Discovery</strong><span class="v">${h.last_discovery_at ? _fmtAgo(_agoSec(h.last_discovery_at)) : 'nunca'}</span></div>`;
    hHtml += `<div class="obs-stat-row"><strong>Health médio da biblioteca</strong><span class="v">${h.avg_health_score !== null ? h.avg_health_score.toFixed(2) : '—'}</span></div>`;
    document.getElementById('obsHealth').innerHTML = hHtml;
  } catch (e) {
    document.getElementById('obsClock').textContent = 'erro: ' + e.message;
  }
}

async function obsForceTick() {
  try {
    const r = await api('POST', '/director/tick');
    toast(`Rodada: ${r.executed} executadas, ${r.rejected} recusadas, ${r.failed} falhas`);
    refreshObs();
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
}

// --- Init ---
loadDashboard();
