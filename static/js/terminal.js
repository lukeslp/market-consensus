/* ============================================================
   FORESIGHT TERMINAL — Unified Application Script
   ============================================================ */
(function () {
  'use strict';

  // ── Configuration ──────────────────────────────────────────
  const API_ROOT = (() => {
    const base = window.location.pathname.replace(/\/+$/, '');
    const idx = base.indexOf('/static');
    return (idx > 0 ? base.substring(0, idx) : base) + '/api';
  })();

  const PROVIDER_MODELS = {
    anthropic:   { name: 'Anthropic',   model: 'claude-sonnet-4-6' },
    openai:      { name: 'OpenAI',      model: 'gpt-5.2' },
    gemini:      { name: 'Gemini',      model: 'gemini-2.5-flash' },
    xai:         { name: 'xAI',         model: 'grok-4-1-fast-reasoning' },
    perplexity:  { name: 'Perplexity',  model: 'sonar-pro' },
    mistral:     { name: 'Mistral',     model: 'mistral-large-latest' },
    cohere:      { name: 'Cohere',      model: 'command-a-03-2025' },
    huggingface: { name: 'HuggingFace', model: 'Llama-3.3-70B' },
  };

  // ── State ──────────────────────────────────────────────────
  let allPredictions = [];
  let currentFilter = 'all';
  let currentSort = 'ticker';
  let searchQuery = '';
  let sseSource = null;
  let feedMessages = [];

  // ── DOM refs ───────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // ── API helpers ────────────────────────────────────────────
  async function apiFetch(path) {
    const res = await fetch(API_ROOT + path);
    if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
    return res.json();
  }

  // ── Initialization ─────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    loadAll();
    initSSE();
    bindEvents();
    // Refresh data every 30s
    setInterval(loadAll, 30000);
  });

  async function loadAll() {
    try {
      const [current, stats, health, history] = await Promise.all([
        apiFetch('/current'),
        apiFetch('/stats'),
        apiFetch('/health/providers'),
        apiFetch('/history?per_page=10'),
      ]);
      renderPredictions(current);
      renderStats(stats);
      renderProviders(health);
      renderAccuracy(stats);
      renderCycles(history);
      renderMarketDirection(current);
      updatePhase(current);
    } catch (e) {
      console.error('Load error:', e);
    }
  }

  // ── SSE Stream ─────────────────────────────────────────────
  function initSSE() {
    if (sseSource) sseSource.close();
    const url = API_ROOT + '/stream';
    sseSource = new EventSource(url);

    sseSource.onopen = () => {
      $('#conn-status .conn-dot').className = 'conn-dot connected';
    };

    sseSource.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'heartbeat' || msg.type === 'connected') return;
        if (msg.type === 'snapshot') {
          // Initial snapshot from SSE
          loadAll();
          return;
        }
        // Real event — update feed and refresh data
        handleSSEEvent(msg);
      } catch (err) {
        console.warn('SSE parse error:', err);
      }
    };

    sseSource.onerror = () => {
      $('#conn-status .conn-dot').className = 'conn-dot error';
      setTimeout(() => {
        if (sseSource.readyState === EventSource.CLOSED) initSSE();
      }, 5000);
    };
  }

  function handleSSEEvent(msg) {
    const data = msg.data || {};
    const type = msg.type || data.event_type || '';

    // Update live feed
    let feedText = '';
    if (type === 'prediction' && data.ticker) {
      const dir = (data.predicted_direction || '').toUpperCase();
      feedText = `${data.ticker} → ${dir} (${data.provider || 'unknown'})`;
    } else if (type === 'cycle_started') {
      feedText = `Cycle #${data.cycle_id || '?'} started`;
    } else if (type === 'cycle_completed') {
      feedText = `Cycle #${data.cycle_id || '?'} completed`;
      loadAll(); // Full refresh on cycle complete
    } else if (type === 'stock_processing') {
      feedText = `Analyzing ${data.ticker || '?'}...`;
    }

    if (feedText) {
      feedMessages.unshift(feedText);
      if (feedMessages.length > 50) feedMessages.pop();
      $('#feed-track').textContent = feedMessages[0];
    }

    // Incremental refresh for predictions
    if (type === 'prediction' || type === 'stock_complete') {
      loadAll();
    }
  }

  // ── Event Bindings ─────────────────────────────────────────
  function bindEvents() {
    // Tabs
    $$('#market-tabs .tab').forEach(tab => {
      tab.addEventListener('click', () => {
        $$('#market-tabs .tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentFilter = tab.dataset.filter;
        renderTable();
      });
    });

    // Search
    $('#search-input').addEventListener('input', (e) => {
      searchQuery = e.target.value.toLowerCase().trim();
      renderTable();
    });

    // Sort
    $('#sort-select').addEventListener('change', (e) => {
      currentSort = e.target.value;
      renderTable();
    });

    // Cycle controls
    $('#run-cycle-btn').addEventListener('click', async () => {
      try {
        await fetch(API_ROOT + '/cycle/start', { method: 'POST' });
        $('#run-cycle-btn').disabled = true;
        $('#abort-cycle-btn').disabled = false;
        loadAll();
      } catch (e) {
        console.error('Start cycle error:', e);
      }
    });

    $('#abort-cycle-btn').addEventListener('click', async () => {
      try {
        const current = await apiFetch('/current');
        if (current.cycle && current.cycle.id) {
          await fetch(API_ROOT + `/cycle/${current.cycle.id}/stop`, { method: 'POST' });
          loadAll();
        }
      } catch (e) {
        console.error('Abort cycle error:', e);
      }
    });

    // Panel toggle
    $('#panel-toggle').addEventListener('click', () => {
      $('#side-panel').classList.toggle('collapsed');
    });

    // Detail overlay
    $('#detail-backdrop').addEventListener('click', closeDetail);
    $('#detail-close').addEventListener('click', closeDetail);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeDetail();
    });
  }

  // ── Render: Predictions ────────────────────────────────────
  function renderPredictions(data) {
    if (!data || !data.predictions) return;
    allPredictions = data.predictions;

    // Update cycle controls
    const hasActive = data.cycle && data.cycle.status === 'active';
    $('#run-cycle-btn').disabled = hasActive;
    $('#abort-cycle-btn').disabled = !hasActive;

    renderTable();
  }

  function renderTable() {
    const tbody = $('#stock-tbody');
    let filtered = [...allPredictions];

    // Filter out MARKET-* tickers from the main table
    filtered = filtered.filter(p => {
      const t = (p.ticker || '').toUpperCase();
      return !t.startsWith('MARKET-');
    });

    // Filter by market type
    if (currentFilter === 'crypto') {
      filtered = filtered.filter(p => isCrypto(p.ticker));
    } else if (currentFilter === 'equity') {
      filtered = filtered.filter(p => !isCrypto(p.ticker));
    }

    // Search filter
    if (searchQuery) {
      filtered = filtered.filter(p =>
        (p.ticker || '').toLowerCase().includes(searchQuery) ||
        (p.name || '').toLowerCase().includes(searchQuery)
      );
    }

    // Sort
    filtered.sort(getSortFn(currentSort));

    if (filtered.length === 0) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="5">No predictions match your filters</td></tr>';
      return;
    }

    tbody.innerHTML = filtered.map(p => {
      const dir = (p.predicted_direction || 'pending').toLowerCase();
      const conf = p.confidence != null ? p.confidence : 0;
      const confPct = Math.round(conf * 100);
      const price = p.initial_price != null ? `$${formatPrice(p.initial_price)}` : '--';
      const provider = prettyProvider(p.provider || '');
      const ticker = p.ticker || '?';
      const name = truncate(p.name || '', 30);
      const isProcessing = !p.predicted_direction;

      return `<tr data-ticker="${ticker}" class="${isProcessing ? 'processing' : ''}" onclick="window._openDetail('${ticker}')">
        <td class="col-ticker">
          <div class="ticker-cell">
            <span class="ticker-symbol">${ticker}</span>
            <span class="ticker-name">${name}</span>
          </div>
        </td>
        <td class="col-price"><span class="price-val">${price}</span></td>
        <td class="col-direction"><span class="dir-badge ${dir}">${dirLabel(dir)}</span></td>
        <td class="col-confidence">
          <div class="conf-cell">
            <div class="conf-bar-bg"><div class="conf-bar-fill ${dir}" style="width:${confPct}%"></div></div>
            <span class="conf-val">${confPct}%</span>
          </div>
        </td>
        <td class="col-provider"><span class="provider-tag">${provider}</span></td>
      </tr>`;
    }).join('');
  }

  // ── Render: Market Direction ────────────────────────────────
  function renderMarketDirection(data) {
    if (!data || !data.predictions) return;

    const cryptoMkt = data.predictions.find(p => (p.ticker || '').toUpperCase() === 'MARKET-CRYPTO');
    const equityMkt = data.predictions.find(p => (p.ticker || '').toUpperCase() === 'MARKET-EQUITIES');

    if (cryptoMkt) {
      const dir = (cryptoMkt.predicted_direction || '').toLowerCase();
      const el = $('#crypto-direction');
      el.textContent = dir ? dir.toUpperCase() : '--';
      el.className = 'market-dir ' + dir;
      const conf = cryptoMkt.confidence != null ? Math.round(cryptoMkt.confidence * 100) : null;
      $('#crypto-confidence').textContent = conf != null ? `${conf}%` : '';
    }

    if (equityMkt) {
      const dir = (equityMkt.predicted_direction || '').toLowerCase();
      const el = $('#equities-direction');
      el.textContent = dir ? dir.toUpperCase() : '--';
      el.className = 'market-dir ' + dir;
      const conf = equityMkt.confidence != null ? Math.round(equityMkt.confidence * 100) : null;
      $('#equities-confidence').textContent = conf != null ? `${conf}%` : '';
    }
  }

  // ── Render: Stats ──────────────────────────────────────────
  function renderStats(stats) {
    if (!stats) return;
    $('#stat-accuracy').textContent = stats.overall_accuracy != null
      ? `${(stats.overall_accuracy * 100).toFixed(1)}%` : '--';
    $('#stat-predictions').textContent = formatNumber(stats.total_predictions || 0);
    $('#stat-cycles').textContent = formatNumber(stats.total_cycles || 0);
    $('#stat-stocks').textContent = formatNumber(stats.total_stocks || 0);
  }

  function updatePhase(data) {
    if (!data || !data.cycle) {
      $('#stat-phase').textContent = 'IDLE';
      return;
    }
    const phase = data.cycle.phase || data.cycle.status || 'active';
    $('#stat-phase').textContent = phase.toUpperCase();
  }

  // ── Render: Providers ──────────────────────────────────────
  function renderProviders(health) {
    const container = $('#provider-list');
    if (!health || !health.providers) {
      container.innerHTML = '<div style="color:var(--text-muted);font-size:0.7rem">No provider data</div>';
      return;
    }

    const providers = health.providers;
    container.innerHTML = Object.entries(providers).map(([key, info]) => {
      const meta = PROVIDER_MODELS[key] || { name: key, model: '?' };
      const status = info.status === 'configured' ? 'healthy' : 'error';
      return `<div class="provider-item">
        <div class="provider-info">
          <span class="provider-name">${meta.name}</span>
          <span class="provider-model">${meta.model}</span>
        </div>
        <span class="provider-status ${status}"></span>
      </div>`;
    }).join('');
  }

  // ── Render: Accuracy ───────────────────────────────────────
  function renderAccuracy(stats) {
    const container = $('#accuracy-list');
    if (!stats || !stats.by_provider || stats.by_provider.length === 0) {
      container.innerHTML = '<div style="color:var(--text-muted);font-size:0.7rem">No accuracy data yet</div>';
      return;
    }

    const sorted = [...stats.by_provider]
      .filter(p => p.evaluated_predictions > 0)
      .sort((a, b) => (b.accuracy || 0) - (a.accuracy || 0));

    if (sorted.length === 0) {
      container.innerHTML = '<div style="color:var(--text-muted);font-size:0.7rem">No evaluated predictions yet</div>';
      return;
    }

    container.innerHTML = sorted.map(p => {
      const pct = ((p.accuracy || 0) * 100).toFixed(1);
      const cls = pct >= 60 ? 'good' : pct >= 45 ? 'mid' : 'bad';
      const name = prettyProvider(p.provider || '');
      return `<div class="accuracy-item">
        <span class="accuracy-name">${name}</span>
        <span class="accuracy-pct ${cls}">${pct}% <small style="color:var(--text-muted)">(${p.evaluated_predictions})</small></span>
      </div>`;
    }).join('');
  }

  // ── Render: Cycles ─────────────────────────────────────────
  function renderCycles(history) {
    const container = $('#cycle-list');
    if (!history || !history.cycles || history.cycles.length === 0) {
      container.innerHTML = '<div style="color:var(--text-muted);font-size:0.7rem">No cycles yet</div>';
      return;
    }

    container.innerHTML = history.cycles.slice(0, 10).map(c => {
      const status = c.status || 'unknown';
      const time = c.started_at ? new Date(c.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
      const preds = c.predictions_made || 0;
      return `<div class="cycle-item">
        <span class="cycle-id">#${c.id}</span>
        <span class="cycle-meta">${time} · ${preds} preds</span>
        <span class="cycle-status ${status}">${status}</span>
      </div>`;
    }).join('');
  }

  // ── Detail Panel ───────────────────────────────────────────
  window._openDetail = async function (ticker) {
    const overlay = $('#detail-overlay');
    overlay.hidden = false;
    $('#detail-ticker').textContent = ticker;
    $('#detail-name').textContent = '';
    $('#detail-body').innerHTML = '<div class="detail-loading">Loading...</div>';

    try {
      const data = await apiFetch(`/stock/${encodeURIComponent(ticker)}`);
      renderDetail(data);
    } catch (e) {
      $('#detail-body').innerHTML = `<div class="detail-loading">Error loading ${ticker}</div>`;
    }
  };

  function closeDetail() {
    $('#detail-overlay').hidden = true;
  }

  function renderDetail(data) {
    if (!data) return;
    const stock = data.stock || {};
    const predictions = data.predictions || [];
    const ticker = data.symbol || '?';

    $('#detail-ticker').textContent = ticker;
    $('#detail-name').textContent = stock.name || '';

    // Get latest consensus
    const consensus = predictions.find(p => (p.provider || '').includes('consensus'));
    const dir = consensus ? (consensus.predicted_direction || '').toLowerCase() : '--';
    const conf = consensus ? Math.round((consensus.confidence || 0) * 100) : '--';
    const price = consensus && consensus.initial_price ? `$${formatPrice(consensus.initial_price)}` : '--';

    // Individual provider predictions (non-consensus)
    const providerPreds = predictions
      .filter(p => !(p.provider || '').includes('consensus') && !(p.provider || '').includes('council'))
      .slice(0, 20);

    const reasoning = consensus && consensus.reasoning ? consensus.reasoning : '';

    let html = `
      <div class="detail-section">
        <div class="detail-section-title">Consensus</div>
        <div class="detail-grid">
          <div class="detail-metric">
            <div class="detail-metric-val dir-badge ${dir}" style="display:inline-flex">${dirLabel(dir)}</div>
            <div class="detail-metric-key">Direction</div>
          </div>
          <div class="detail-metric">
            <div class="detail-metric-val">${conf}%</div>
            <div class="detail-metric-key">Confidence</div>
          </div>
          <div class="detail-metric">
            <div class="detail-metric-val">${price}</div>
            <div class="detail-metric-key">Entry Price</div>
          </div>
          <div class="detail-metric">
            <div class="detail-metric-val">${data.times_predicted || 0}</div>
            <div class="detail-metric-key">Times Predicted</div>
          </div>
        </div>
      </div>`;

    if (reasoning) {
      html += `
      <div class="detail-section">
        <div class="detail-section-title">Reasoning</div>
        <div class="detail-reasoning">${escapeHtml(reasoning)}</div>
      </div>`;
    }

    if (providerPreds.length > 0) {
      html += `
      <div class="detail-section">
        <div class="detail-section-title">Provider Votes</div>
        ${providerPreds.map(p => {
          const pDir = (p.predicted_direction || 'neutral').toLowerCase();
          const pConf = p.confidence != null ? Math.round(p.confidence * 100) + '%' : '--';
          return `<div class="detail-prediction-row">
            <span class="detail-pred-provider">${prettyProvider(p.provider || '')}</span>
            <span class="detail-pred-dir ${pDir}">${dirLabel(pDir)} ${pConf}</span>
          </div>`;
        }).join('')}
      </div>`;
    }

    $('#detail-body').innerHTML = html;
  }

  // ── Helpers ────────────────────────────────────────────────
  function isCrypto(ticker) {
    if (!ticker) return false;
    const t = ticker.toUpperCase();
    return t.endsWith('-USD') || t.startsWith('MARKET-CRYPTO');
  }

  function dirLabel(dir) {
    switch (dir) {
      case 'up': return '▲ UP';
      case 'down': return '▼ DOWN';
      case 'neutral': return '● HOLD';
      default: return '◌ PENDING';
    }
  }

  function prettyProvider(raw) {
    if (!raw) return '';
    // Strip common prefixes/suffixes
    const cleaned = raw.replace(/-synthesis|-council|-swarm|-consensus|-weighted/g, '').trim();
    const meta = PROVIDER_MODELS[cleaned];
    if (meta) return meta.name;
    // Title case fallback
    return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  }

  function formatPrice(val) {
    if (val == null) return '--';
    const num = parseFloat(val);
    if (isNaN(num)) return '--';
    if (num >= 1000) return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (num >= 1) return num.toFixed(2);
    if (num >= 0.01) return num.toFixed(4);
    return num.toFixed(6);
  }

  function formatNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(n);
  }

  function truncate(str, max) {
    return str.length > max ? str.substring(0, max) + '...' : str;
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function getSortFn(sortKey) {
    switch (sortKey) {
      case 'confidence-desc':
        return (a, b) => (b.confidence || 0) - (a.confidence || 0);
      case 'confidence-asc':
        return (a, b) => (a.confidence || 0) - (b.confidence || 0);
      case 'price-desc':
        return (a, b) => (b.initial_price || 0) - (a.initial_price || 0);
      case 'price-asc':
        return (a, b) => (a.initial_price || 0) - (b.initial_price || 0);
      case 'direction':
        return (a, b) => {
          const order = { up: 0, down: 1, neutral: 2 };
          const aDir = order[(a.predicted_direction || 'neutral').toLowerCase()] ?? 3;
          const bDir = order[(b.predicted_direction || 'neutral').toLowerCase()] ?? 3;
          return aDir - bDir;
        };
      default: // ticker
        return (a, b) => (a.ticker || '').localeCompare(b.ticker || '');
    }
  }

})();
