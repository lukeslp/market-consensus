class APIError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.payload = payload;
  }
}

class ForesightAPI {
  constructor(base = '') {
    this.base = base;
  }

  async request(path, options = {}) {
    const response = await fetch(`${this.base}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options
    });

    if (!response.ok) {
      let payload = null;
      try { payload = await response.json(); } catch (err) { payload = null; }
      throw new APIError(payload?.message || response.statusText, response.status, payload);
    }

    return response.json();
  }

  health() { return this.request('/health'); }
  current() { return this.request('/api/current'); }
  stats() { return this.request('/api/stats'); }
  stock(symbol) { return this.request(`/api/stock/${symbol}`); }
  startCycle() { return this.request('/api/cycle/start', { method: 'POST' }); }
  stopCycle(id) { return this.request(`/api/cycle/${id}/stop`, { method: 'POST' }); }
}

window.ForesightAPI = ForesightAPI;
window.APIError = APIError;
