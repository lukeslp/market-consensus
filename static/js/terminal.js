/* ============================================================
   CONSENSUS TERMINAL — Unified Application Script
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
    anthropic:   { name: 'Anthropic',   model: 'claude-haiku-4-5' },
    openai:      { name: 'OpenAI',      model: 'gpt-5-mini' },
    gemini:      { name: 'Gemini',      model: 'gemini-2.5-flash' },
    xai:         { name: 'xAI',         model: 'grok-4-1-fast' },
    perplexity:  { name: 'Perplexity',  model: 'sonar' },
    mistral:     { name: 'Mistral',     model: 'mistral-small' },
    cohere:      { name: 'Cohere',      model: 'command-r' },
    huggingface: { name: 'HuggingFace', model: 'Llama-3.3-70B' },
    ollama:      { name: 'Ollama',      model: 'glm-5' },
  };

  // ── State ──────────────────────────────────────────────────
  let allWatchlist = [];       // Full 100-item watchlist (from /api/watchlist)
  let allPredictions = [];     // Predictions from /api/current (fallback)
  let currentFilter = 'all';
  let currentSort = 'ticker';
  let searchQuery = '';
  let sseSource = null;
  let feedMessages = [];
  let useWatchlistMode = false;
  let refreshInterval = null;
  let lastUpdateTime = null;
  let freshnessInterval = null;
  let keyboardFocusIndex = -1;

  // ── DOM refs ───────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // ── API helpers ────────────────────────────────────────────
  async function apiFetch(path) {
    const res = await fetch(API_ROOT + path);
    if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
    return res.json();
  }

  // ── Simple markdown renderer ───────────────────────────────
  function renderMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);

    // Headers
    html = html.replace(/^### (.+)$/gm, '<h4 class="md-h4">$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3 class="md-h3">$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2 class="md-h2">$1</h2>');

    // Bold and italic
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code class="md-code">$1</code>');

    // Bullet lists
    html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul class="md-list">$&</ul>');

    // Numbered lists
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

    // Pipe-delimited sections (common in reasoning output)
    html = html.replace(/ \| /g, '<br><span class="md-sep">│</span> ');
    html = html.replace(/ \|\| /g, '<br><span class="md-sep">║</span> ');

    // Line breaks (double newline = paragraph, single = br)
    html = html.replace(/\n\n/g, '</p><p class="md-p">');
    html = html.replace(/\n/g, '<br>');

    return '<p class="md-p">' + html + '</p>';
  }

  // ── Format reasoning into structured sections ──────────────
  function formatReasoning(reasoning) {
    if (!reasoning) return '';

    // Parse the council reasoning format
    // Pattern: "Council weighted vote totals: up=X, down=Y, neutral=Z. Winner=dir. Individual reports: provider [stage]: ..."
    const councilMatch = reasoning.match(/Council weighted vote totals: up=([\d.]+), down=([\d.]+), neutral=([\d.]+)\. Winner=(\w+)\./);
    if (councilMatch) {
      const [, up, down, neutral, winner] = councilMatch;
      let html = `<div class="reasoning-section">
        <div class="reasoning-header">Council Vote Totals</div>
        <div class="vote-bars">
          <div class="vote-bar-row">
            <span class="vote-label up">▲ UP</span>
            <div class="vote-bar-bg"><div class="vote-bar-fill up" style="width:${Math.round(parseFloat(up) / (parseFloat(up) + parseFloat(down) + parseFloat(neutral)) * 100)}%"></div></div>
            <span class="vote-score">${parseFloat(up).toFixed(2)}</span>
          </div>
          <div class="vote-bar-row">
            <span class="vote-label down">▼ DOWN</span>
            <div class="vote-bar-bg"><div class="vote-bar-fill down" style="width:${Math.round(parseFloat(down) / (parseFloat(up) + parseFloat(down) + parseFloat(neutral)) * 100)}%"></div></div>
            <span class="vote-score">${parseFloat(down).toFixed(2)}</span>
          </div>
          <div class="vote-bar-row">
            <span class="vote-label neutral">● HOLD</span>
            <div class="vote-bar-bg"><div class="vote-bar-fill neutral" style="width:${Math.round(parseFloat(neutral) / (parseFloat(up) + parseFloat(down) + parseFloat(neutral)) * 100)}%"></div></div>
            <span class="vote-score">${parseFloat(neutral).toFixed(2)}</span>
          </div>
        </div>
        <div class="vote-winner">Winner: <span class="dir-badge ${winner}">${dirLabel(winner)}</span></div>
      </div>`;

      // Parse individual reports
      const reportsMatch = reasoning.match(/Individual reports: (.+)/);
      if (reportsMatch) {
        const reports = reportsMatch[1].split(' | ').filter(r => r.trim());
        if (reports.length > 0) {
          html += `<div class="reasoning-section">
            <div class="reasoning-header">Individual Reports</div>
            <div class="report-list">`;
          for (const report of reports) {
            const provMatch = report.match(/^(\w+)\s*\[(\w+)\]:\s*dir=(\w+)\s+conf=([\d.]+)\s+weight=([\d.]+)\s+score=([\d.]+);\s*reason=(.*)/);
            if (provMatch) {
              const [, prov, stage, dir, conf, weight, score, reason] = provMatch;
              html += `<div class="report-item">
                <div class="report-header">
                  <span class="report-provider">${prettyProvider(prov)}</span>
                  <span class="report-stage">${stage}</span>
                  <span class="dir-badge ${dir}" style="font-size:0.65rem">${dirLabel(dir)}</span>
                  <span class="report-conf">${Math.round(parseFloat(conf) * 100)}%</span>
                  <span class="report-weight" title="Weight">w=${parseFloat(weight).toFixed(2)}</span>
                </div>
                <div class="report-reason">${renderMarkdown(reason.trim())}</div>
              </div>`;
            } else {
              html += `<div class="report-item"><div class="report-reason">${renderMarkdown(report.trim())}</div></div>`;
            }
          }
          html += `</div></div>`;
        }
      }
      return html;
    }

    // Fallback: render as markdown
    return `<div class="reasoning-section">
      <div class="reasoning-header">Analysis</div>
      <div class="reasoning-body">${renderMarkdown(reasoning)}</div>
    </div>`;
  }

  // ── Initialization ─────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    loadAll();
    initSSE();
    bindEvents();
    bindSettings();
    bindHelp();
    // Refresh data every 30s
    refreshInterval = setInterval(loadAll, 30000);
    // Update freshness display every 15s
    freshnessInterval = setInterval(updateFreshness, 15000);
  });

  async function loadAll() {
    try {
      const results = await Promise.allSettled([
        apiFetch('/watchlist'),
        apiFetch('/current'),
        apiFetch('/stats'),
        apiFetch('/health/providers'),
        apiFetch('/history?per_page=10'),
      ]);
      const watchlistData = results[0].status === 'fulfilled' ? results[0].value : null;
      const current       = results[1].status === 'fulfilled' ? results[1].value : null;
      const stats         = results[2].status === 'fulfilled' ? results[2].value : null;
      const health        = results[3].status === 'fulfilled' ? results[3].value : null;
      const history       = results[4].status === 'fulfilled' ? results[4].value : null;

      if (watchlistData && watchlistData.watchlist) {
        useWatchlistMode = true;
        allWatchlist = watchlistData.watchlist;
        renderTable();
        if (watchlistData.cycle) {
          updatePhaseFromCycle(watchlistData.cycle);
          updateCycleProgress(watchlistData.cycle);
        }
      } else if (current) {
        useWatchlistMode = false;
        renderPredictions(current);
      }

      if (current) {
        renderMarketDirection(current);
        updateFeedFromData(current);
        if (current.cycle) updateCycleProgress(current.cycle);
      }
      if (stats)   { renderStats(stats); renderAccuracy(stats); }
      if (health)  { renderProviders(health); }
      if (history) { renderCycles(history); }

      // Update freshness timestamp
      lastUpdateTime = Date.now();
      updateFreshness();

      // Update cycle controls from current data
      if (current && current.cycle) {
        const hasActive = current.cycle.status === 'active';
        $('#run-cycle-btn').disabled = hasActive;
        $('#abort-cycle-btn').disabled = !hasActive;
      }

      // Show error if nothing loaded
      if (!watchlistData && !current && !stats) {
        $('#stock-tbody').innerHTML = '<tr class="empty-row"><td colspan="5">API connection error — retrying...</td></tr>';
      }
    } catch (e) {
      console.error('Load error:', e);
      $('#stock-tbody').innerHTML = '<tr class="empty-row"><td colspan="5">Error: ' + e.message + '</td></tr>';
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
          loadAll();
          return;
        }
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

    let feedText = '';
    if (type === 'prediction' && data.ticker) {
      const dir = (data.predicted_direction || '').toUpperCase();
      feedText = `${data.ticker} → ${dir} (${data.provider || 'unknown'})`;
    } else if (type === 'cycle_started') {
      feedText = `Cycle #${data.cycle_id || '?'} started`;
    } else if (type === 'cycle_completed') {
      feedText = `Cycle #${data.cycle_id || '?'} completed`;
      loadAll();
    } else if (type === 'stock_processing') {
      feedText = `Analyzing ${data.ticker || '?'}...`;
    }

    if (feedText) {
      feedMessages.unshift(feedText);
      if (feedMessages.length > 50) feedMessages.pop();
      $('#feed-track').textContent = feedMessages[0];
    }

    if (type === 'prediction' || type === 'stock_complete') {
      loadAll();
    }
  }

  // ── Event Bindings ─────────────────────────────────────────
  function bindEvents() {
    $$('#market-tabs .tab').forEach(tab => {
      tab.addEventListener('click', () => {
        $$('#market-tabs .tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentFilter = tab.dataset.filter;
        renderTable();
      });
    });

    $('#search-input').addEventListener('input', (e) => {
      searchQuery = e.target.value.toLowerCase().trim();
      renderTable();
    });

    $('#sort-select').addEventListener('change', (e) => {
      currentSort = e.target.value;
      renderTable();
    });

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

    $('#panel-toggle').addEventListener('click', () => {
      $('#side-panel').classList.toggle('collapsed');
    });

    $('#detail-backdrop').addEventListener('click', closeDetail);
    $('#detail-close').addEventListener('click', closeDetail);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { closeDetail(); return; }

      // Skip keyboard nav if user is typing in an input
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
      // Skip if analytics view is active
      const analyticsView = document.getElementById('view-analytics');
      if (analyticsView && !analyticsView.hidden) return;

      const rows = $$('#stock-tbody tr:not(.empty-row)');
      if (rows.length === 0) return;

      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        keyboardFocusIndex = Math.min(keyboardFocusIndex + 1, rows.length - 1);
        highlightRow(rows);
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        keyboardFocusIndex = Math.max(keyboardFocusIndex - 1, 0);
        highlightRow(rows);
      } else if (e.key === 'Enter' && keyboardFocusIndex >= 0 && keyboardFocusIndex < rows.length) {
        e.preventDefault();
        const ticker = rows[keyboardFocusIndex].dataset.ticker;
        if (ticker) window._openDetail(ticker);
      }
    });
  }

  // ── Render: Predictions (legacy fallback) ──────────────────
  function renderPredictions(data) {
    if (!data || !data.predictions) return;
    allPredictions = data.predictions;
    if (!useWatchlistMode) {
      renderTable();
    }
    updatePhaseFromCycle(data.cycle);
  }

  function updatePhaseFromCycle(cycle) {
    if (!cycle) {
      $('#stat-phase').textContent = 'IDLE';
      return;
    }
    const phase = cycle.phase || cycle.status || 'active';
    $('#stat-phase').textContent = phase.toUpperCase();
  }

  // ── Render: Table ──────────────────────────────────────────
  function renderTable() {
    const tbody = $('#stock-tbody');
    let items;

    if (useWatchlistMode && allWatchlist.length > 0) {
      items = [...allWatchlist];
    } else {
      // Fallback to predictions-only mode
      items = allPredictions.map(p => ({
        ticker: p.ticker,
        name: p.name || '',
        asset_type: isCrypto(p.ticker) ? 'crypto' : 'equity',
        predicted_direction: p.predicted_direction,
        confidence: p.confidence,
        initial_price: p.initial_price,
        provider: p.provider || '',
        has_prediction: true,
      }));
    }

    // Filter out MARKET-* tickers from the main table
    items = items.filter(p => {
      const t = (p.ticker || '').toUpperCase();
      return !t.startsWith('MARKET-');
    });

    // Filter by market type
    if (currentFilter === 'crypto') {
      items = items.filter(p => p.asset_type === 'crypto' || isCrypto(p.ticker));
    } else if (currentFilter === 'equity') {
      items = items.filter(p => p.asset_type !== 'crypto' && !isCrypto(p.ticker));
    }

    // Search filter
    if (searchQuery) {
      items = items.filter(p =>
        (p.ticker || '').toLowerCase().includes(searchQuery) ||
        (p.name || '').toLowerCase().includes(searchQuery)
      );
    }

    // Sort
    items.sort(getSortFn(currentSort));

    if (items.length === 0) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="5">No stocks match your filters</td></tr>';
      return;
    }

    tbody.innerHTML = items.map(p => {
      const hasPred = p.has_prediction || p.predicted_direction;
      const dir = hasPred ? (p.predicted_direction || 'pending').toLowerCase() : 'pending';
      const conf = hasPred && p.confidence != null ? p.confidence : 0;
      const confPct = hasPred ? Math.round(conf * 100) : 0;
      const price = p.initial_price != null ? `$${formatPrice(p.initial_price)}` : (p.last_price != null ? `$${formatPrice(p.last_price)}` : '--');
      const provider = hasPred ? prettyProvider(p.provider || '') : '';
      const ticker = p.ticker || '?';
      const name = truncate(p.name || '', 30);
      const isPending = !hasPred;

      // Vote split mini bar
      const vt = p.vote_totals || {};
      const vtTotal = (vt.up || 0) + (vt.down || 0) + (vt.neutral || 0);
      const voteSplitHtml = vtTotal > 0
        ? `<div class="vote-split" data-tip="${(vt.up||0).toFixed(1)} up · ${(vt.down||0).toFixed(1)} down · ${(vt.neutral||0).toFixed(1)} hold">
             <div class="vote-split-seg up" style="width:${Math.round((vt.up||0)/vtTotal*100)}%"></div>
             <div class="vote-split-seg down" style="width:${Math.round((vt.down||0)/vtTotal*100)}%"></div>
             <div class="vote-split-seg neutral" style="width:${Math.round((vt.neutral||0)/vtTotal*100)}%"></div>
           </div>`
        : `<div class="conf-bar-bg"><div class="conf-bar-fill ${dir}" style="width:${confPct}%"></div></div>`;

      return `<tr data-ticker="${ticker}" class="${isPending ? 'pending-row' : ''}" onclick="window._openDetail('${ticker}')">
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
            ${voteSplitHtml}
            <span class="conf-val">${hasPred ? confPct + '%' : '--'}</span>
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
    const agentVotes = data.agent_votes || [];
    const debateRounds = data.debate_rounds || [];
    const ticker = data.symbol || '?';

    $('#detail-ticker').textContent = ticker;
    $('#detail-name').textContent = stock.name || '';

    // Get latest consensus
    const consensus = predictions.find(p => (p.provider || '').includes('consensus'));
    const councilWeighted = predictions.find(p => p.provider === 'council-weighted');
    const bestPred = consensus || councilWeighted;
    const dir = bestPred ? (bestPred.predicted_direction || '').toLowerCase() : '--';
    const conf = bestPred ? Math.round((bestPred.confidence || 0) * 100) : '--';
    const price = bestPred && bestPred.initial_price ? `$${formatPrice(bestPred.initial_price)}` : '--';

    // Individual provider predictions (non-consensus, non-council, non-synthesis)
    const providerPreds = predictions
      .filter(p => {
        const prov = p.provider || '';
        return !prov.includes('consensus') && !prov.includes('council') && !prov.includes('synthesis');
      })
      .slice(0, 20);

    // Synthesis votes
    const synthesisPreds = predictions
      .filter(p => (p.provider || '').includes('synthesis') && !(p.provider || '').includes('consensus'))
      .slice(0, 20);

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

    // Debate rounds (structured vote data)
    if (debateRounds.length > 0) {
      for (const round of debateRounds) {
        const vt = round.vote_totals || {};
        const totalVote = (vt.up || 0) + (vt.down || 0) + (vt.neutral || 0) || 1;
        html += `
        <div class="detail-section">
          <div class="detail-section-title">${round.round_type === 'synthesis' ? 'Synthesis Round' : 'Council Debate'}</div>
          <div class="vote-bars">
            <div class="vote-bar-row">
              <span class="vote-label up">▲ UP</span>
              <div class="vote-bar-bg"><div class="vote-bar-fill up" style="width:${Math.round((vt.up || 0) / totalVote * 100)}%"></div></div>
              <span class="vote-score">${(vt.up || 0).toFixed(2)}</span>
            </div>
            <div class="vote-bar-row">
              <span class="vote-label down">▼ DOWN</span>
              <div class="vote-bar-bg"><div class="vote-bar-fill down" style="width:${Math.round((vt.down || 0) / totalVote * 100)}%"></div></div>
              <span class="vote-score">${(vt.down || 0).toFixed(2)}</span>
            </div>
            <div class="vote-bar-row">
              <span class="vote-label neutral">● HOLD</span>
              <div class="vote-bar-bg"><div class="vote-bar-fill neutral" style="width:${Math.round((vt.neutral || 0) / totalVote * 100)}%"></div></div>
              <span class="vote-score">${(vt.neutral || 0).toFixed(2)}</span>
            </div>
          </div>
          <div class="vote-winner">Winner: <span class="dir-badge ${round.winning_direction}">${dirLabel(round.winning_direction || '')}</span>
            <span class="vote-conf">${Math.round((round.winning_confidence || 0) * 100)}%</span>
            <span class="vote-participants">${round.participant_count || 0} participants</span>
          </div>
        </div>`;
      }
    }

    // Agent votes (structured individual votes)
    if (agentVotes.length > 0) {
      // Group by phase
      const byPhase = {};
      for (const vote of agentVotes) {
        const phase = vote.phase || 'analysis';
        if (!byPhase[phase]) byPhase[phase] = [];
        byPhase[phase].push(vote);
      }

      for (const [phase, votes] of Object.entries(byPhase)) {
        const phaseLabel = phase === 'analysis' ? 'Analysis Agents' : phase === 'synthesis' ? 'Synthesis Votes' : phase.charAt(0).toUpperCase() + phase.slice(1);
        html += `
        <div class="detail-section">
          <div class="detail-section-title">${phaseLabel}</div>
          <div class="agent-vote-list">`;
        for (const vote of votes) {
          const vDir = (vote.vote_direction || 'neutral').toLowerCase();
          const vConf = vote.confidence != null ? Math.round(vote.confidence * 100) + '%' : '--';
          const role = vote.agent_role || '';
          html += `<div class="agent-vote-item">
            <div class="agent-vote-header">
              <span class="agent-provider">${prettyProvider(vote.provider || '')}</span>
              ${role ? `<span class="agent-role">${role}</span>` : ''}
              <span class="dir-badge ${vDir}" style="font-size:0.65rem">${dirLabel(vDir)}</span>
              <span class="agent-conf">${vConf}</span>
            </div>
            ${vote.reasoning ? `<div class="agent-reasoning">${renderMarkdown(vote.reasoning)}</div>` : ''}
          </div>`;
        }
        html += `</div></div>`;
      }
    }

    // Provider predictions (fallback if no agent_votes)
    if (agentVotes.length === 0 && providerPreds.length > 0) {
      html += `
      <div class="detail-section">
        <div class="detail-section-title">Provider Votes</div>
        ${providerPreds.map(p => {
          const pDir = (p.predicted_direction || 'neutral').toLowerCase();
          const pConf = p.confidence != null ? Math.round(p.confidence * 100) + '%' : '--';
          const reasoning = p.reasoning || '';
          return `<div class="detail-prediction-row">
            <div class="detail-pred-header">
              <span class="detail-pred-provider">${prettyProvider(p.provider || '')}</span>
              <span class="detail-pred-dir ${pDir}">${dirLabel(pDir)} ${pConf}</span>
            </div>
            ${reasoning ? `<div class="detail-pred-reasoning">${renderMarkdown(reasoning)}</div>` : ''}
          </div>`;
        }).join('')}
      </div>`;
    }

    // Consensus reasoning (formatted)
    const reasoning = bestPred && bestPred.reasoning ? bestPred.reasoning : '';
    if (reasoning && debateRounds.length === 0) {
      html += formatReasoning(reasoning);
    }

    $('#detail-body').innerHTML = html;
  }

  // ── Feed from data (on page load) ─────────────────────────
  function updateFeedFromData(data) {
    if (!data || !data.predictions || data.predictions.length === 0) return;
    if (feedMessages.length > 0) return;

    const cycle = data.cycle;
    const preds = data.predictions.filter(p => !(p.ticker || '').startsWith('MARKET-'));
    const hasActive = cycle && cycle.status === 'active';

    if (hasActive && preds.length > 0) {
      const latest = preds[preds.length - 1];
      const dir = (latest.predicted_direction || '').toUpperCase();
      const text = `${latest.ticker} → ${dir} (${prettyProvider(latest.provider || '')}) · ${preds.length} predictions this cycle`;
      $('#feed-track').textContent = text;
    } else if (preds.length > 0) {
      $('#feed-track').textContent = `${preds.length} predictions · Cycle #${cycle ? cycle.id : '?'} ${cycle ? cycle.status : ''}`;
    }
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
    const cleaned = raw.replace(/-synthesis|-council|-swarm|-consensus|-weighted/g, '').trim();
    const meta = PROVIDER_MODELS[cleaned];
    if (meta) return meta.name;
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
        return (a, b) => ((b.initial_price || b.last_price) || 0) - ((a.initial_price || a.last_price) || 0);
      case 'price-asc':
        return (a, b) => ((a.initial_price || a.last_price) || 0) - ((b.initial_price || b.last_price) || 0);
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

  // ── Settings ────────────────────────────────────────────────
  function loadSettings() {
    try {
      const saved = JSON.parse(localStorage.getItem('consensus-settings') || '{}');
      // Font size
      const size = saved.fontSize || 'md';
      applyFontSize(size);
      // Compact
      if (saved.compact) {
        document.body.classList.add('compact');
        const el = $('#toggle-compact');
        if (el) { el.classList.add('on'); el.setAttribute('aria-checked', 'true'); }
      }
      // Auto-refresh
      if (saved.autoRefresh === false) {
        const el = $('#toggle-refresh');
        if (el) { el.classList.remove('on'); el.setAttribute('aria-checked', 'false'); }
      }
      // Help banner — show on first visit
      if (!saved.helpDismissed) {
        const banner = $('#help-banner');
        if (banner) banner.classList.add('visible');
      }
    } catch (e) { /* ignore */ }
  }

  function saveSettings() {
    const sizeBtn = document.querySelector('.size-btn.active');
    const settings = {
      fontSize: sizeBtn ? sizeBtn.dataset.size : 'md',
      compact: document.body.classList.contains('compact'),
      autoRefresh: $('#toggle-refresh') ? $('#toggle-refresh').classList.contains('on') : true,
      helpDismissed: !$('#help-banner').classList.contains('visible'),
    };
    localStorage.setItem('consensus-settings', JSON.stringify(settings));
  }

  function applyFontSize(size) {
    document.documentElement.classList.remove('font-sm', 'font-lg');
    if (size === 'sm') document.documentElement.classList.add('font-sm');
    else if (size === 'lg') document.documentElement.classList.add('font-lg');
    // Update active button
    $$('.size-btn').forEach(b => b.classList.toggle('active', b.dataset.size === size));
  }

  function bindSettings() {
    const btn = $('#settings-btn');
    const dropdown = $('#settings-dropdown');
    if (!btn || !dropdown) return;

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      dropdown.classList.toggle('open');
      btn.classList.toggle('active', dropdown.classList.contains('open'));
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (!dropdown.contains(e.target) && e.target !== btn) {
        dropdown.classList.remove('open');
        btn.classList.remove('active');
      }
    });

    // Font size buttons
    $$('.size-btn').forEach(b => {
      b.addEventListener('click', () => {
        applyFontSize(b.dataset.size);
        saveSettings();
      });
    });

    // Compact toggle
    const compact = $('#toggle-compact');
    if (compact) {
      compact.addEventListener('click', () => {
        compact.classList.toggle('on');
        const isOn = compact.classList.contains('on');
        compact.setAttribute('aria-checked', String(isOn));
        document.body.classList.toggle('compact', isOn);
        saveSettings();
      });
    }

    // Auto-refresh toggle
    const refresh = $('#toggle-refresh');
    if (refresh) {
      refresh.addEventListener('click', () => {
        refresh.classList.toggle('on');
        const isOn = refresh.classList.contains('on');
        refresh.setAttribute('aria-checked', String(isOn));
        if (isOn) {
          if (!refreshInterval) refreshInterval = setInterval(loadAll, 30000);
        } else {
          clearInterval(refreshInterval);
          refreshInterval = null;
        }
        saveSettings();
      });
    }
  }

  function bindHelp() {
    const btn = $('#help-btn');
    const banner = $('#help-banner');
    const dismiss = $('#help-dismiss');
    if (!btn || !banner) return;

    btn.addEventListener('click', () => {
      banner.classList.toggle('visible');
      saveSettings();
    });

    if (dismiss) {
      dismiss.addEventListener('click', () => {
        banner.classList.remove('visible');
        saveSettings();
      });
    }
  }

})();
