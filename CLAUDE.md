# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Foresight is a stock prediction dashboard that uses multiple language models to discover stocks, generate predictions, and track accuracy over time. It operates in continuous prediction cycles, evaluating model performance against actual market outcomes.

## Current Status

- ✅ **Database Integrated**: `ForesightDB` from `db.py` is fully integrated into the Flask app.
- ✅ **Background Worker**: `PredictionWorker` in `app/worker.py` is operational and handles automated cycles.
- ✅ **Services Operational**: `StockService` and `PredictionService` are wired into the worker.
- ✅ **Frontend Functional**: D3.js visualizations (`grid.js`, `detail.js`, `sidebar.js`) are fully implemented and connected to real-time data.
- ✅ **Tests Passing**: Complete test suite (62 tests) is passing.

## Quick Start

```bash
# Development
source venv/bin/activate
export PYTHONPATH=/home/coolhand/shared:$PYTHONPATH
python run.py

# Production (Managed by Service Manager)
sm start foresight-api
sm status
sm logs foresight-api

# Manual Database Initialization
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
│   ├── __init__.py          # Application factory & worker startup
│   ├── config.py            # Environment-based configuration
│   ├── database.py          # Flask integration for ForesightDB
│   ├── errors.py            # Error handlers
│   ├── worker.py            # Background prediction cycle worker
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── main.py          # Dashboard UI routes
│   │   └── api.py           # REST + SSE endpoints
│   └── services/
│       ├── __init__.py
│       ├── stock_service.py     # Stock data fetching (yfinance)
│       └── prediction_service.py # LLM predictions (llm_providers)
├── static/                  # Frontend assets (HTML, CSS, D3.js)
├── db.py                    # Core database implementation (ForesightDB)
├── run.py                   # Entry point
└── start.sh                 # Production startup script
```

### Database Schema

Uses the comprehensive schema in `db.py`:
- **cycles**: Active/completed prediction cycles.
- **stocks**: Global stock registry deduplicated by ticker.
- **prices**: Historical price tracking for accuracy evaluation.
- **predictions**: LLM predictions with confidence and reasoning.
- **accuracy_stats**: Provider performance metrics.
- **events**: SSE event queue for real-time dashboard updates.

SQLite configured with **WAL mode** for concurrent reads during background writes.

### Services Layer

- **StockService**: Fetches current prices and history via `yfinance`.
- **PredictionService**: Discovers stocks (Grok), generates predictions (Claude), and synthesizes confidence (Gemini).

## API Endpoints

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with database and worker status |
| `/api/current` | GET | Current prediction cycle and its predictions |
| `/api/stats` | GET | Accuracy statistics by provider |
| `/api/history` | GET | Historical cycles (paginated) |
| `/api/stock/<symbol>` | GET | Detailed stock history and predictions |
| `/api/cycle/start` | POST | Manually trigger a new cycle |
| `/api/cycle/<id>/stop` | POST | Stop a running cycle |

### SSE Streaming

`GET /api/stream` - Server-Sent Events for real-time updates.
- Events: `connected`, `heartbeat`, `cycle_start`, `prediction`, `price_update`, `cycle_complete`.

## Testing

```bash
# Run all tests
./run_tests.sh all

# Individual categories
./run_tests.sh unit
./run_tests.sh integration
./run_tests.sh api
```

## Reusable Code & Patterns

- **SSE Pattern**: Uses `/home/coolhand/SNIPPETS/streaming-patterns/sse_streaming_responses.py`.
- **LLM Integration**: Uses `/home/coolhand/shared/llm_providers/`.
- **Concurrency**: WAL mode and `busy_timeout` for multi-threaded SQLite access.
