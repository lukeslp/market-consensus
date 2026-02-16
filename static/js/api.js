/**
 * Foresight API Client
 * Clean interface for REST endpoints with error handling
 */

class ForesightAPI {
  constructor(baseURL = '') {
    this.baseURL = baseURL;
  }

  async request(endpoint, options = {}) {
    try {
      const response = await fetch(`${this.baseURL}${endpoint}`, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        },
        ...options
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({
          error: 'Unknown Error',
          message: response.statusText
        }));
        throw new APIError(error.message, response.status, error);
      }

      return await response.json();
    } catch (error) {
      if (error instanceof APIError) {
        throw error;
      }
      throw new APIError(error.message, 0, { originalError: error });
    }
  }

  // Health check
  async health() {
    return this.request('/health');
  }

  // Current cycle
  async getCurrentCycle() {
    return this.request('/api/current');
  }

  // Provider statistics
  async getStats() {
    return this.request('/api/stats');
  }

  // Historical cycles
  async getHistory(page = 1, limit = 20) {
    return this.request(`/api/history?page=${page}&limit=${limit}`);
  }

  // Stock details
  async getStock(symbol) {
    return this.request(`/api/stock/${symbol}`);
  }

  // Start new cycle
  async startCycle() {
    return this.request('/api/cycle/start', {
      method: 'POST'
    });
  }

  // Stop cycle
  async stopCycle(cycleId) {
    return this.request(`/api/cycle/${cycleId}/stop`, {
      method: 'POST'
    });
  }

  // SSE connection
  createEventSource() {
    return new EventSource(`${this.baseURL}/api/stream`);
  }
}

class APIError extends Error {
  constructor(message, status, data) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.data = data;
  }
}

// Export singleton instance
const api = new ForesightAPI();

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ForesightAPI, APIError, api };
}
