import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Embedded HTML representation of LecturePack Admin Dashboard
const rawHtml = `<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LecturePack Gateway - Model Usage Viewer</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #F3F0E8; --panel: #FFFFFF; --panel2: #F7F4ED; --sunk: #F0ECE2;
    --ink: #1C1A16; --muted: #726A5F; --border: #241F19; --line: #E3DCCD;
    --blue: #3FB4C7; --blue-strong: #2A93A6; --blue-soft: #DDF5F9; --blue-ink: #0C6675;
    --orange: #EF5A1E; --orange-ink: #B83E0D; --orange-soft: #FBE2D5;
    --green: #107847; --green-soft: #D3F0DF; --red: #BA3024; --red-soft: #FADAD5; --yellow: #D99400; --yellow-soft: #FBEDC6;
    --shadow-ink: #241F19;
    --shadow-hard: 3px 3px 0 var(--shadow-ink);
    --shadow-hard-sm: 2px 2px 0 var(--shadow-ink);
    --shadow-hi: 0 4px 14px rgba(28,26,22,.08);
    --on-signal: #1C1A16;
    --motion-fast: 90ms;
    --motion-spring: cubic-bezier(.2,0,0,1);
    --motion-ease: cubic-bezier(.22,1,.36,1);
  }

  [data-theme="dark"] {
    --bg: #16191F; --panel: #1F242C; --panel2: #262C35; --sunk: #1A1E24;
    --ink: #ECE7DB; --muted: #A3AAB8; --border: #000000; --line: #4E5563;
    --blue: #B3EBF2; --blue-strong: #8FE0EA; --blue-soft: #123840; --blue-ink: #B3EBF2;
    --orange: #FF6C36; --orange-ink: #FF8A5C; --orange-soft: #38220F;
    --green: #4CCB86; --green-soft: #123020; --red: #FF6E5E; --red-soft: #361715; --yellow: #F2C24A; --yellow-soft: #332810;
    --shadow-ink: #000000;
    --shadow-hard: 3px 3px 0 var(--shadow-ink);
    --shadow-hard-sm: 2px 2px 0 var(--shadow-ink);
    --shadow-hi: 0 6px 18px rgba(0,0,0,.45);
    --on-signal: #131519;
  }

  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    background-color: var(--bg);
    color: var(--ink);
    font-family: 'Space Grotesk', system-ui, sans-serif;
    min-height: 100vh;
  }

  ::-webkit-scrollbar { width: 9px; height: 9px; }
  ::-webkit-scrollbar-thumb {
    background: var(--muted);
    border-radius: 10px;
    border: 2px solid var(--bg);
  }
  ::-webkit-scrollbar-thumb:hover { background: var(--blue); }

  .lp-mono { font-family: 'JetBrains Mono', monospace; }

  .lp-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    padding: 0 24px;
    height: 60px;
    background: var(--panel);
    border-bottom: 2px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .lp-header-line {
    position: absolute;
    left: 0; right: 0; bottom: -2px;
    height: 2px;
    background: linear-gradient(90deg, var(--blue), var(--orange));
  }

  .lp-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    padding: 3px 8px;
    border-radius: 6px;
    border: 1.5px solid var(--border);
    letter-spacing: .05em;
  }
  .lp-badge-nvidia { background: #76B900; color: #000; border-color: #4c7700; }
  .lp-badge-openrouter { background: var(--blue); color: #000; border-color: var(--blue-strong); }
  .lp-badge-workers-ai { background: var(--orange); color: #fff; border-color: var(--orange-ink); }
  .lp-badge-google { background: #4285F4; color: #fff; border-color: #1a73e8; }
  .lp-badge-success { background: var(--green-soft); color: var(--green); border-color: var(--green); }
  .lp-badge-failed { background: var(--red-soft); color: var(--red); border-color: var(--red); }
  .lp-badge-warn { background: var(--yellow-soft); color: var(--yellow); border-color: var(--yellow); }

  .lp-btn {
    font-family: 'Space Grotesk', system-ui, sans-serif;
    font-weight: 600;
    font-size: 13px;
    padding: 8px 14px;
    border: 2px solid var(--border);
    border-radius: 9px;
    background: var(--panel);
    color: var(--ink);
    cursor: pointer;
    box-shadow: var(--shadow-hard-sm);
    transition: transform var(--motion-fast) var(--motion-spring), box-shadow var(--motion-fast) var(--motion-ease), background var(--motion-fast) var(--motion-ease);
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .lp-btn:hover {
    transform: translateY(-1px);
    box-shadow: var(--shadow-hard);
    background: var(--panel2);
  }
  .lp-btn:active {
    transform: translateY(1px);
    box-shadow: 0 0 0 var(--shadow-ink);
  }
  .lp-btn-primary {
    background: var(--orange);
    color: var(--on-signal);
    border-color: var(--border);
  }
  .lp-btn-primary:hover {
    background: var(--orange-ink);
    color: #fff;
  }

  .lp-tab {
    font-family: 'Space Grotesk', system-ui, sans-serif;
    font-weight: 600;
    font-size: 13px;
    padding: 7px 14px;
    border: 2px solid var(--border);
    border-radius: 8px;
    background: var(--panel);
    color: var(--ink);
    cursor: pointer;
    box-shadow: var(--shadow-hard-sm);
    transition: all var(--motion-fast) var(--motion-spring);
  }
  .lp-tab:hover { background: var(--panel2); transform: translateY(-1px); }
  .lp-tab.active {
    background: var(--orange);
    color: var(--on-signal);
    font-weight: 700;
  }

  .lp-card {
    background: var(--panel);
    border: 2px solid var(--border);
    border-radius: 12px;
    padding: 18px 20px;
    box-shadow: var(--shadow-hard);
    position: relative;
  }

  .lp-input {
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    padding: 8px 12px;
    border: 2px solid var(--border);
    border-radius: 8px;
    background: var(--sunk);
    color: var(--ink);
    outline: none;
    transition: border-color var(--motion-fast) var(--motion-ease);
  }
  .lp-input:focus {
    border-color: var(--blue);
  }

  .lp-grid-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }

  .lp-table-container {
    overflow-x: auto;
    border: 2px solid var(--border);
    border-radius: 10px;
    background: var(--panel);
    box-shadow: var(--shadow-hard);
  }
  table.lp-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    text-align: left;
  }
  table.lp-table th {
    background: var(--panel2);
    border-bottom: 2px solid var(--border);
    padding: 12px 14px;
    font-weight: 700;
    color: var(--muted);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .05em;
  }
  table.lp-table td {
    padding: 12px 14px;
    border-bottom: 1px solid var(--line);
  }
  table.lp-table tr:last-child td { border-bottom: none; }
  table.lp-table tr:hover td { background: var(--panel2); }

  .lp-progress-bar {
    width: 100%;
    height: 8px;
    background: var(--sunk);
    border-radius: 4px;
    overflow: hidden;
    border: 1px solid var(--line);
  }
  .lp-progress-fill {
    height: 100%;
    background: var(--green);
    border-radius: 4px;
    transition: width 300ms ease;
  }

  .lp-pulse {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 8px var(--green);
    animation: lppulse 1.8s infinite;
  }
  @keyframes lppulse {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.3); opacity: 0.6; }
  }
</style>
</head>
<body>

<header class="lp-header">
  <div class="lp-header-line"></div>
  <div style="display:flex;align-items:center;gap:10px">
    <div style="width:28px;height:28px;background:var(--orange);border-radius:8px;display:flex;align-items:center;justify-content:center;box-shadow:0 0 12px rgba(239,90,30,.4)">
      <div style="width:10px;height:10px;background:#fff;transform:rotate(45deg);border-radius:2px"></div>
    </div>
    <span style="font-weight:700;font-size:16px;letter-spacing:-.01em">Lecture<span style="color:var(--orange)">Pack</span></span>
    <span class="lp-badge" style="background:var(--sunk);color:var(--muted)">Admin Gateway</span>
  </div>

  <div style="display:flex;align-items:center;gap:12px">
    <div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)" class="lp-mono">
      <span class="lp-pulse" id="status-dot"></span>
      <span id="connection-status">Ready</span>
    </div>
    <button class="lp-btn" id="btn-theme-toggle" type="button" title="Toggle Dark/Light Mode">
      <span id="theme-icon">☀️</span>
    </button>
  </div>
</header>

<main style="max-width:1300px;margin:0 auto;padding:24px 20px">

  <!-- Control & Authentication Bar -->
  <section class="lp-card" style="margin-bottom:24px">
    <div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:16px">
      <div style="display:flex;flex-wrap:wrap;align-items:center;gap:12px;flex:1;min-width:300px">
        <label for="admin-key-input" style="font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase" class="lp-mono">Admin Key</label>
        <input type="password" id="admin-key-input" class="lp-input" placeholder="Enter ADMIN_API_KEY" style="width:240px">
        <input type="text" id="gateway-url-input" class="lp-input" placeholder="Gateway URL (defaults to current)" style="width:260px" value="">
        <button class="lp-btn lp-btn-primary" id="btn-fetch" type="button">Connect & Refresh</button>
      </div>

      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase" class="lp-mono">Window:</span>
        <button class="lp-tab active" data-window="24h">24h</button>
        <button class="lp-tab" data-window="7d">7d</button>
        <button class="lp-tab" data-window="30d">30d</button>
        <button class="lp-tab" data-window="all">All</button>
      </div>
    </div>
  </section>

  <!-- Key Metrics Row -->
  <section class="lp-grid-stats">
    <div class="lp-card">
      <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase" class="lp-mono">Total Model Requests</div>
      <div style="font-size:32px;font-weight:700;margin-top:6px" class="lp-mono" id="stat-total-calls">0</div>
      <div style="font-size:12px;margin-top:4px" id="stat-success-rate">0% Success</div>
    </div>

    <div class="lp-card">
      <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase" class="lp-mono">Prompt Tokens (In)</div>
      <div style="font-size:32px;font-weight:700;margin-top:6px;color:var(--blue-ink)" class="lp-mono" id="stat-input-tokens">0</div>
      <div style="font-size:12px;color:var(--muted);margin-top:4px">Aggregated input</div>
    </div>

    <div class="lp-card">
      <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase" class="lp-mono">Completion Tokens (Out)</div>
      <div style="font-size:32px;font-weight:700;margin-top:6px;color:var(--orange-ink)" class="lp-mono" id="stat-output-tokens">0</div>
      <div style="font-size:12px;color:var(--muted);margin-top:4px">Aggregated output</div>
    </div>

    <div class="lp-card">
      <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase" class="lp-mono">Average Latency</div>
      <div style="font-size:32px;font-weight:700;margin-top:6px" class="lp-mono" id="stat-avg-latency">0 ms</div>
      <div style="font-size:12px;color:var(--muted);margin-top:4px">End-to-end model time</div>
    </div>

    <div class="lp-card">
      <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase" class="lp-mono">OpenRouter Balance</div>
      <div style="font-size:30px;font-weight:700;margin-top:6px;color:var(--green)" class="lp-mono" id="stat-openrouter-credit">--</div>
      <div style="font-size:12px;color:var(--muted);margin-top:4px" id="stat-openrouter-usage">Live account credits</div>
    </div>
  </section>

  <!-- Models Breakdown Table -->
  <section style="margin-bottom:28px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <h2 style="font-size:16px;font-weight:700;margin:0;display:flex;align-items:center;gap:8px">
        <span>Provider & Model Usage Breakdown</span>
      </h2>
      <span class="lp-badge" style="background:var(--sunk);color:var(--muted)" id="models-count-badge">0 Models</span>
    </div>
    <div class="lp-table-container">
      <table class="lp-table" id="models-table">
        <thead>
          <tr>
            <th>Provider</th>
            <th>Model</th>
            <th>Total Calls</th>
            <th>Success Rate</th>
            <th>Input Tokens</th>
            <th>Output Tokens</th>
            <th>Avg Latency</th>
          </tr>
        </thead>
        <tbody id="models-tbody">
          <tr><td colspan="7" style="text-align:center;color:var(--muted);padding:24px">No model data recorded yet. Connect to fetch usage stats.</td></tr>
        </tbody>
      </table>
    </div>
  </section>

  <!-- Two Column: Task Breakdown & Route Health -->
  <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(360px, 1fr));gap:20px;margin-bottom:28px">
    <!-- Tasks Table -->
    <section>
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <h2 style="font-size:16px;font-weight:700;margin:0">Usage by Study Task</h2>
      </div>
      <div class="lp-table-container">
        <table class="lp-table" id="tasks-table">
          <thead>
            <tr>
              <th>Task Type</th>
              <th>Calls</th>
              <th>Success Rate</th>
              <th>Avg Latency</th>
            </tr>
          </thead>
          <tbody id="tasks-tbody">
            <tr><td colspan="4" style="text-align:center;color:var(--muted);padding:18px">No task activity logged.</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Provider Health & Cooldowns -->
    <section>
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <h2 style="font-size:16px;font-weight:700;margin:0">Route Health & Cooldown Status</h2>
      </div>
      <div class="lp-table-container">
        <table class="lp-table" id="health-table">
          <thead>
            <tr>
              <th>Route ID</th>
              <th>Consecutive Fails</th>
              <th>Last Error</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="health-tbody">
            <tr><td colspan="4" style="text-align:center;color:var(--muted);padding:18px">All routes healthy.</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <!-- Recent Operational Events Feed -->
  <section style="margin-bottom:28px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <h2 style="font-size:16px;font-weight:700;margin:0">Recent Operational Events (Last 50)</h2>
      <span class="lp-badge" style="background:var(--sunk);color:var(--muted)">Metadata Only</span>
    </div>
    <div class="lp-table-container">
      <table class="lp-table" id="events-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Task</th>
            <th>Provider / Model</th>
            <th>Status</th>
            <th>Latency</th>
            <th>Tokens (In/Out)</th>
          </tr>
        </thead>
        <tbody id="events-tbody">
          <tr><td colspan="6" style="text-align:center;color:var(--muted);padding:24px">No recent events recorded.</td></tr>
        </tbody>
      </table>
    </div>
  </section>

</main>

<script>
  let activeWindow = '24h';
  const STORAGE_KEY_ADMIN = 'lp_admin_gateway_key';
  const STORAGE_KEY_URL = 'lp_admin_gateway_url';
  const STORAGE_KEY_THEME = 'lp_admin_theme';

  const adminKeyInput = document.getElementById('admin-key-input');
  const gatewayUrlInput = document.getElementById('gateway-url-input');
  const btnFetch = document.getElementById('btn-fetch');
  const btnThemeToggle = document.getElementById('btn-theme-toggle');
  const themeIcon = document.getElementById('theme-icon');
  const statusDot = document.getElementById('status-dot');
  const statusText = document.getElementById('connection-status');

  const DEFAULT_PRODUCTION_URL = 'https://lecturepack-ai-gateway.discordsammy2.workers.dev';

  // Parse URL search params or hash params: #key=... or ?key=...
  const urlSearch = new URLSearchParams(window.location.search);
  const hashString = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash;
  const hashSearch = new URLSearchParams(hashString);
  const paramKey = hashSearch.get('key') || urlSearch.get('key');
  const paramUrl = hashSearch.get('url') || urlSearch.get('url');

  if (paramKey) {
    adminKeyInput.value = paramKey;
    localStorage.setItem(STORAGE_KEY_ADMIN, paramKey);
  } else if (localStorage.getItem(STORAGE_KEY_ADMIN)) {
    adminKeyInput.value = localStorage.getItem(STORAGE_KEY_ADMIN);
  }

  if (paramUrl) {
    gatewayUrlInput.value = paramUrl;
    localStorage.setItem(STORAGE_KEY_URL, paramUrl);
  } else if (localStorage.getItem(STORAGE_KEY_URL)) {
    gatewayUrlInput.value = localStorage.getItem(STORAGE_KEY_URL);
  } else if (!window.location.origin || window.location.origin === 'null' || window.location.protocol === 'file:') {
    gatewayUrlInput.value = DEFAULT_PRODUCTION_URL;
  }

  const savedTheme = localStorage.getItem(STORAGE_KEY_THEME) || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);
  themeIcon.textContent = savedTheme === 'dark' ? '🌙' : '☀️';

  btnThemeToggle.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem(STORAGE_KEY_THEME, next);
    themeIcon.textContent = next === 'dark' ? '🌙' : '☀️';
  });

  // Time window buttons
  document.querySelectorAll('.lp-tab[data-window]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.lp-tab[data-window]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeWindow = btn.dataset.window;
      fetchUsageData();
    });
  });

  btnFetch.addEventListener('click', () => {
    localStorage.setItem(STORAGE_KEY_ADMIN, adminKeyInput.value.trim());
    localStorage.setItem(STORAGE_KEY_URL, gatewayUrlInput.value.trim());
    fetchUsageData();
  });

  function formatNumber(num) {
    return Number(num || 0).toLocaleString();
  }

  function formatTime(isoOrTs) {
    if (!isoOrTs) return '-';
    const date = new Date(isoOrTs);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' ' + date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  function getProviderBadge(provider) {
    const p = String(provider || '').toLowerCase();
    if (p.includes('nvidia')) return '<span class="lp-badge lp-badge-nvidia">NVIDIA</span>';
    if (p.includes('openrouter')) return '<span class="lp-badge lp-badge-openrouter">OpenRouter</span>';
    if (p.includes('workers')) return '<span class="lp-badge lp-badge-workers-ai">Workers AI</span>';
    if (p.includes('openai') || p.includes('google') || p.includes('gemini')) return '<span class="lp-badge lp-badge-google">Google AI</span>';
    return '<span class="lp-badge" style="background:var(--sunk);color:var(--muted)">' + provider + '</span>';
  }

  async function fetchUsageData(isSilent = false) {
    const adminKey = adminKeyInput.value.trim();
    if (!adminKey) {
      statusDot.style.background = 'var(--yellow)';
      statusDot.style.boxShadow = '0 0 8px var(--yellow)';
      statusText.textContent = 'Enter Key';
      return;
    }

    let baseUrl = gatewayUrlInput.value.trim();
    if (!baseUrl) {
      if (window.location.origin && window.location.origin !== 'null' && window.location.protocol !== 'file:') {
        baseUrl = window.location.origin;
      } else {
        baseUrl = DEFAULT_PRODUCTION_URL;
      }
    }

    if (!isSilent) {
      statusDot.style.background = 'var(--yellow)';
      statusDot.style.boxShadow = '0 0 8px var(--yellow)';
      statusText.textContent = 'Fetching...';
    }

    try {
      const url = baseUrl.replace(/\\/+$/, '') + '/v1/admin/stats?window=' + encodeURIComponent(activeWindow);
      const res = await fetch(url, {
        headers: {
          'x-admin-key': adminKey,
          'Authorization': 'Bearer ' + adminKey
        }
      });

      if (res.status === 401 || res.status === 403) {
        statusDot.style.background = 'var(--red)';
        statusDot.style.boxShadow = '0 0 8px var(--red)';
        statusText.textContent = 'Unauthorized (Check Key)';
        alert('Invalid admin key. Please enter the correct ADMIN_API_KEY secret.');
        return;
      }

      if (!res.ok) {
        throw new Error('HTTP ' + res.status + ': ' + res.statusText);
      }

      const data = await res.json();
      renderDashboard(data);

      statusDot.style.background = 'var(--green)';
      statusDot.style.boxShadow = '0 0 8px var(--green)';
      statusText.textContent = 'Connected';
    } catch (err) {
      statusDot.style.background = 'var(--red)';
      statusDot.style.boxShadow = '0 0 8px var(--red)';
      statusText.textContent = 'Error';
      console.error('Failed to fetch admin stats:', err);
    }
  }

  function renderDashboard(data) {
    const summary = data.summary || {};
    const models = data.models || [];
    const tasks = data.tasks || [];
    const health = data.health || [];
    const events = data.recent_events || [];
    const openrouter = data.openrouter_balance;

    // Summary Cards
    const totalCalls = Number(summary.total_calls || 0);
    const successCalls = Number(summary.successful_calls || 0);
    const successRate = totalCalls > 0 ? ((successCalls / totalCalls) * 100).toFixed(1) : '100.0';

    document.getElementById('stat-total-calls').textContent = formatNumber(totalCalls);
    document.getElementById('stat-success-rate').textContent = successRate + '% Success (' + formatNumber(successCalls) + ' ok / ' + formatNumber(summary.failed_calls) + ' fail)';
    document.getElementById('stat-input-tokens').textContent = formatNumber(summary.total_input_tokens);
    document.getElementById('stat-output-tokens').textContent = formatNumber(summary.total_output_tokens);
    document.getElementById('stat-avg-latency').textContent = (summary.avg_latency_ms || 0) + ' ms';

    // OpenRouter Credit
    if (openrouter && openrouter.ok && openrouter.data) {
      const orData = openrouter.data;
      const limit = orData.limit != null ? '$' + orData.limit : 'Pay-as-you-go';
      const usage = orData.usage != null ? '$' + Number(orData.usage).toFixed(2) : '$0.00';
      const balance = orData.limit_remaining != null ? '$' + Number(orData.limit_remaining).toFixed(2) : 'Active';
      document.getElementById('stat-openrouter-credit').textContent = balance;
      document.getElementById('stat-openrouter-usage').textContent = 'Usage: ' + usage + ' | Cap: ' + limit;
    } else if (openrouter && openrouter.ok === false) {
      document.getElementById('stat-openrouter-credit').textContent = 'Error';
      document.getElementById('stat-openrouter-usage').textContent = 'Check OPENROUTER_API_KEY';
    } else {
      document.getElementById('stat-openrouter-credit').textContent = 'N/A';
      document.getElementById('stat-openrouter-usage').textContent = 'No key configured';
    }

    // Models Table
    document.getElementById('models-count-badge').textContent = models.length + ' Model' + (models.length === 1 ? '' : 's');
    const modelsTbody = document.getElementById('models-tbody');
    if (!models.length) {
      modelsTbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:24px">No model requests logged in this window.</td></tr>';
    } else {
      modelsTbody.innerHTML = models.map(function(m) {
        const calls = Number(m.total_calls || 0);
        const ok = Number(m.successful_calls || 0);
        const rate = calls > 0 ? ((ok / calls) * 100).toFixed(1) : '100.0';
        return '<tr>'
          + '<td>' + getProviderBadge(m.provider) + '</td>'
          + '<td class="lp-mono" style="font-weight:600">' + m.model + '</td>'
          + '<td class="lp-mono">' + formatNumber(calls) + '</td>'
          + '<td style="min-width:140px">'
          + '  <div style="display:flex;align-items:center;gap:8px">'
          + '    <span class="lp-mono" style="font-size:12px;width:45px">' + rate + '%</span>'
          + '    <div class="lp-progress-bar">'
          + '      <div class="lp-progress-fill" style="width:' + rate + '%;background:' + (rate < 95 ? 'var(--red)' : 'var(--green)') + '"></div>'
          + '    </div>'
          + '  </div>'
          + '</td>'
          + '<td class="lp-mono">' + formatNumber(m.input_tokens) + '</td>'
          + '<td class="lp-mono">' + formatNumber(m.output_tokens) + '</td>'
          + '<td class="lp-mono">' + m.avg_latency_ms + ' ms</td>'
          + '</tr>';
      }).join('');
    }

    // Tasks Table
    const tasksTbody = document.getElementById('tasks-tbody');
    if (!tasks.length) {
      tasksTbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:18px">No tasks recorded.</td></tr>';
    } else {
      tasksTbody.innerHTML = tasks.map(function(t) {
        const calls = Number(t.total_calls || 0);
        const ok = Number(t.successful_calls || 0);
        const rate = calls > 0 ? ((ok / calls) * 100).toFixed(1) : '100.0';
        return '<tr>'
          + '<td class="lp-mono" style="font-weight:600;color:var(--orange-ink)">' + t.task + '</td>'
          + '<td class="lp-mono">' + formatNumber(calls) + '</td>'
          + '<td class="lp-mono">' + rate + '%</td>'
          + '<td class="lp-mono">' + t.avg_latency_ms + ' ms</td>'
          + '</tr>';
      }).join('');
    }

    // Health Table
    const healthTbody = document.getElementById('health-tbody');
    if (!health.length) {
      healthTbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:18px">All routes healthy.</td></tr>';
    } else {
      healthTbody.innerHTML = health.map(function(h) {
        const fails = Number(h.consecutive_failures || 0);
        const isCooling = fails >= 2;
        const statusBadge = isCooling
          ? '<span class="lp-badge lp-badge-warn">Cooling Down (' + fails + ' fails)</span>'
          : (fails > 0
            ? '<span class="lp-badge lp-badge-failed">1 Failure</span>'
            : '<span class="lp-badge lp-badge-success">Healthy</span>');
        return '<tr>'
          + '<td class="lp-mono" style="font-weight:600">' + h.route_id + '</td>'
          + '<td class="lp-mono">' + fails + '</td>'
          + '<td class="lp-mono" style="font-size:11px;color:var(--muted)">' + (h.last_error_code || 'None') + '</td>'
          + '<td>' + statusBadge + '</td>'
          + '</tr>';
      }).join('');
    }

    // Recent Events Table
    const eventsTbody = document.getElementById('events-tbody');
    if (!events.length) {
      eventsTbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:24px">No recent events.</td></tr>';
    } else {
      eventsTbody.innerHTML = events.map(function(e) {
        const isOk = Number(e.success) === 1;
        const statusBadge = isOk
          ? '<span class="lp-badge lp-badge-success">200 OK</span>'
          : '<span class="lp-badge lp-badge-failed">' + (e.status_code || 'ERR') + ' ' + (e.failure_code || '') + '</span>';
        return '<tr>'
          + '<td class="lp-mono" style="font-size:12px;color:var(--muted)">' + formatTime(e.created_at) + '</td>'
          + '<td class="lp-mono" style="font-weight:600">' + e.task + '</td>'
          + '<td class="lp-mono">' + getProviderBadge(e.provider) + ' <span style="font-size:12px;margin-left:4px">' + e.model + '</span></td>'
          + '<td>' + statusBadge + '</td>'
          + '<td class="lp-mono">' + e.latency_ms + ' ms</td>'
          + '<td class="lp-mono">' + formatNumber(e.input_tokens) + ' / ' + formatNumber(e.output_tokens) + '</td>'
          + '</tr>';
      }).join('');
    }
  }

  // Initial trigger if key exists
  if (adminKeyInput.value.trim()) {
    fetchUsageData();
  }

  // Continuous live background polling every 10 seconds
  setInterval(function() {
    if (adminKeyInput.value.trim() && !document.hidden) {
      fetchUsageData(true);
    }
  }, 10000);
</script>

</body>
</html>`;

export const DASHBOARD_HTML = rawHtml;
