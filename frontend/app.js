let dashboard = null;
let map = null;
let markers = [];
let selectedSeverity = 'ALL';
let conversation = [];

const number = value => new Intl.NumberFormat('en-IN').format(value || 0);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));

async function loadDashboard() {
  const response = await fetch('/api/dashboard');
  dashboard = await response.json();
  renderMetrics();
  renderMap();
  renderPriorities();
  renderPriorityCases();
  renderStates();
  renderAnomalies();
  document.querySelector('#side-anomalies').textContent = number(dashboard.anomalies.reduce((sum, item) => sum + item.count, 0));
}

async function renderPriorityCases() {
  const container = document.querySelector('#priority-cases');
  try {
    const response = await fetch('/api/priority-cases?limit=10');
    const data = await response.json();
    container.innerHTML = data.cases.length ? data.cases.map((item, index) => `<article class="priority-case ${item.severity.toLowerCase()}"><div class="case-rank">${String(index + 1).padStart(2, '0')}<small>PRIORITY</small></div><div class="case-body"><div class="case-heading"><strong>${escapeHtml(item.claim_id)}</strong><span>${escapeHtml(item.severity)} · ${item.priority_score}/100</span></div><div class="case-location">${escapeHtml(item.district)}, ${escapeHtml(item.state)} · ${escapeHtml(item.status)}</div><h3>${escapeHtml(item.problem)}</h3><div class="case-evidence">${item.reasons.map(reason => `<span>• ${escapeHtml(reason)}</span>`).join('')}${item.evidence ? `<span>• ${escapeHtml(item.evidence)}</span>` : ''}</div><div class="case-action"><b>Suggested next step</b>${escapeHtml(item.suggested_action)}</div></div></article>`).join('') : '<div class="empty-state">No priority cases require attention.</div>';
  } catch (error) {
    container.innerHTML = '<div class="empty-state">Priority cases are temporarily unavailable.</div>';
  }
}

function renderMetrics() {
  const summary = dashboard.summary;
  const flagged = dashboard.anomalies.reduce((sum, item) => sum + item.count, 0);
  const approvedRate = Math.round((summary.approved_claims / summary.total_claims) * 100);
  document.querySelector('#metrics').innerHTML = [
    ['TOTAL CLAIMS', number(summary.total_claims), 'Across 7 monitored states', ''],
    ['APPROVED', number(summary.approved_claims), `${approvedRate}% of registered claims`, ''],
    ['PENDING REVIEW', number(summary.pending_claims), 'Claims awaiting resolution', 'alert'],
    ['REJECTED', number(dashboard.rejected), 'Final decisions recorded', ''],
    ['POTENTIAL SIGNALS', number(flagged), `${summary.missing_decisions || 0} missing decisions included`, 'alert'],
    ['HIGH-RISK DISTRICTS', number(dashboard.high_risk_districts), 'Prioritized for attention', 'alert']
  ].map(([label, value, caption, cls]) => `<div class="metric ${cls}"><div class="metric-label">${label}</div><div class="metric-value">${value}</div><div class="metric-caption">${caption}</div></div>`).join('');
}

function renderMap() {
  if (!map) {
    map = L.map('map', {zoomControl: false}).setView([22.5, 79.5], 5.2);
    L.control.zoom({position: 'bottomright'}).addTo(map);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {attribution: '&copy; OpenStreetMap &copy; CARTO'}).addTo(map);
  }
  markers.forEach(marker => marker.remove());
  markers = dashboard.districts.filter(d => d.latitude && d.longitude).map(district => {
    const color = district.high_anomalies > 0 ? '#c85448' : district.anomaly_count > 0 ? '#d17a3e' : '#237b5a';
    const marker = L.circleMarker([district.latitude, district.longitude], {radius: Math.min(14, 6 + Math.log((district.total_claims || 1) / 100)), fillColor: color, color: '#fff', weight: 1.5, fillOpacity: .85});
    marker.bindPopup(`<strong>${escapeHtml(district.district_name)}</strong><br>${escapeHtml(district.state_name)}<br><b>${number(district.total_claims)}</b> claims · <b>${number(district.anomaly_count)}</b> potential signals`);
    marker.addTo(map);
    return marker;
  });
}

function renderPriorities() {
  const districts = dashboard.districts.slice(0, 8);
  document.querySelector('#district-count').textContent = `${dashboard.districts.length} districts`;
  document.querySelector('#priority-list').innerHTML = districts.map((district, index) => {
    const score = Math.min(100, Math.round(((district.high_anomalies || 0) * 3 + (district.anomaly_count || 0)) / Math.max(1, district.total_claims) * 4000));
    return `<div class="priority-row"><span class="rank">0${index + 1}</span><div class="priority-name">${escapeHtml(district.district_name)}<span class="priority-state">${escapeHtml(district.state_name)} · ${number(district.total_claims)} claims</span><div class="risk-bar"><i style="width:${Math.max(9, score)}%"></i></div></div><div class="priority-score">${number(district.anomaly_count)}<small> signals</small></div></div>`;
  }).join('');
}

function renderStates() {
  const sort = document.querySelector('#state-sort').value;
  const states = [...dashboard.states].sort((a, b) => b[sort] - a[sort]);
  const max = Math.max(...states.map(state => state.total_claims));
  document.querySelector('#state-table').innerHTML = states.map(state => `<tr><td class="state-name">${escapeHtml(state.state)}</td><td>${number(state.total_claims)}</td><td>${number(state.approved_claims)}</td><td>${number(state.pending_claims)}</td><td><b>${number(state.flagged_claims)}</b></td><td><div class="state-bar"><i style="width:${Math.round(state.approved_claims / max * 100)}%"></i></div></td></tr>`).join('');
}

function renderAnomalies() {
  const rows = dashboard.recent_anomalies.filter(item => selectedSeverity === 'ALL' || item.severity === selectedSeverity);
  document.querySelector('#anomaly-list').innerHTML = rows.slice(0, 40).map(item => `<div class="anomaly-row ${item.severity.toLowerCase()}"><div class="anomaly-severity">${escapeHtml(item.severity)}<div class="type-label">${escapeHtml(item.anomaly_type.replaceAll('_', ' '))}</div></div><div><div class="anomaly-title">${escapeHtml(item.description)}</div><div class="anomaly-detail">${escapeHtml(item.evidence)}</div></div><div class="anomaly-claim">${escapeHtml(item.claim_id)}<div class="type-label">${escapeHtml(item.district)}</div></div></div>`).join('');
}

async function searchClaims() {
  const query = document.querySelector('#query').value.trim();
  const container = document.querySelector('#search-results');
  if (!query) { container.innerHTML = '<div class="empty-state">Enter a claim, state, district, village, or status.</div>'; return; }
  const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
  const data = await response.json();
  container.innerHTML = data.results.length ? data.results.slice(0, 8).map(item => `<div class="search-item"><strong>${escapeHtml(item.claim_id)} · ${escapeHtml(item.status)}</strong><span>${escapeHtml(item.district)}, ${escapeHtml(item.state)} · ${item.anomaly_type ? escapeHtml(item.anomaly_type.replaceAll('_', ' ')) : 'No signal'}</span></div>`).join('') : '<div class="empty-state">No matching records.</div>';
}

function setQuestion(question) {
  document.querySelector('#query').value = question;
  askAssistant();
}

function setPortalQuestion(question) {
  document.querySelector('#query').value = question;
  document.querySelector('#state-section').scrollIntoView({behavior: 'smooth'});
  askAssistant();
}

function usePortalSearch() {
  const value = document.querySelector('#portal-query').value.trim();
  if (!value) return;
  if (/^FRA-\d+$/i.test(value)) {
    document.querySelector('#query').value = value;
    document.querySelector('#state-section').scrollIntoView({behavior: 'smooth'});
    searchClaims();
    return;
  }
  setPortalQuestion(value);
}

function skipToContent() {
  const content = document.querySelector('#main-content');
  content.focus({preventScroll: true});
  content.scrollIntoView({behavior: 'smooth', block: 'start'});
}

function showLanguageNotice() {
  window.alert('Hindi content is planned for a future version of this prototype.');
}

function showAccessibilityNotice() {
  window.alert('Accessibility controls: use Tab to navigate, Enter to activate controls, and Ctrl+F5 to refresh live data.');
}

async function askAssistant() {
  const query = document.querySelector('#query').value.trim();
  const container = document.querySelector('#search-results');
  if (!query) {
    container.innerHTML = '<div class="empty-state">Type a question first.</div>';
    return;
  }
  if (/^FRA-\d+$/i.test(query)) {
    searchClaims();
    return;
  }
  conversation.push({role: 'user', content: query});
  renderConversation();
  container.innerHTML = '<div class="empty-state">Reading the monitoring register...</div>';
  try {
    const response = await fetch('/api/ai/query', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: query, history: conversation.slice(0, -1)})
    });
    if (!response.ok) throw new Error('Assistant request failed');
    const result = await response.json();
    conversation.push({role: 'assistant', content: result.answer, provider: result.provider});
    renderConversation();
    container.innerHTML = '';
  } catch (error) {
    container.innerHTML = `<div class="empty-state">The assistant could not answer right now. Try again or search for a claim ID.</div>`;
  }
}

function renderConversation() {
  const history = document.querySelector('#chat-history');
  history.innerHTML = conversation.length ? conversation.map(item => `<div class="chat-message ${item.role}"><span>${item.role === 'user' ? 'YOU' : 'VANADHIKAR AI'}</span><p>${escapeHtml(item.content)}</p>${item.provider ? `<small>${escapeHtml(item.provider)}</small>` : ''}</div>`).join('') : '<div class="empty-state">Start a conversation about the live monitoring register.</div>';
  history.scrollTop = history.scrollHeight;
}

document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => { document.querySelectorAll('.filter').forEach(item => item.classList.remove('active')); button.classList.add('active'); selectedSeverity = button.dataset.severity; renderAnomalies(); }));
loadDashboard().catch(error => { document.querySelector('#metrics').innerHTML = `<div class="panel">Unable to load dashboard data: ${escapeHtml(error.message)}</div>`; });
