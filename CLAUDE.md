# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Foresight is a stock prediction dashboard that uses multiple language models to discover stocks, generate predictions, and track accuracy over time. It operates in continuous prediction cycles, evaluating model performance against actual market outcomes.

## Commands

```bash
# Development
source venv/bin/activate
export PYTHONPATH=/home/coolhand/shared:$PYTHONPATH
python run.py                    # Development server

# Production
./start.sh                       # Gunicorn with 2 workers, 4 threads

# Service management
sm start foresight / sm stop foresight / sm restart foresight
sm logs foresight

# Database
python -c "from app import create_app; app = create_app(); app.app_context().push(); from app.database import init_db; init_db(app)"
```

**Port**: 5062
**URL**: https://dr.eamer.dev/foresight (when proxied via Caddy)

## Architecture

### Application Factory Pattern

Foresight follows Flask best practices with an application factory:

```
foresight/
├── app/
│   ├── __init__.py          # Application factory
│   ├── config.py            # Environment-based configuration
│   ├── database.py          # SQLite with WAL mode
│   ├── errors.py            # Error handlers
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── main.py          # Dashboard UI routes
│   │   └── api.py           # REST + SSE endpoints
│   └── services/
│       ├── __init__.py
│       ├── stock_service.py     # Stock data fetching
│       └── prediction_service.py # LLM predictions
├── static/                  # Frontend assets
├── run.py                   # Entry point
├── start.sh                 # Production startup
├── app.py                   # DEPRECATED (backward compat)
└── settings.py              # DEPRECATED (backward compat)
```

### Database Schema

SQLite with **WAL mode** enabled for concurrent reads:

- **cycles** - Prediction cycles (start_time, end_time, status)
- **stocks** - Discovered stocks per cycle (symbol, name, price)
- **predictions** - LLM predictions (provider, model, prediction, confidence, reasoning)
- **results** - Actual outcomes (actual_outcome, price_change, was_correct)

Indexes on cycle_id, stock_id, prediction_id for efficient queries.

### Blueprint Structure

| Blueprint | Prefix | Purpose |
|-----------|--------|---------|
| `main_bp` | `/` | Dashboard UI, health check |
| `api_bp` | `/api` | REST endpoints, SSE streaming |

### Services Layer

**StockService** (`app/services/stock_service.py`):
- `fetch_stock_info(symbol)` - Get current stock data via yfinance
- `fetch_historical_data(symbol, days)` - Get price history
- `validate_symbol(symbol)` - Check if symbol exists
- `get_market_status()` - Check if markets are open

**PredictionService** (`app/services/prediction_service.py`):
- `discover_stocks(count)` - Use Grok to find interesting stocks
- `generate_prediction(symbol, data)` - Use Claude for predictions
- `synthesize_confidence(predictions)` - Use Gemini to score predictions

Uses shared library providers via `ProviderFactory.get_provider()`.

## API Endpoints

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with database status |
| `/api/current` | GET | Current prediction cycle data |
| `/api/stats` | GET | Accuracy statistics by provider |
| `/api/history` | GET | Historical cycles (paginated) |
| `/api/stock/<symbol>` | GET | Detailed stock prediction history |
| `/api/cycle/start` | POST | Manually trigger new cycle |
| `/api/cycle/<id>/stop` | POST | Stop running cycle |

### SSE Streaming

`GET /api/stream` - Server-Sent Events endpoint for real-time prediction updates

Event types:
- `connected` - Initial connection
- `heartbeat` - Keep-alive every 30s
- `prediction` - New prediction available (TODO: wire to background worker)

Example event:
```json
{
  "type": "prediction",
  "cycle_id": 1,
  "stock": {"symbol": "AAPL", "name": "Apple Inc."},
  "prediction": {
    "provider": "anthropic",
    "prediction": "bullish",
    "confidence": 0.75,
    "reasoning": "..."
  }
}
```

## Configuration

Environment-based via `app/config.py`:

**DevelopmentConfig**:
- DEBUG = True
- SQLite database in project root

**ProductionConfig**:
- DEBUG = False
- Logging to `foresight.log` with rotation

Key config values:
- `PORT` - Server port (default: 5062)
- `DB_PATH` - SQLite database path
- `CYCLE_INTERVAL` - Seconds between cycles (default: 600)
- `PROVIDERS` - LLM provider mapping (discovery, prediction, synthesis)
- `MAX_STOCKS` - Max stocks per cycle (default: 10)
- `LOOKBACK_DAYS` - Historical data days (default: 30)

## Error Handling

Centralized error handlers in `app/errors.py`:
- 400 Bad Request
- 404 Not Found
- 405 Method Not Allowed
- 500 Internal Server Error
- 503 Service Unavailable
- Generic Exception handler

All errors return JSON:
```json
{
  "error": "Error Type",
  "message": "Human-readable message"
}
```

Database rollback on 500 errors.

## Database Concurrency

SQLite configured with:
- **WAL mode** - Allows concurrent reads while writing
- **busy_timeout=5000ms** - Wait up to 5s for locks
- **check_same_thread=False** - Allow multi-threaded access

Use `get_db()` within request context or `get_db_context()` for background workers.

## Shared Library Integration

Imports from `/home/coolhand/shared/`:

```python
from llm_providers import ProviderFactory
# Available: xai, anthropic, gemini, openai, etc.
```

API keys loaded from:
1. `/home/coolhand/.env` (master)
2. `.env` (local overrides)

## Adding New Endpoints

1. Add route to appropriate blueprint (`app/routes/main.py` or `app/routes/api.py`)
2. Use `from app.database import get_db` for database access
3. Return JSON via `jsonify()` for API endpoints
4. Add error handling (raise HTTPException or catch Exception)
5. Update this documentation

## Adding New Services

1. Create module in `app/services/`
2. Implement as class with static methods or instance methods
3. Import in routes as needed
4. Add tests
5. Document in this file

## TODO

- [ ] Background worker for continuous prediction cycles
- [ ] Queue/channel system for SSE real-time updates
- [ ] Result validation (check predictions against actual outcomes)
- [ ] Provider performance comparison dashboard
- [ ] Export predictions to CSV/JSON
- [ ] Historical accuracy charts
- [ ] Rate limiting on API endpoints
- [ ] Authentication for cycle start/stop endpoints

## Troubleshooting

```bash
# Database locked
# Ensure WAL mode is enabled (it's automatic in init_db)
sqlite3 foresight.db "PRAGMA journal_mode;"  # Should return "wal"

# Import errors from shared library
export PYTHONPATH=/home/coolhand/shared:$PYTHONPATH

# Port already in use
lsof -i :5062
sm stop foresight

# Provider initialization fails
# Check API keys in /home/coolhand/.env
grep "XAI_API_KEY\|ANTHROPIC_API_KEY\|GEMINI_API_KEY" /home/coolhand/.env
```

## Design Decisions

**Why WAL mode?** - Allows concurrent reads during prediction cycles without blocking the web UI.

**Why application factory?** - Enables multiple app instances for testing, easier configuration management.

**Why blueprints?** - Separates concerns (UI vs API), makes code more maintainable.

**Why services layer?** - Keeps business logic separate from routes, makes testing easier.

**Why SSE instead of WebSocket?** - One-way streaming is sufficient, SSE is simpler and works through proxies better.

**Why three LLM providers?** - Different models have different strengths (discovery, prediction, synthesis).
