const API_ROOT = (() => {
  const p = window.location.pathname;
  return p.endsWith('/') ? p : p.slice(0, p.lastIndexOf('/') + 1);
})();

const PROVIDER_LINKS = {
  cohere:      'https://dashboard.cohere.com/api-keys',
  gemini:      'https://aistudio.google.com/app/apikey',
  openai:      'https://platform.openai.com/account/limits',
  xai:         'https://console.x.ai',
  anthropic:   'https://console.anthropic.com/settings/keys',
  mistral:     'https://console.mistral.ai/api-keys',
  perplexity:  'https://www.perplexity.ai/settings/api',
  huggingface: 'https://huggingface.co/settings/tokens',
};

function classifyProviderError(raw) {
  const s = String(raw || '').toLowerCase();
  if (s.includes('trial') || s.includes('1000 api calls')) return { label: 'Trial limit', linkText: 'Upgrade ↗' };
  if (s.includes('429') || s.includes('rate limit') || s.includes('resource exhausted') || s.includes('quota')) return { label: 'Rate limited', linkText: 'Quotas ↗' };
  if (s.includes('api key') || s.includes('unauthorized') || s.includes('invalid key') || s.includes('401')) return { label: 'Auth error', linkText: 'Keys ↗' };
  if (s.includes('timeout') || s.includes('connection')) return { label: 'Timeout', linkText: 'Status ↗' };
  return { label: 'Error', linkText: 'Dashboard ↗' };
}

class ForesightDashboard {
  constructor() {
    this.api = new window.ForesightAPI(API_ROOT.replace(/\/$/, ''));
    this.grid = null;
    this.detail = null;
    this.sidebar = null;
    this.eventSource = null;
    this.currentCycle = null;
    this.selectedSymbol = null;
    this.tickerItems = [];

    this.init();
  }

  init() {
    if (typeof d3 === 'undefined') {
      this.toast('D3 failed to load');
      return;
    }

    this.installPhaseController();
    this.mountVisuals();
    this.bindUI();
    this.bootstrap();
  }

  installPhaseController() {
    const label = document.getElementById('phase-label');
    const steps = document.querySelectorAll('.phase-step');
    const order = ['discovery', 'analysis', 'debate', 'consensus'];

    window.setPhase = (phase) => {
      if (label) label.textContent = phase.toUpperCase();
      const idx = order.indexOf(phase);
      steps.forEach((el) => {
        const s = el.dataset.phase;
        const sIdx = order.indexOf(s);
        el.classList.toggle('active', s === phase);
        el.classList.toggle('done', sIdx >= 0 && idx >= 0 && sIdx < idx);
      });
    };

    window.resetPhases = () => {
      if (label) label.textContent = 'IDLE';
      steps.forEach((el) => el.classList.remove('active', 'done'));
    };
  }

  mountVisuals() {
    this.grid = new window.StockGrid('#grid-stage', {
      columns: 10,
      onTileClick: (stock) => this.selectStock(stock.symbol)
    });

    const detailHost = document.getElementById('detail-visual');
    if (detailHost) {
      detailHost.innerHTML = '';
      this.detail = new window.StockDetail('#detail-visual', { width: 820, height: 390 });
    }

    this.sidebar = new window.Sidebar('#leaderboard-host', { width: 280 });
  }

  bindUI() {
    const startBtn = document.getElementById('start-cycle-btn');
    const stopBtn = document.getElementById('stop-cycle-btn');
    const closeBtn = document.getElementById('close-detail');
    const backdrop = document.getElementById('detail-backdrop');
    const tickerBtn = document.getElementById('ticker-pause-btn');
    const ticker = document.getElementById('ticker-content');

    startBtn?.addEventListener('click', async () => {
      this.setCycleButtonState(true);
      try {
        await this.api.startCycle();
      } catch (err) {
        this.toast('Failed to start cycle');
        this.setCycleButtonState(false);
      }
    });

    stopBtn?.addEventListener('click', async () => {
      if (!this.currentCycle?.id) return;
      try {
        await this.api.stopCycle(this.currentCycle.id);
      } catch (err) {
        this.toast('Failed to stop cycle');
      }
      this.setCycleButtonState(false);
      window.resetPhases?.();
    });

    closeBtn?.addEventListener('click', () => this.closeDetail());
    backdrop?.addEventListener('click', () => this.closeDetail());

    tickerBtn?.addEventListener('click', () => {
      const paused = tickerBtn.getAttribute('aria-pressed') === 'true';
      tickerBtn.setAttribute('aria-pressed', paused ? 'false' : 'true');
      tickerBtn.textContent = paused ? 'Pause' : 'Play';
      tickerBtn.setAttribute('aria-label', paused ? 'Pause ticker' : 'Resume ticker');
      ticker?.classList.toggle('paused', !paused);
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && this.selectedSymbol) {
        this.closeDetail();
      }

      const inInput = /INPUT|TEXTAREA|SELECT/.test(event.target.tagName) || event.target.isContentEditable;
      if (!inInput && (event.key === 'r' || event.key === 'R')) {
        this.reload();
        this.announce('Dashboard refreshed');
      }
    });
  }

  async bootstrap() {
    await this.reload();
    await Promise.all([this.loadProviderHealth(), this.loadHistory()]);
    this.providerHealthTimer = setInterval(() => this.loadProviderHealth(), 15000);
    this.connectStream();
  }

  async reload() {
    await Promise.all([this.loadCurrent(), this.loadStats()]);
  }

  async loadCurrent() {
    try {
      const payload = await this.api.current();
      if (!payload?.cycle) {
        this.currentCycle = null;
        this.renderCycleCard(null);
        this.grid.update([]);
        this.showGridEmpty();
        return;
      }

      this.currentCycle = payload.cycle;
      this.renderCycleCard(payload.cycle);
      this.hideGridEmpty();
      this.grid.update(this.predictionsToGrid(payload.predictions || []));

      const active = ['running', 'active'].includes(payload.cycle.status);
      this.setCycleButtonState(active);
      if (active) window.setPhase?.('analysis');
      else window.resetPhases?.();
    } catch (err) {
      this.toast('Failed to load current cycle');
      this.showGridEmpty();
    }
  }

  predictionsToGrid(predictions) {
    return predictions.map((p) => ({
      symbol: p.ticker,
      name: p.name,
      price: p.predicted_price ?? p.initial_price,
      prediction: p.predicted_direction,
      confidence: p.confidence,
      accuracy: p.accuracy,
      provider: p.provider
    }));
  }

  renderCycleCard(cycle) {
    const card = document.getElementById('current-cycle-info');
    if (!card) return;

    if (!cycle) {
      card.innerHTML = '<p>No active cycle</p>';
      return;
    }

    const ts = cycle.start_time || cycle.started_at;
    const started = ts ? new Date(ts).toLocaleTimeString() : '--';
    const label = cycle._is_historical ? 'Last cycle' : `Cycle #${cycle.id}`;
    card.innerHTML = `<p>${label} <b style="color:var(--accent);text-transform:uppercase;">${cycle.status || 'unknown'}</b></p><p style="margin-top:.35rem;">Started ${started}</p>`;
  }

  async loadStats() {
    try {
      const stats = await this.api.stats();
      this.sidebar.update(stats);

      const set = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
      };

      set('stat-total-predictions', Number(stats.total_predictions ?? 0).toLocaleString());
      set('stat-overall-accuracy', Number.isFinite(+stats.overall_accuracy) ? `${(+stats.overall_accuracy * 100).toFixed(1)}%` : '--');
      set('stat-cycles', Number(stats.total_cycles ?? 0).toLocaleString());
      set('stat-stocks', Number(stats.total_stocks ?? 0).toLocaleString());
    } catch (err) {
      this.toast('Failed to load stats');
    }
  }

  async loadHistory() {
    const host = document.getElementById('cycle-history');
    if (!host) return;

    try {
      const response = await fetch(`${API_ROOT}api/history?per_page=8`);
      const payload = await response.json();
      const cycles = payload?.cycles || [];

      if (!cycles.length) {
        host.innerHTML = '<p class="provider-health-empty">No completed cycles yet.</p>';
        return;
      }

      host.innerHTML = cycles.map((c) => {
        const started = c.start_time ? new Date(c.start_time).toLocaleString([], {
          month: 'short', day: 'numeric',
          hour: '2-digit', minute: '2-digit'
        }) : '--';
        const status = c.status || 'unknown';
        const preds = Number(c.predictions_made || 0);
        const stocks = Number(c.stocks_discovered || 0);
        return `
          <article class="cycle-history-item">
            <div>
              <span class="ch-id">#${c.id}</span>
              <span class="ch-time"> ${started}</span>
              <div class="ch-count">${stocks} stocks · ${preds} predictions</div>
            </div>
            <span class="ch-status ${status}">${status}</span>
          </article>
        `;
      }).join('');
    } catch (err) {
      host.innerHTML = '<p class="provider-health-empty">History unavailable.</p>';
    }
  }

  async loadProviderHealth() {
    const host = document.getElementById('provider-health');
    if (!host) return;

    try {
      const response = await fetch(`${API_ROOT}api/health/providers`);
      const payload = await response.json();
      const providers = payload?.providers || {};
      const runtime = payload?.runtime || {};
      const merged = {};

      // Configured roles first
      Object.entries(providers).forEach(([role, info]) => {
        const key = info?.provider || role;
        merged[key] = {
          key,
          role,
          status: info?.status || 'error',
          last_error: info?.last_error || info?.error || null
        };
      });

      // Add any runtime-only providers (xai, perplexity, etc.)
      Object.entries(runtime).forEach(([providerName, info]) => {
        if (!merged[providerName]) {
          merged[providerName] = {
            key: providerName,
            role: 'runtime',
            status: info?.healthy ? 'configured' : 'error',
            last_error: info?.last_error || null
          };
        } else if (info?.healthy === false) {
          // Runtime failure overrides configured-ok surface
          merged[providerName].status = 'error';
          merged[providerName].last_error = info?.last_error || merged[providerName].last_error;
        }
      });

      const entries = Object.values(merged);

      if (!entries.length) {
        host.innerHTML = '<p class="provider-health-empty">No provider health data.</p>';
        return;
      }

      host.innerHTML = entries.map((item) => {
        const failed = item.status !== 'configured';
        const name = (item.key || 'unknown').toUpperCase();
        const state = failed ? 'FAIL' : 'OK';
        const stateClass = failed ? 'fail' : 'ok';
        const link = PROVIDER_LINKS[(item.key || '').toLowerCase()];
        const { label, linkText } = failed ? classifyProviderError(item.last_error) : {};
        const errHtml = failed
          ? `<p class="provider-error">${label}${link ? ` <a href="${link}" target="_blank" rel="noopener noreferrer" class="provider-err-link">${linkText}</a>` : ''}</p>`
          : '';
        return `
          <article class="provider-health-item">
            <div class="provider-health-head">
              <span class="provider-name">${name}</span>
              <span class="provider-state ${stateClass}">${state}</span>
            </div>
            ${errHtml}
          </article>
        `;
      }).join('');

      if (!payload.healthy) {
        this.setConnectionStatus('reconnecting');
      }
    } catch (err) {
      host.innerHTML = '<p class="provider-health-empty">Provider health unavailable.</p>';
    }
  }

  async selectStock(symbol) {
    if (!symbol) return;

    this.selectedSymbol = symbol;
    this.lastFocusedTile = document.activeElement;

    const drawer = document.getElementById('stock-detail');
    const detailSymbol = document.getElementById('detail-symbol');
    if (detailSymbol) detailSymbol.textContent = `${symbol} Detail`;
    if (drawer) {
      drawer.setAttribute('aria-hidden', 'false');
      drawer.setAttribute('aria-modal', 'true');
      drawer.setAttribute('aria-label', `${symbol} stock details`);
    }

    this.grid.highlightTile(symbol);

    try {
      const payload = await this.api.stock(symbol);
      this.detail?.update(payload);
      this.announce(`Selected ${symbol}`);
    } catch (err) {
      this.toast(`Failed to load ${symbol}`);
    }
  }

  closeDetail() {
    const drawer = document.getElementById('stock-detail');
    if (drawer) {
      drawer.setAttribute('aria-hidden', 'true');
      drawer.removeAttribute('aria-modal');
    }

    this.selectedSymbol = null;
    this.grid.highlightTile(null);

    if (this.lastFocusedTile?.focus) {
      this.lastFocusedTile.focus();
      this.lastFocusedTile = null;
    }
  }

  setCycleButtonState(running) {
    const startBtn = document.getElementById('start-cycle-btn');
    const stopBtn = document.getElementById('stop-cycle-btn');
    if (startBtn) startBtn.disabled = !!running;
    if (stopBtn) stopBtn.disabled = !running;
  }

  connectStream() {
    if (this.eventSource) this.eventSource.close();

    this.eventSource = new EventSource(`${API_ROOT}api/stream`);
    this.eventSource.onopen = () => this.setConnectionStatus('connected');
    this.eventSource.onerror = () => this.setConnectionStatus('reconnecting');
    this.eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        this.handleStream(payload);
      } catch (err) {
        // Ignore malformed SSE events.
      }
    };
  }

  handleStream(payload) {
    const type = payload?.type;

    if (type === 'connected' || type === 'heartbeat') return;

    if (type === 'error') {
      const msg = payload?.error || 'Stream error';
      this.toast(msg.length > 80 ? msg.slice(0, 77) + '…' : msg);
      return;
    }

    if (type === 'cycle_start') {
      this.currentCycle = payload.cycle || null;
      this.renderCycleCard(this.currentCycle);
      this.setCycleButtonState(true);
      window.setPhase?.('discovery');
      this.toast('New prediction cycle started');
      return;
    }

    if (type === 'cycle_complete' || type === 'cycle_end') {
      this.setCycleButtonState(false);
      window.resetPhases?.();
      this.toast('Prediction cycle completed');
      this.reload();
      this.loadHistory();
      return;
    }

    if (type === 'analysis_start') {
      window.setPhase?.('analysis');
      return;
    }

    if (type === 'debate_start') {
      window.setPhase?.('debate');
      return;
    }

    if (type === 'consensus_start') {
      window.setPhase?.('consensus');
      return;
    }

    if (type === 'stock_discovered') {
      window.setPhase?.('discovery');
      const ticker = payload?.data?.ticker;
      if (ticker) this.grid.patchTile(ticker, { symbol: ticker });
      return;
    }

    if (type === 'price_update') {
      const ticker = payload?.data?.ticker;
      const price = payload?.data?.price;
      if (ticker && Number.isFinite(+price)) this.grid.patchTile(ticker, { price: +price });
      return;
    }

    if (type === 'prediction' || type === 'prediction_made') {
      window.setPhase?.('analysis');
      const symbol = payload.ticker || payload.stock?.symbol || payload.stock?.ticker || '';
      const direction = payload.predicted_direction || payload.prediction || payload.data?.direction || 'neutral';
      const confidence = payload.confidence ?? payload.data?.confidence;
      if (symbol) {
        this.grid.patchTile(symbol, { prediction: direction, confidence });
        const signal = direction === 'up' ? '▲' : direction === 'down' ? '▼' : '—';
        this.pushTicker(`${symbol} ${signal}`);
      }
    }
  }

  setConnectionStatus(status) {
    const indicator = document.getElementById('status-indicator');
    const text = document.getElementById('status-text');
    if (indicator) indicator.className = `status-indicator ${status}`;
    if (text) {
      if (status === 'connected') text.textContent = 'Connected';
      else if (status === 'reconnecting') text.textContent = 'Reconnecting...';
      else text.textContent = 'Disconnected';
    }
  }

  pushTicker(text) {
    const el = document.getElementById('ticker-content');
    if (!el) return;

    if (el.textContent.includes('Awaiting first cycle')) {
      el.textContent = '';
    }

    this.tickerItems.push(`${text}   `);
    if (this.tickerItems.length > 40) this.tickerItems.shift();
    const half = this.tickerItems.join('');
    el.textContent = half + half;
  }

  showGridEmpty() {
    const host = document.getElementById('grid-stage');
    if (!host || host.querySelector('.empty-state')) return;

    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.style.cssText = 'position:absolute;inset:0;display:grid;place-items:center;color:var(--muted);font-size:.84rem;pointer-events:none;';
    empty.textContent = 'Awaiting cycle start...';
    host.appendChild(empty);
  }

  hideGridEmpty() {
    const node = document.querySelector('#grid-stage .empty-state');
    if (node) node.remove();
  }

  toast(message) {
    const node = document.createElement('div');
    node.className = 'toast';
    node.setAttribute('role', 'status');
    node.setAttribute('aria-live', 'polite');
    node.textContent = message;
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 2400);
  }

  announce(message) {
    const node = document.getElementById('sr-announcer');
    if (!node) return;
    node.textContent = '';
    requestAnimationFrame(() => {
      node.textContent = message;
    });
  }

  destroy() {
    if (this.eventSource) this.eventSource.close();
    if (this.providerHealthTimer) clearInterval(this.providerHealthTimer);
    this.grid?.destroy();
    this.detail?.destroy();
    this.sidebar?.destroy();
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    window.foresightDashboard = new ForesightDashboard();
  });
} else {
  window.foresightDashboard = new ForesightDashboard();
}

window.addEventListener('beforeunload', () => {
  window.foresightDashboard?.destroy();
});
