# Foresight API Design Summary

**Date:** 2026-02-16
**Status:** Design Complete, Implementation Pending

## Deliverables

### 1. OpenAPI Specification
**Location:** `/home/coolhand/projects/foresight/openapi.yaml`

Complete OpenAPI 3.0.3 specification with:
- 6 endpoint definitions (GET /current, /history, /stock/{symbol}, /stats, /stream, /health)
- Request/response schemas for all endpoints
- Parameter validation rules
- Error response definitions
- Rate limiting documentation
- Security scheme (optional API key)

Can be imported into Swagger UI, Postman, Insomnia, or used to generate client SDKs.

### 2. Developer Documentation
**Location:** `/home/coolhand/projects/foresight/docs/API.md`

Comprehensive Markdown documentation with:
- Endpoint descriptions with examples
- Query parameter references
- TypeScript data model definitions
- JavaScript code examples
- Best practices (polling vs streaming)
- Error handling patterns
- Pagination strategies

### 3. HTML Documentation
**Location:** `/home/coolhand/docs/geepers/api-foresight.html`

Clean, professional HTML documentation with:
- Table of contents
- Endpoint reference
- Data model tables
- Error code reference
- Responsive design for mobile/desktop
- Swiss Design aesthetic (geometric, minimal)

### 4. Architecture Report
**Location:** `/home/coolhand/geepers/reports/by-date/2026-02-16/api-foresight.md`

Detailed report covering:
- Design decisions and rationale
- REST compliance checklist
- Security considerations
- Implementation recommendations
- Agent coordination strategy
- Success metrics

### 5. Project Recommendations
**Location:** `/home/coolhand/geepers/recommendations/by-project/foresight.md`

Prioritized action items:
- Critical: Implement database module
- High: Core API endpoints, validation, rate limiting
- Medium: SSE streaming, worker process
- Code patterns and examples
- Security checklist

## API Endpoints

### 1. GET /api/current
Current active prediction cycle with stock predictions.

**Returns:**
- Cycle ID, number, status
- Array of stock predictions (symbol, price, direction, confidence, reasoning)
- Null for incomplete fields (end_price, actual_direction, correct)

### 2. GET /api/history
Paginated historical cycles.

**Query Parameters:**
- `page` (1-indexed)
- `limit` (max 100)
- `status` (active/completed/verified)
- `sort` (asc/desc)

**Returns:**
- Data array with cycles
- Pagination metadata (page, limit, total, total_pages)

### 3. GET /api/stock/{symbol}
Detailed stock prediction history.

**Path Parameters:**
- `symbol` - Stock ticker (uppercase, 1-5 letters)

**Query Parameters:**
- `cycles` - Number of recent cycles (max 100)

**Returns:**
- Stock symbol, current price
- Overall accuracy for this stock
- Prediction count
- Array of historical predictions with cycle info

### 4. GET /api/stats
Accuracy statistics and analytics.

**Query Parameters:**
- `timeframe` (24h/7d/30d/all)

**Returns:**
- Overall stats (total, correct, accuracy, cycles)
- By provider (discovery/prediction/synthesis)
- By direction (up/down accuracy)
- Top performing stocks

### 5. GET /api/stream
Server-Sent Events for real-time updates.

**Query Parameters:**
- `event_types` - Comma-separated list to subscribe

**Event Types:**
- `cycle_start` - New cycle started
- `prediction` - New prediction made
- `price_update` - Stock price updated
- `cycle_complete` - Cycle finished

**Returns:** text/event-stream with JSON data payloads

### 6. GET /api/health
Service health monitoring.

**Returns:**
- Overall status (healthy/degraded/unhealthy)
- Service name and version
- Component status (database, worker, providers)
- HTTP 200 if healthy, 503 if unhealthy

## Design Highlights

### REST Compliance
✅ Resource-based URLs (nouns, not verbs)
✅ Proper HTTP methods (GET for read operations)
✅ Consistent naming (kebab-case URLs, snake_case JSON)
✅ Standard status codes (200, 400, 404, 429, 500, 503)
✅ Pagination for collections
✅ Filtering and sorting support

### Response Format
All responses use consistent JSON structure with:
- Direct resource return (no wrapper objects)
- Pagination metadata for lists
- Error objects with error code, message, details, timestamp
- ISO 8601 timestamps
- Null for optional/incomplete fields

### Security
- Optional API key authentication (X-API-Key header)
- Rate limiting: 100 req/min (REST), 5 conn/min (SSE)
- Input validation with regex patterns
- CORS configuration for dr.eamer.dev
- No sensitive data in URLs
- Parameterized queries (SQL injection prevention)

### Documentation
- Complete OpenAPI 3.0.3 spec
- Markdown developer guide with examples
- Clean HTML reference documentation
- TypeScript type definitions
- JavaScript code examples

## Implementation Roadmap

### Phase 1: Database Foundation (Critical)
1. Create database schema (cycles, predictions, stocks tables)
2. Implement database module with connection pooling
3. Add indexes for performance
4. Write database functions (get_current_cycle, get_history, etc.)

### Phase 2: Core API (High Priority)
1. Implement /api/current endpoint
2. Implement /api/history with pagination
3. Implement /api/stats endpoint
4. Add input validation (Marshmallow schemas)
5. Add centralized error handlers

### Phase 3: Rate Limiting & Security (High Priority)
1. Add Flask-Limiter
2. Configure rate limits (100/min REST, 5/min SSE)
3. Implement API key authentication (optional)
4. Configure CORS
5. Add request logging

### Phase 4: Detail Endpoints (Medium Priority)
1. Implement /api/stock/{symbol}
2. Add query parameter filtering
3. Optimize database queries with joins

### Phase 5: Real-time Streaming (Medium Priority)
1. Implement /api/stream with SSE
2. Set up event queue/pub-sub
3. Connect to worker process events
4. Manage connection lifecycle

### Phase 6: Worker Integration (Medium Priority)
1. Create background worker process
2. Implement prediction cycle logic
3. Call LLM agents (Grok, Claude, Gemini)
4. Update database with results
5. Trigger SSE events

### Phase 7: Production Deployment (Final)
1. Add to service_manager.py
2. Configure Caddy routing
3. Set up monitoring and logging
4. Load testing and optimization
5. Documentation deployment

## Testing Strategy

### Unit Tests
- Database functions (CRUD operations)
- Validation schemas (valid/invalid inputs)
- Error handlers (correct status codes)
- Utility functions

### Integration Tests
- Full endpoint flows (request → database → response)
- Pagination edge cases (empty, first page, last page)
- Rate limiting behavior (within limits, exceeded)
- Error scenarios (404, 400, 500)

### Load Tests
- Concurrent requests (target: 100 req/sec)
- SSE connection stability (target: 100+ concurrent)
- Database query performance (target: <50ms)
- Rate limit enforcement

### Security Tests
- Input validation (SQL injection, XSS)
- CORS headers
- Rate limit bypass attempts
- API key authentication

## Success Metrics

Once deployed, track:
- **Performance:** API response times (<100ms target for non-streaming)
- **Reliability:** Error rate (<1% target)
- **Usage:** Requests per endpoint, popular query parameters
- **SSE:** Connection count, event throughput, connection duration
- **Business:** Prediction accuracy by provider, top stocks, user engagement

## Integration Points

### Database Module (db.py)
All endpoints depend on database access. Must implement first.

### Worker Process (worker.py)
Runs prediction cycles, updates database, triggers SSE events.

### LLM Agents (agents.py)
Called by worker to generate predictions. API only consumes results.

### Price Fetcher (price_fetcher.py)
Background price updates, triggers SSE price_update events.

### Service Manager
Add foresight to `~/service_manager.py` for process management.

### Caddy
Configure reverse proxy at `/foresight/` in `/etc/caddy/Caddyfile`.

## File Reference

**Project Files:**
- `/home/coolhand/projects/foresight/openapi.yaml` - OpenAPI spec
- `/home/coolhand/projects/foresight/docs/API.md` - Developer docs
- `/home/coolhand/projects/foresight/app.py` - Flask server (stub)
- `/home/coolhand/projects/foresight/settings.py` - Configuration

**Geepers Output:**
- `/home/coolhand/geepers/reports/by-date/2026-02-16/api-foresight.md` - Architecture report
- `/home/coolhand/geepers/recommendations/by-project/foresight.md` - Implementation roadmap
- `/home/coolhand/docs/geepers/api-foresight.html` - HTML documentation

**To Create:**
- `db.py` - Database module
- `models.py` - Data models (Cycle, Prediction, etc.)
- `validation.py` - Marshmallow schemas
- `worker.py` - Background prediction worker
- `agents.py` - LLM agent integration
- `price_fetcher.py` - Stock price fetching
- `tests/` - Test suite

## Next Steps

1. **Review this summary** and the three main deliverables (openapi.yaml, docs/API.md, report)
2. **Implement database module** following the schema in the OpenAPI spec
3. **Build core endpoints** (/current, /history, /stats) using the patterns in the report
4. **Add validation and error handling** for production readiness
5. **Deploy to service manager** and configure Caddy routing

## References

**Existing Patterns:**
- Flask SSE: `~/servers/swarm/`, `~/servers/lessonplanner/`
- Service Manager: `~/service_manager.py`
- Caddy Config: `/etc/caddy/Caddyfile`
- Shared Utilities: `~/shared/web/sse_helpers.py`

**Tools:**
- OpenAPI validation: `swagger-cli validate openapi.yaml`
- API testing: Postman, Insomnia, curl
- Load testing: Apache Bench, wrk, locust
- Documentation: Swagger UI, Redoc

---

**Design completed by:** API Architect Agent
**Date:** 2026-02-16
**Ready for implementation:** Yes
