/**
 * Foresight Dashboard - Main Application
 * Integrates StockGrid, StockDetail, and Sidebar visualizations with SSE streaming
 */

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

    // Stock Detail
    const detailContainer = d3.select('#stock-detail');
    if (!detailContainer.empty()) {
      this.detail = new StockDetail('#stock-detail', {
        width: 800,
        height: 400
      });
    }

    // Sidebar
    const sidebarContainer = d3.select('#sidebar');
    if (!sidebarContainer.empty()) {
      this.sidebar = new Sidebar('#sidebar', {
        width: 300
      });
    }
  }

  async loadCurrentCycle() {
    try {
      const response = await fetch('/api/current');
      const data = await response.json();

      if (data.cycle) {
        this.currentCycle = data.cycle;
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

  async loadStats() {
    try {
      const response = await fetch('/api/stats');
      const data = await response.json();

      if (this.sidebar) {
        this.sidebar.update(data);
      }
    } catch (error) {
      console.error('Failed to load stats:', error);
    }
  }

  async selectStock(symbol) {
    this.selectedStock = symbol;

    try {
      const response = await fetch(`/api/stock/${symbol}`);
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

    this.eventSource = new EventSource('/api/stream');

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
      this.updateConnectionStatus('disconnected');

      // Attempt reconnection after delay
      setTimeout(() => {
        if (this.eventSource.readyState === EventSource.CLOSED) {
          console.log('Attempting to reconnect...');
          this.connectToStream();
        }
      }, 5000);
    };

    // Listen for custom event types
    this.eventSource.addEventListener('prediction', (event) => {
      const data = JSON.parse(event.data);
      this.handlePrediction(data);
    });

    this.eventSource.addEventListener('cycle_start', (event) => {
      const data = JSON.parse(event.data);
      this.handleCycleStart(data);
    });

    this.eventSource.addEventListener('cycle_complete', (event) => {
      const data = JSON.parse(event.data);
      this.handleCycleComplete(data);
    });
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
        // Reload grid to show new stock
        this.loadCurrentCycle();
        break;
      case 'price_update':  // Backend event type
        // Could update specific stock, but reload for now
        this.loadCurrentCycle();
        break;
      default:
        console.log('Unknown event type:', data.type);
    }
  }

  handlePrediction(data) {
    console.log('New prediction:', data);

    // Reload current cycle to get updated data
    this.loadCurrentCycle();

    // Reload stats if provider stats might have changed
    this.loadStats();

    // Visual notification
    this.showNotification(`New prediction for ${data.stock?.symbol || 'stock'}`);
  }

  handleCycleStart(data) {
    console.log('Cycle started:', data);
    this.currentCycle = data.cycle;
    this.showNotification('New prediction cycle started');
    this.loadCurrentCycle();
  }

  handleCycleComplete(data) {
    console.log('Cycle completed:', data);
    this.showNotification('Prediction cycle completed');
    this.loadCurrentCycle();
    this.loadStats();
  }

  updateConnectionStatus(status) {
    const indicator = document.querySelector('#connection-status');
    if (!indicator) return;

    if (status === 'connected') {
      indicator.textContent = '🟢 Connected';
      indicator.style.color = 'var(--stock-up)';
    } else {
      indicator.textContent = '🔴 Disconnected';
      indicator.style.color = 'var(--stock-down)';
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
      border-radius: 8px;
      padding: 12px 20px;
      color: var(--text-primary);
      backdrop-filter: blur(10px);
      z-index: 1000;
      animation: slideIn 0.3s ease-out;
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'slideOut 0.3s ease-out';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  showError(message) {
    console.error(message);
    const statusEl = document.querySelector('#status');
    if (statusEl) {
      statusEl.innerHTML = `
        <h2 style="color: var(--stock-down);">Error</h2>
        <p>${message}</p>
      `;
    }
  }

  showEmptyState() {
    const gridEl = document.querySelector('#stock-grid');
    if (gridEl) {
      gridEl.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 400px; gap: 20px;">
          <div class="loading-spinner" style="width: 40px; height: 40px; border: 3px solid var(--glass-border); border-top: 3px solid var(--accent); border-radius: 50%; animation: spin 1s linear infinite;"></div>
          <h2 style="margin: 0; color: var(--text-primary);">Waiting for Predictions</h2>
          <p style="margin: 0; color: var(--text-secondary); text-align: center; max-width: 300px;">
            The prediction engine is running its first cycle. This typically takes 30-60 seconds.
          </p>
          <p style="margin: 0; color: var(--text-secondary); font-size: 0.9em;">
            Or click "Start New Cycle" to trigger immediately
          </p>
        </div>
      `;
    }
  }

  setupKeyboardNav() {
    document.addEventListener('keydown', (e) => {
      // Escape to deselect
      if (e.key === 'Escape' && this.selectedStock) {
        this.selectedStock = null;
        if (this.grid) {
          this.grid.highlightTile(null);
        }
        if (this.detail) {
          this.detail.showEmpty();
        }
      }

      // R to refresh
      if (e.key === 'r' || e.key === 'R') {
        this.loadCurrentCycle();
        this.loadStats();
        this.announce('Dashboard refreshed');
      }
    });
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
