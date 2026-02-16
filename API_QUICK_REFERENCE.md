# Foresight API Quick Reference

## Base URL
```
Production:  https://dr.eamer.dev/foresight/api
Development: http://localhost:5062/api
```

## Endpoints

| Method | Endpoint | Description | Key Parameters |
|--------|----------|-------------|----------------|
| GET | `/current` | Current prediction cycle | - |
| GET | `/history` | Historical cycles (paginated) | `page`, `limit`, `status`, `sort` |
| GET | `/stock/{symbol}` | Stock detail & history | `symbol` (path), `cycles` (query) |
| GET | `/stats` | Accuracy statistics | `timeframe` (24h/7d/30d/all) |
| GET | `/stream` | SSE real-time updates | `event_types` |
| GET | `/health` | Service health check | - |

## Quick Examples

### Get Current Cycle
```bash
curl https://dr.eamer.dev/foresight/api/current
```

### Get Last 7 Days History
```bash
curl https://dr.eamer.dev/foresight/api/history?page=1&limit=20&sort=desc
```

### Get Stock Detail
```bash
curl https://dr.eamer.dev/foresight/api/stock/AAPL?cycles=10
```

### Get Statistics
```bash
curl https://dr.eamer.dev/foresight/api/stats?timeframe=7d
```

### Monitor Live Updates
```javascript
const eventSource = new EventSource('https://dr.eamer.dev/foresight/api/stream');
eventSource.addEventListener('prediction', (e) => {
  const data = JSON.parse(e.data);
  console.log(`${data.symbol} → ${data.direction} (${data.confidence})`);
});
```

## Response Codes

| Code | Meaning | Common Cause |
|------|---------|--------------|
| 200 | OK | Success |
| 400 | Bad Request | Invalid parameters |
| 404 | Not Found | Resource doesn't exist |
| 429 | Rate Limit Exceeded | Too many requests |
| 500 | Internal Error | Server error |
| 503 | Service Unavailable | Service unhealthy |

## Rate Limits

- **REST:** 100 requests / 60 seconds
- **SSE:** 5 connections / 60 seconds

Headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1676556600
```

## Error Format

```json
{
  "error": "not_found",
  "message": "Resource not found",
  "status": 404,
  "details": { "cycle_id": 999 },
  "timestamp": "2026-02-16T14:30:00Z"
}
```

## Data Models

### Cycle
```typescript
{
  id: number;
  created_at: string;        // ISO 8601
  cycle_number: number;
  status: "active" | "completed" | "verified";
  stocks: Prediction[];
  completed_at?: string;
  accuracy?: number;         // 0-1
}
```

### Prediction
```typescript
{
  symbol: string;            // Uppercase ticker
  current_price: number;
  predicted_direction: "up" | "down";
  confidence: number;        // 0-1
  reasoning: string;
  start_price?: number;
  end_price?: number;
  actual_direction?: "up" | "down";
  correct?: boolean;
}
```

## SSE Event Types

| Event | Data | When |
|-------|------|------|
| `cycle_start` | `{cycle_id, cycle_number, timestamp}` | New cycle begins |
| `prediction` | `{cycle_id, symbol, direction, confidence}` | Prediction made |
| `price_update` | `{symbol, price, change, timestamp}` | Price changes |
| `cycle_complete` | `{cycle_id, accuracy, timestamp}` | Cycle finishes |

## Authentication (Optional)

```bash
curl -H "X-API-Key: your-api-key-here" https://dr.eamer.dev/foresight/api/current
```

## Full Documentation

- **OpenAPI Spec:** `/home/coolhand/projects/foresight/openapi.yaml`
- **Developer Guide:** `/home/coolhand/projects/foresight/docs/API.md`
- **HTML Docs:** `/home/coolhand/docs/geepers/api-foresight.html`
- **Architecture:** `/home/coolhand/geepers/reports/by-date/2026-02-16/api-foresight.md`

## Implementation Status

- ✅ API Design Complete
- ✅ OpenAPI Specification
- ✅ Documentation
- ⏳ Database Module (pending)
- ⏳ Endpoint Implementation (pending)
- ⏳ SSE Streaming (pending)
- ⏳ Worker Process (pending)

## Tools

**Validate OpenAPI:**
```bash
swagger-cli validate openapi.yaml
```

**Generate Client:**
```bash
openapi-generator-cli generate -i openapi.yaml -g typescript-fetch
```

**Test Endpoint:**
```bash
curl -X GET http://localhost:5062/api/health
```

**Monitor SSE:**
```bash
curl -N http://localhost:5062/api/stream
```
