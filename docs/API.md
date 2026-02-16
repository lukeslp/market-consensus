# Foresight API Documentation

Version: 1.0.0

## Overview

The Foresight API provides real-time stock prediction data using multi-provider language models. The system runs prediction cycles every 10 minutes, discovering trending stocks and generating predictions with confidence scores.

**Base URLs:**
- Production: `https://dr.eamer.dev/foresight/api`
- Development: `http://localhost:5062/api`

## Authentication

All endpoints are publicly accessible. Optional API key authentication is available for higher rate limits.

To use API key authentication, include the key in the request header:

```
X-API-Key: your-api-key-here
```

## Rate Limiting

Rate limits are enforced to ensure fair usage:

| Endpoint Type | Limit | Window |
|--------------|-------|--------|
| REST endpoints | 100 requests | 60 seconds |
| SSE connections | 5 connections | 60 seconds |

Rate limit information is included in response headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1676556600
```

When rate limit is exceeded, you'll receive a `429` status with a `Retry-After` header indicating when you can retry.

## Response Format

All endpoints return JSON responses (except SSE stream which uses `text/event-stream`).

### Success Response

```json
{
  "id": 42,
  "created_at": "2026-02-16T14:30:00Z",
  "cycle_number": 42,
  "status": "active",
  "stocks": [...]
}
```

### Error Response

```json
{
  "error": "not_found",
  "message": "Resource not found",
  "status": 404,
  "details": {
    "cycle_id": 999,
    "reason": "No cycle exists with this ID"
  },
  "timestamp": "2026-02-16T14:30:00Z"
}
```

## Error Codes

| Code | Error Type | Description |
|------|-----------|-------------|
| 400 | `bad_request` | Invalid request parameters |
| 404 | `not_found` | Resource not found |
| 429 | `rate_limit_exceeded` | Rate limit exceeded |
| 500 | `internal_error` | Unexpected server error |
| 503 | `service_unavailable` | Service temporarily unavailable |

## Endpoints

### GET /current

Get the current active prediction cycle with all stock predictions.

**Response:** `200 OK`

```json
{
  "id": 42,
  "created_at": "2026-02-16T14:30:00Z",
  "cycle_number": 42,
  "status": "active",
  "stocks": [
    {
      "symbol": "AAPL",
      "current_price": 185.23,
      "predicted_direction": "up",
      "confidence": 0.78,
      "reasoning": "Strong quarterly earnings, new product launch momentum",
      "start_price": 183.50,
      "end_price": null,
      "actual_direction": null,
      "correct": null
    },
    {
      "symbol": "TSLA",
      "current_price": 245.67,
      "predicted_direction": "down",
      "confidence": 0.62,
      "reasoning": "Production concerns, regulatory headwinds",
      "start_price": 247.80,
      "end_price": null,
      "actual_direction": null,
      "correct": null
    }
  ],
  "completed_at": null,
  "accuracy": null
}
```

**Field Descriptions:**

- `id`: Unique cycle identifier
- `created_at`: ISO 8601 timestamp when cycle started
- `cycle_number`: Sequential cycle number
- `status`: `active`, `completed`, or `verified`
- `stocks`: Array of stock predictions
  - `symbol`: Stock ticker (uppercase)
  - `current_price`: Current price in USD
  - `predicted_direction`: `up` or `down`
  - `confidence`: 0-1 confidence score
  - `reasoning`: LLM explanation
  - `start_price`: Price at cycle start
  - `end_price`: Price at cycle end (null if active)
  - `actual_direction`: Actual direction (null until verified)
  - `correct`: Whether prediction was correct (null until verified)
- `completed_at`: When cycle completed (null if active)
- `accuracy`: Cycle accuracy 0-1 (null until verified)

**Errors:**
- `404`: No current cycle found
- `500`: Database error

---

### GET /history

Get paginated list of historical prediction cycles.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number (1-indexed) |
| `limit` | integer | 20 | Results per page (max 100) |
| `status` | string | - | Filter by status: `active`, `completed`, `verified` |
| `sort` | string | `desc` | Sort order: `asc` or `desc` |

**Example Request:**

```
GET /history?page=1&limit=20&status=completed&sort=desc
```

**Response:** `200 OK`

```json
{
  "data": [
    {
      "id": 41,
      "created_at": "2026-02-16T14:20:00Z",
      "cycle_number": 41,
      "status": "completed",
      "stocks": [...],
      "completed_at": "2026-02-16T14:30:00Z",
      "accuracy": 0.80,
      "stock_count": 5
    },
    {
      "id": 40,
      "created_at": "2026-02-16T14:10:00Z",
      "cycle_number": 40,
      "status": "completed",
      "stocks": [...],
      "completed_at": "2026-02-16T14:20:00Z",
      "accuracy": 0.60,
      "stock_count": 5
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 41,
    "total_pages": 3
  }
}
```

**Errors:**
- `400`: Invalid query parameters
- `500`: Database error

---

### GET /stock/{symbol}

Get detailed prediction history for a specific stock.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol` | string | Stock ticker symbol (uppercase, 1-5 letters) |

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cycles` | integer | 10 | Number of recent cycles to include (max 100) |

**Example Request:**

```
GET /stock/AAPL?cycles=10
```

**Response:** `200 OK`

```json
{
  "symbol": "AAPL",
  "current_price": 185.23,
  "accuracy": 0.75,
  "prediction_count": 10,
  "predictions": [
    {
      "cycle_id": 42,
      "cycle_number": 42,
      "created_at": "2026-02-16T14:30:00Z",
      "symbol": "AAPL",
      "current_price": 185.23,
      "predicted_direction": "up",
      "confidence": 0.78,
      "reasoning": "Strong quarterly earnings",
      "start_price": 183.50,
      "end_price": null,
      "actual_direction": null,
      "correct": null
    },
    {
      "cycle_id": 41,
      "cycle_number": 41,
      "created_at": "2026-02-16T14:20:00Z",
      "symbol": "AAPL",
      "current_price": 183.50,
      "predicted_direction": "up",
      "confidence": 0.82,
      "reasoning": "Market momentum positive",
      "start_price": 181.25,
      "end_price": 185.23,
      "actual_direction": "up",
      "correct": true
    }
  ]
}
```

**Errors:**
- `400`: Invalid symbol format
- `404`: Stock symbol not found
- `500`: Database error

---

### GET /stats

Get accuracy statistics and analytics.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeframe` | string | `all` | Time range: `24h`, `7d`, `30d`, `all` |

**Example Request:**

```
GET /stats?timeframe=7d
```

**Response:** `200 OK`

```json
{
  "overall": {
    "total_predictions": 210,
    "correct_predictions": 157,
    "accuracy": 0.748,
    "total_cycles": 42
  },
  "by_provider": {
    "discovery": {
      "provider": "xai",
      "total_discoveries": 42
    },
    "prediction": {
      "provider": "anthropic",
      "total_predictions": 210,
      "correct": 157,
      "accuracy": 0.748
    },
    "synthesis": {
      "provider": "gemini",
      "avg_confidence": 0.72
    }
  },
  "by_direction": {
    "up": {
      "total": 118,
      "correct": 92,
      "accuracy": 0.780
    },
    "down": {
      "total": 92,
      "correct": 65,
      "accuracy": 0.707
    }
  },
  "top_stocks": [
    {
      "symbol": "AAPL",
      "predictions": 10,
      "accuracy": 0.90
    },
    {
      "symbol": "MSFT",
      "predictions": 8,
      "accuracy": 0.875
    }
  ]
}
```

**Field Descriptions:**

- `overall`: Aggregate statistics across all predictions
- `by_provider`: Performance broken down by LLM provider
  - `discovery`: Stock discovery provider (Grok/xAI)
  - `prediction`: Prediction provider (Claude/Anthropic)
  - `synthesis`: Confidence scoring provider (Gemini)
- `by_direction`: Accuracy separated by prediction direction
- `top_stocks`: Best performing stocks (sorted by accuracy)

**Errors:**
- `400`: Invalid timeframe
- `500`: Database error

---

### GET /stream

Server-Sent Events stream for real-time updates.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `event_types` | string | `all` | Comma-separated event types to subscribe to |

**Event Types:**
- `cycle_start`: New prediction cycle started
- `prediction`: New stock prediction made
- `price_update`: Stock price updated
- `cycle_complete`: Prediction cycle completed

**Example Request:**

```
GET /stream?event_types=cycle_start,prediction,price_update
```

**Response:** `200 OK` with `Content-Type: text/event-stream`

```
event: cycle_start
data: {"cycle_id": 43, "cycle_number": 43, "timestamp": "2026-02-16T14:40:00Z"}

event: prediction
data: {"cycle_id": 43, "symbol": "MSFT", "direction": "up", "confidence": 0.82, "reasoning": "Cloud growth accelerating"}

event: price_update
data: {"symbol": "AAPL", "price": 186.45, "change": 0.66, "timestamp": "2026-02-16T14:41:00Z"}

event: cycle_complete
data: {"cycle_id": 42, "accuracy": 0.80, "correct": 4, "total": 5, "timestamp": "2026-02-16T14:35:00Z"}
```

**Client Example (JavaScript):**

```javascript
const eventSource = new EventSource('/api/stream');

eventSource.addEventListener('prediction', (event) => {
  const data = JSON.parse(event.data);
  console.log(`New prediction: ${data.symbol} → ${data.direction} (${data.confidence})`);
});

eventSource.addEventListener('cycle_complete', (event) => {
  const data = JSON.parse(event.data);
  console.log(`Cycle ${data.cycle_id} completed with ${data.accuracy} accuracy`);
});

eventSource.onerror = (error) => {
  console.error('SSE error:', error);
  eventSource.close();
};
```

**Errors:**
- `400`: Invalid event types
- `429`: Too many concurrent connections
- `500`: Stream initialization error

---

### GET /health

Service health check endpoint.

**Response:** `200 OK` (service healthy)

```json
{
  "status": "healthy",
  "service": "foresight",
  "version": "1.0.0",
  "timestamp": "2026-02-16T14:30:00Z",
  "components": {
    "database": "healthy",
    "worker": "healthy",
    "providers": {
      "xai": "healthy",
      "anthropic": "healthy",
      "gemini": "healthy"
    }
  }
}
```

**Response:** `503 Service Unavailable` (service unhealthy)

```json
{
  "status": "unhealthy",
  "service": "foresight",
  "version": "1.0.0",
  "timestamp": "2026-02-16T14:30:00Z",
  "components": {
    "database": "healthy",
    "worker": "degraded",
    "providers": {
      "xai": "unhealthy",
      "anthropic": "healthy",
      "gemini": "healthy"
    }
  }
}
```

**Component Status Values:**
- `healthy`: Component functioning normally
- `degraded`: Component functioning with reduced performance
- `unhealthy`: Component unavailable or failing

---

## Data Models

### Cycle

Represents a complete prediction cycle.

```typescript
interface Cycle {
  id: number;                    // Unique identifier
  created_at: string;            // ISO 8601 timestamp
  cycle_number: number;          // Sequential number
  status: 'active' | 'completed' | 'verified';
  stocks: Prediction[];          // Stock predictions
  completed_at?: string;         // Completion timestamp
  accuracy?: number;             // 0-1 accuracy score
}
```

### Prediction

Represents a single stock prediction.

```typescript
interface Prediction {
  symbol: string;                // Ticker symbol (uppercase)
  current_price: number;         // Current price (USD)
  predicted_direction: 'up' | 'down';
  confidence: number;            // 0-1 confidence score
  reasoning: string;             // LLM explanation
  start_price?: number;          // Price at cycle start
  end_price?: number;            // Price at cycle end
  actual_direction?: 'up' | 'down';
  correct?: boolean;             // Prediction correctness
}
```

### StockDetail

Detailed stock information with history.

```typescript
interface StockDetail {
  symbol: string;                // Ticker symbol
  current_price: number;         // Current price (USD)
  accuracy: number;              // Overall accuracy (0-1)
  prediction_count: number;      // Total predictions
  predictions: PredictionWithCycle[];
}

interface PredictionWithCycle extends Prediction {
  cycle_id: number;              // Cycle identifier
  cycle_number: number;          // Cycle number
  created_at: string;            // Cycle timestamp
}
```

### Statistics

Accuracy statistics and analytics.

```typescript
interface Statistics {
  overall: {
    total_predictions: number;
    correct_predictions: number;
    accuracy: number;            // 0-1
    total_cycles: number;
  };
  by_provider: {
    discovery: ProviderStats;
    prediction: ProviderStats;
    synthesis: ProviderStats;
  };
  by_direction: {
    up: DirectionStats;
    down: DirectionStats;
  };
  top_stocks: StockStats[];
}

interface ProviderStats {
  provider: string;              // Provider name
  total_predictions?: number;
  correct?: number;
  accuracy?: number;             // 0-1
  avg_confidence?: number;       // 0-1
  total_discoveries?: number;    // For discovery provider
}

interface DirectionStats {
  total: number;
  correct: number;
  accuracy: number;              // 0-1
}

interface StockStats {
  symbol: string;
  predictions: number;
  accuracy: number;              // 0-1
}
```

### Pagination

Pagination metadata for list endpoints.

```typescript
interface Pagination {
  page: number;                  // Current page (1-indexed)
  limit: number;                 // Results per page
  total: number;                 // Total results
  total_pages: number;           // Total pages
}
```

### Error

Error response format.

```typescript
interface Error {
  error: string;                 // Error type
  message: string;               // Human-readable message
  status: number;                // HTTP status code
  details?: object;              // Additional details
  timestamp: string;             // ISO 8601 timestamp
}
```

---

## Best Practices

### Polling vs Streaming

For real-time updates, prefer the SSE stream (`/stream`) over polling REST endpoints:

**Recommended:** Use SSE stream
```javascript
const eventSource = new EventSource('/api/stream');
eventSource.addEventListener('prediction', handlePrediction);
```

**Not recommended:** Polling every second
```javascript
// Avoid this - wastes bandwidth and hits rate limits
setInterval(() => fetch('/api/current'), 1000);
```

### Error Handling

Always handle errors gracefully:

```javascript
try {
  const response = await fetch('/api/current');

  if (!response.ok) {
    const error = await response.json();
    console.error(`API Error: ${error.message}`);

    if (error.status === 429) {
      // Rate limited - wait before retry
      const retryAfter = response.headers.get('Retry-After');
      console.log(`Rate limited. Retry after ${retryAfter}s`);
    }
    return;
  }

  const data = await response.json();
  // Handle success
} catch (err) {
  console.error('Network error:', err);
}
```

### Rate Limit Management

Monitor rate limit headers to avoid hitting limits:

```javascript
function checkRateLimit(response) {
  const limit = response.headers.get('X-RateLimit-Limit');
  const remaining = response.headers.get('X-RateLimit-Remaining');
  const reset = response.headers.get('X-RateLimit-Reset');

  console.log(`Rate limit: ${remaining}/${limit} (resets at ${new Date(reset * 1000)})`);

  if (remaining < 10) {
    console.warn('Approaching rate limit!');
  }
}
```

### Pagination

When fetching historical data, use pagination efficiently:

```javascript
async function getAllHistory() {
  let allCycles = [];
  let page = 1;
  let hasMore = true;

  while (hasMore) {
    const response = await fetch(`/api/history?page=${page}&limit=100`);
    const data = await response.json();

    allCycles = allCycles.concat(data.data);
    hasMore = page < data.pagination.total_pages;
    page++;
  }

  return allCycles;
}
```

---

## Examples

### Fetch Current Cycle

```javascript
const response = await fetch('https://dr.eamer.dev/foresight/api/current');
const cycle = await response.json();

console.log(`Cycle #${cycle.cycle_number} - ${cycle.stocks.length} stocks`);
cycle.stocks.forEach(stock => {
  console.log(`${stock.symbol}: ${stock.predicted_direction} (${(stock.confidence * 100).toFixed(0)}%)`);
});
```

### Monitor Live Updates

```javascript
const eventSource = new EventSource('https://dr.eamer.dev/foresight/api/stream');

eventSource.addEventListener('cycle_start', (event) => {
  const data = JSON.parse(event.data);
  console.log(`New cycle started: #${data.cycle_number}`);
});

eventSource.addEventListener('prediction', (event) => {
  const data = JSON.parse(event.data);
  console.log(`Prediction: ${data.symbol} → ${data.direction} (${data.confidence})`);
});
```

### Get Stock Performance

```javascript
const response = await fetch('https://dr.eamer.dev/foresight/api/stock/AAPL?cycles=20');
const stockData = await response.json();

console.log(`${stockData.symbol} overall accuracy: ${(stockData.accuracy * 100).toFixed(1)}%`);
console.log(`Predictions: ${stockData.prediction_count}`);

// Calculate win streak
let currentStreak = 0;
for (const pred of stockData.predictions) {
  if (pred.correct) currentStreak++;
  else break;
}
console.log(`Current win streak: ${currentStreak}`);
```

### View Statistics Dashboard

```javascript
const response = await fetch('https://dr.eamer.dev/foresight/api/stats?timeframe=7d');
const stats = await response.json();

console.log('Last 7 days:');
console.log(`Overall accuracy: ${(stats.overall.accuracy * 100).toFixed(1)}%`);
console.log(`Total predictions: ${stats.overall.total_predictions}`);
console.log(`Correct: ${stats.overall.correct_predictions}`);

console.log('\nTop performers:');
stats.top_stocks.forEach((stock, i) => {
  console.log(`${i+1}. ${stock.symbol}: ${(stock.accuracy * 100).toFixed(1)}% (${stock.predictions} predictions)`);
});
```

---

## OpenAPI Specification

Full OpenAPI 3.0 specification available at: `/openapi.yaml`

Import into tools like Swagger UI, Postman, or Insomnia for interactive documentation and testing.

---

## Support

For issues or questions:
- Email: luke@lukesteuber.com
- GitHub: https://github.com/lukeslp/foresight
- Bluesky: @lukesteuber.com
