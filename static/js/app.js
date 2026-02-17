/**
 * Foresight Dashboard - Main Application
 * Integrates StockGrid, StockDetail, and Sidebar visualizations with SSE streaming
 */

// Detect app root path so API calls work behind any URL prefix (e.g. /foresight/)
const API_ROOT = (() => {
  const p = window.location.pathname;
  return p.endsWith('/') ? p : p.substring(0, p.lastIndexOf('/') + 1);
})();

class ForesightDashboard {
  constructor() {
    this.grid = null;
    this.detail = null;
    this.sidebar = null;
    this.eventSource = null;
    this.currentCycle = null;
    this.selectedStock = null;

    this.init();
  }

  init() {
    console.log('Foresight Dashboard initializing...');

    // Check D3.js availability
    if (typeof d3 === 'undefined') {
      console.error('D3.js not loaded. Include D3.js v7 before app.js');
      this.showError('Visualization library not loaded');
      return;
    }

    // Initialize visualizations
    this.initializeVisualizations();

    // Load initial data
    this.loadCurrentCycle();
    this.loadStats();

    // Setup SSE streaming
    this.connectToStream();

    // Keyboard navigation
    this.setupKeyboardNav();

    // Wire cycle control buttons
    const startBtn = document.getElementById('start-cycle-btn');
    const stopBtn  = document.getElementById('stop-cycle-btn');

    if (startBtn) {
      startBtn.addEventListener('click', async () => {
        startBtn.disabled = true;
        if (stopBtn) stopBtn.disabled = false;
        try {
          await fetch(`${API_ROOT}api/cycle/start`, { method: 'POST' });
        } catch (e) {
          console.error('Failed to start cycle:', e);
          startBtn.disabled = false;
          if (stopBtn) stopBtn.disabled = true;
        }
      });
    }

    if (stopBtn) {
      stopBtn.addEventListener('click', async () => {
        if (!this.currentCycle) return;
        try {
          await fetch(`${API_ROOT}api/cycle/${this.currentCycle.id}/stop`, { method: 'POST' });
        } catch (e) {
          console.error('Failed to stop cycle:', e);
        }
        stopBtn.disabled = true;
        if (startBtn) startBtn.disabled = false;
        if (window.resetPhases) window.resetPhases();
      });
    }
  }

  initializeVisualizations() {
    // Stock Grid
    const gridContainer = d3.select('#stock-grid');
    if (!gridContainer.empty()) {
      this.grid = new StockGrid('#stock-grid', {
        columns: 10,
        tileSize: 120,
        gap: 8,
        onTileClick: (stock) => this.selectStock(stock.symbol)
      });
    }

    // Stock Detail — mount inside the body section, not the full aside
    // (the aside contains a close button header that must remain interactive)
    const detailContainer = d3.select('#detail-body');
    if (!detailContainer.empty()) {
      detailContainer.html(''); // clear loading skeleton placeholder
      this.detail = new StockDetail('#detail-body', {
        width: 800,
        height: 400
      });
    }

    // Sidebar — mount inside the leaderboard section, not the full sidebar
    const sidebarContainer = d3.select('#provider-stats');
    if (!sidebarContainer.empty()) {
      // Clear the loading skeleton
      sidebarContainer.html('');
      this.sidebar = new Sidebar('#provider-stats', {
        width: 240
      });
    }
  }

  async loadCurrentCycle() {
    try {
      const response = await fetch(`${API_ROOT}api/current`);
      const data = await response.json();

      if (data.cycle) {
        this.currentCycle = data.cycle;

        // Clear empty-state overlay if present
        const overlay = document.querySelector('#stock-grid .empty-state');
        if (overlay) overlay.remove();

        // Update cycle info in sidebar
        this.updateCycleInfo(data.cycle);

        // API returns predictions as separate top-level field, not in cycle.stocks
        this.updateGrid(data.predictions || []);
      } else {
        console.log('No active cycle');
        this.showEmptyState();
      }
    } catch (error) {
      console.error('Failed to load current cycle:', error);
      this.showError('Failed to load prediction data');
    }
  }

  updateCycleInfo(cycle) {
    const infoEl = document.getElementById('current-cycle-info');
    if (!infoEl) return;

    const started = cycle.started_at
      ? new Date(cycle.started_at).toLocaleTimeString()
      : '—';
    const status = cycle.status || 'unknown';

    infoEl.innerHTML = `
      <p class="cycle-status">Cycle #${cycle.id} &mdash; <span style="color:var(--accent-primary);text-transform:uppercase;font-size:.7rem;letter-spacing:.1em;">${status}</span></p>
      <p style="margin:.25rem 0 0;color:var(--text-muted);font-family:var(--font-data);font-size:.7rem;">Started ${started}</p>
    `;

    // Sync button state and phase display
    const running = status === 'running' || status === 'active';
    this.setCycleButtonState(running);
    if (running && window.setPhase) window.setPhase('analysis'); // best guess mid-cycle
    if (!running && window.resetPhases) window.resetPhases();
  }

  async loadStats() {
    try {
      const response = await fetch(`${API_ROOT}api/stats`);
      const data = await response.json();

      if (this.sidebar) {
        this.sidebar.update(data);
      }

      // Update intelligence bar stats
      const totalPreds = document.getElementById('stat-total-predictions');
      const overallAcc  = document.getElementById('stat-overall-accuracy');
      const cyclesEl    = document.getElementById('stat-cycles');
      const stocksEl    = document.getElementById('stat-stocks');

      if (totalPreds && data.total_predictions !== undefined) {
        totalPreds.textContent = data.total_predictions.toLocaleString();
      }
      if (overallAcc && data.overall_accuracy !== undefined) {
        overallAcc.textContent = `${(data.overall_accuracy * 100).toFixed(1)}%`;
      }
      if (cyclesEl && data.total_cycles !== undefined) {
        cyclesEl.textContent = data.total_cycles.toLocaleString();
      }
      if (stocksEl && data.total_stocks !== undefined) {
        stocksEl.textContent = data.total_stocks.toLocaleString();
      }
    } catch (error) {
      console.error('Failed to load stats:', error);
    }
  }

  async selectStock(symbol) {
    this.selectedStock = symbol;

    // Store the tile that triggered the open so we can return focus on close
    this._lastFocusedTile = document.activeElement;

    // Open panel immediately — don't wait for fetch
    const panel = document.getElementById('stock-detail');
    const backdrop = document.getElementById('detail-backdrop');
    if (panel) {
      // Show empty/cleared state while loading (don't destroy the D3 SVG via innerHTML)
      if (this.detail) this.detail.showEmpty();
      panel.setAttribute('aria-hidden', 'false');
      panel.setAttribute('aria-modal', 'true');
      // Focus the close button after the slide-in transition completes
      setTimeout(() => {
        const closeBtn = document.getElementById('close-detail');
        if (closeBtn) closeBtn.focus();
      }, 360);
    }
    if (backdrop) {
      backdrop.style.display = 'block';
      backdrop.offsetHeight; // force reflow for CSS transition
      backdrop.classList.add('visible');
    }

    try {
      const response = await fetch(`${API_ROOT}api/stock/${symbol}`);
      const data = await response.json();

      if (this.detail) {
        this.detail.update(data);
      }

      if (this.grid) {
        this.grid.highlightTile(symbol);
      }

      // Announce for screen readers
      this.announce(`Selected stock ${symbol}`);
    } catch (error) {
      console.error(`Failed to load stock ${symbol}:`, error);
      this.showError(`Failed to load ${symbol} details`);
    }
  }

  closeDetail() {
    const panel = document.getElementById('stock-detail');
    const backdrop = document.getElementById('detail-backdrop');
    if (panel) {
      panel.setAttribute('aria-hidden', 'true');
      panel.removeAttribute('aria-modal');
    }
    if (backdrop) {
      backdrop.classList.remove('visible');
      setTimeout(() => { backdrop.style.display = 'none'; }, 300);
    }
    this.selectedStock = null;
    if (this.grid) this.grid.highlightTile(null);
    // Return focus to the tile that triggered the panel open
    if (this._lastFocusedTile && this._lastFocusedTile.focus) {
      this._lastFocusedTile.focus();
      this._lastFocusedTile = null;
    }
  }

  updateGrid(predictions) {
    if (!this.grid) return;

    // Transform predictions data for grid
    // API returns predictions with: ticker, name, predicted_direction, confidence, accuracy, etc.
    const gridData = predictions.map(pred => ({
      symbol: pred.ticker,  // API returns 'ticker' not 'symbol'
      name: pred.name,
      price: pred.predicted_price || pred.initial_price,  // Use predicted or initial price
      change: null,  // Change percent not in predictions, would need price history
      prediction: pred.predicted_direction,  // 'up', 'down', 'neutral'
      confidence: pred.confidence,
      accuracy: pred.accuracy,
      provider: pred.provider
    }));

    this.grid.update(gridData);
  }

  connectToStream() {
    if (this.eventSource) {
      this.eventSource.close();
    }

    this.eventSource = new EventSource(`${API_ROOT}api/stream`);

    this.eventSource.onopen = () => {
      console.log('SSE connection established');
      this.updateConnectionStatus('connected');
    };

    this.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleStreamEvent(data);
      } catch (error) {
        console.error('Failed to parse SSE event:', error);
      }
    };

    this.eventSource.onerror = (error) => {
      console.error('SSE connection error:', error);
      this.updateConnectionStatus('reconnecting');

      // Attempt reconnection after delay
      setTimeout(() => {
        if (this.eventSource.readyState === EventSource.CLOSED) {
          console.log('Attempting to reconnect...');
          this.connectToStream();
        }
      }, 5000);
    };

    // Backend emits plain `data:` events (no `event:` header),
    // so all routing is handled by onmessage → handleStreamEvent()
  }

  handleStreamEvent(data) {
    switch (data.type) {
      case 'connected':
        console.log('Connected to stream');
        break;
      case 'heartbeat':
        // Keep-alive, no action needed
        break;
      // Map backend event types to frontend handlers
      case 'prediction':
      case 'prediction_made':  // Backend event type
        if (window.setPhase) window.setPhase('analysis');
        this.handlePrediction(data);
        break;
      case 'cycle_start':
        this.handleCycleStart(data);
        break;
      case 'cycle_complete':
      case 'cycle_end':  // Backend event type
        this.handleCycleComplete(data);
        break;
      case 'stock_discovered':  // Backend event type
        if (window.setPhase) window.setPhase('discovery');
        // Add a placeholder tile for the newly discovered stock
        if (data.data?.stock_id && this.grid) {
          const ticker = data.data?.ticker || '';
          if (ticker) this.grid.patchTile(ticker, { symbol: ticker });
        }
        break;
      case 'analysis_start':
        if (window.setPhase) window.setPhase('analysis');
        break;
      case 'debate_start':
        if (window.setPhase) window.setPhase('debate');
        break;
      case 'consensus_start':
        if (window.setPhase) window.setPhase('consensus');
        break;
      case 'price_update':  // Backend event type
        // Patch the specific tile's price without a full reload
        if (data.data?.stock_id && this.grid) {
          const price = data.data?.price;
          if (price) this.grid.patchTile(data.data?.ticker || '', { price });
        }
        break;
      default:
        console.log('Unknown event type:', data.type);
    }
  }

  handlePrediction(data) {
    console.log('New prediction:', data);

    // Patch the grid in-memory from the SSE payload — avoids a full fetch+re-render
    // during active cycles where many predictions arrive in quick succession
    const symbol = data.ticker || data.stock?.symbol || data.stock?.ticker || '';
    const direction = data.predicted_direction || data.prediction || data.data?.direction || '';
    const confidence = data.confidence || data.data?.confidence;
    if (symbol && this.grid) {
      this.grid.patchTile(symbol, { prediction: direction, confidence });
    }

    // Update ticker tape with latest prediction
    const symbol = data.ticker || data.stock?.symbol || data.stock?.ticker || '';
    const direction = data.predicted_direction || data.prediction || '';
    if (symbol) {
      const dirLabel = direction === 'up' ? '▲' : direction === 'down' ? '▼' : '—';
      this.addTickerItem(`${symbol} ${dirLabel}`);
    }
  }

  addTickerItem(text) {
    const ticker = document.getElementById('ticker-content');
    if (!ticker) return;

    // Strip the placeholder if still present
    if (ticker.dataset.init !== 'true') {
      ticker.innerHTML = '';
      ticker.dataset.init = 'true';
    }

    // Track items in an array so we can rebuild the doubled content (capped at 40)
    if (!this._tickerItems) this._tickerItems = [];
    this._tickerItems.push(`${text}   `);
    if (this._tickerItems.length > 40) this._tickerItems.shift();

    // The -50% translateX animation requires content doubled inside the container
    // for a seamless infinite scroll loop (second half is the invisible reset point)
    const half = this._tickerItems.join('');
    ticker.textContent = half + half;
  }

  handleCycleStart(data) {
    console.log('Cycle started:', data);
    this.currentCycle = data.cycle;
    this.showNotification('New prediction cycle started');
    if (window.setPhase) window.setPhase('discovery');
    this.setCycleButtonState(true);
    this.loadCurrentCycle();
  }

  handleCycleComplete(data) {
    console.log('Cycle completed:', data);
    this.showNotification('Prediction cycle completed');
    if (window.resetPhases) window.resetPhases();
    this.setCycleButtonState(false);
    this.loadCurrentCycle();
    this.loadStats();
  }

  setCycleButtonState(running) {
    const startBtn = document.getElementById('start-cycle-btn');
    const stopBtn  = document.getElementById('stop-cycle-btn');
    if (startBtn) startBtn.disabled = running;
    if (stopBtn)  stopBtn.disabled  = !running;
  }

  updateConnectionStatus(status) {
    const dot  = document.getElementById('status-indicator');
    const text = document.getElementById('status-text');

    if (dot) {
      dot.className = 'status-indicator'; // reset all state classes
      dot.classList.add(status); // 'connected' | 'disconnected' | 'reconnecting'
    }
    if (text) {
      text.textContent = status === 'connected' ? 'Connected'
        : status === 'reconnecting' ? 'Reconnecting...'
        : 'Disconnected';
    }
  }

  showNotification(message) {
    // Create toast notification
    const toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.textContent = message;
    toast.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      background: var(--glass-bg);
      border: 1px solid var(--glass-border);
      border-radius: 4px;
      padding: 10px 16px;
      color: var(--text-primary);
      font-family: var(--font-data);
      font-size: 0.75rem;
      letter-spacing: 0.05em;
      backdrop-filter: blur(10px);
      z-index: 2000;
    `;

    document.body.appendChild(toast);

    toast.classList.add('toast-notification');
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.25s ease-out';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  showError(message) {
    console.error(message);
    // Show as a notification since there's no dedicated #status element
    this.showNotification(`⚠ ${message}`);
  }

  showEmptyState() {
    // Don't replace the D3 container; append a floating message inside it
    const gridEl = document.querySelector('#stock-grid');
    if (!gridEl) return;

    const existing = gridEl.querySelector('.empty-state');
    if (existing) return; // Already shown

    const msg = document.createElement('div');
    msg.className = 'empty-state';
    msg.style.cssText = [
      'position:absolute', 'inset:0', 'display:flex', 'flex-direction:column',
      'align-items:center', 'justify-content:center', 'gap:1rem',
      'pointer-events:none'
    ].join(';');
    msg.innerHTML = `
      <div class="loading-spinner" style="width:36px;height:36px;border:2px solid var(--glass-border);border-top:2px solid var(--accent-primary);border-radius:50%;"></div>
      <p style="margin:0;color:var(--text-primary);font-family:var(--font-display);letter-spacing:.08em;">Awaiting Oracle</p>
      <p style="margin:0;color:var(--text-muted);font-family:var(--font-data);font-size:.75rem;">Run Cycle to begin</p>
    `;
    // Make container relative so absolute child positions correctly
    gridEl.style.position = 'relative';
    gridEl.appendChild(msg);
  }

  setupKeyboardNav() {
    document.addEventListener('keydown', (e) => {
      // Escape to close detail panel
      if (e.key === 'Escape' && this.selectedStock) {
        this.closeDetail();
        if (this.detail) this.detail.showEmpty();
      }

      // R to refresh (not in inputs)
      const tag = e.target.tagName;
      if ((e.key === 'r' || e.key === 'R') && tag !== 'INPUT' && tag !== 'TEXTAREA' && !e.target.isContentEditable) {
        this.loadCurrentCycle();
        this.loadStats();
        this.announce('Dashboard refreshed');
      }
    });

    // Close button
    const closeBtn = document.getElementById('close-detail');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        this.closeDetail();
        if (this.detail) this.detail.showEmpty();
      });
    }

    // Backdrop click to close
    const backdrop = document.getElementById('detail-backdrop');
    if (backdrop) {
      backdrop.addEventListener('click', () => {
        this.closeDetail();
        if (this.detail) this.detail.showEmpty();
      });
    }
  }

  announce(message) {
    // Screen reader announcement
    const announcement = document.createElement('div');
    announcement.setAttribute('role', 'status');
    announcement.setAttribute('aria-live', 'polite');
    announcement.className = 'sr-only';
    announcement.textContent = message;
    document.body.appendChild(announcement);

    setTimeout(() => announcement.remove(), 1000);
  }

  destroy() {
    if (this.eventSource) {
      this.eventSource.close();
    }
    if (this.grid) {
      this.grid.destroy();
    }
    if (this.detail) {
      this.detail.destroy();
    }
    if (this.sidebar) {
      this.sidebar.destroy();
    }
  }
}

// Initialize dashboard when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    window.foresightDashboard = new ForesightDashboard();
  });
} else {
  window.foresightDashboard = new ForesightDashboard();
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  if (window.foresightDashboard) {
    window.foresightDashboard.destroy();
  }
});
