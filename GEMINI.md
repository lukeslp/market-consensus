# Foresight - Stock Prediction Dashboard

Real-time stock prediction dashboard utilizing multi-provider LLM agents (Grok, Claude, Gemini) to discover stocks, generate predictions, and track accuracy against actual market data.

## Project Overview

- **Purpose**: Autonomous stock analysis and prediction with real-time performance tracking.
- **Backend**: Flask application using the Application Factory pattern.
- **Database**: SQLite with Write-Ahead Logging (WAL) enabled for high concurrency.
- **Frontend**: Glassmorphic dark-themed UI using D3.js for visualizations and Server-Sent Events (SSE) for real-time updates.
- **Agent Orchestration**:
  - **Discovery**: Grok (xAI) identifies trending/interesting stocks.
  - **Prediction**: Claude (Anthropic) generates technical analysis and direction.
  - **Synthesis**: Gemini (Google) synthesizes multiple predictions into a confidence score.
- **Shared Library**: Relies on `~/shared/` for LLM provider abstractions (`llm_providers`).

## Building and Running

### Environment Setup
```bash
source venv/bin/activate
export PYTHONPATH=/home/coolhand/shared:$PYTHONPATH
pip install -r requirements.txt
```

### Development Server
```bash
python run.py
```
Default Port: **5062**

### Production Server
```bash
./start.sh
```
Uses Gunicorn with 2 workers and 4 threads.

### Service Management
```bash
sm start foresight
sm status
sm logs foresight
```

### Testing
```bash
# Database tests
python test_db.py

# Full test suite
./run_tests.sh
```

## Key Files & Directories

- `run.py`: Main entry point for the Flask application.
- `db.py`: Core database module containing the `ForesightDB` class (comprehensive CRUD).
- `app/`:
  - `worker.py`: Background thread handling the prediction cycle (Discovery -> Prediction -> Evaluation).
  - `routes/api.py`: REST API and SSE streaming endpoints.
  - `services/`: Logic for stock data (`stock_service.py`) and LLM interactions (`prediction_service.py`).
- `static/`: Frontend assets (HTML, CSS, JS).
- `CLAUDE.md`: Detailed developer guide, roadmap, and critical known issues.
- `DATABASE.md`: Detailed schema and database API reference.

## Development Conventions

- **Database**: Use the `ForesightDB` class from `db.py` rather than raw SQLite connections. Always use `get_db()` within Flask contexts.
- **Real-time Updates**: Prefer SSE via `/api/stream` for UI updates. Events are queued in the `events` table.
- **Async Logic**: Long-running prediction tasks should be handled by the background `PredictionWorker` in `app/worker.py`.
- **Shared Utilities**: Check `/home/coolhand/shared/` before implementing core infrastructure (LLMs, data fetching, SSE helpers).
- **Environment Variables**: API keys and configuration are loaded from `/home/coolhand/.env` and a local `.env` file.

## Implementation Status (Current: 2026-02-16)

- **Database**: Fully integrated using the `ForesightDB` class from `db.py`. Concurrency issues resolved with WAL mode and proper thread handling.
- **Worker**: Background `PredictionWorker` is fully operational and wired into the API. It handles autonomous prediction cycles (Discovery -> Prediction -> Evaluation).
- **API**: REST endpoints and SSE streaming are fully implemented and verified with tests.
- **Frontend**: D3.js visualizations in `static/js/grid.js`, `detail.js`, and `sidebar.js` are fully functional and connected to the real-time SSE stream.
- **Testing**: Complete test suite (62 tests) is passing, covering unit, integration, and API layers.

## Remaining Work

- **LLM Real-world Validation**: Continue monitoring performance with actual LLM API calls (Grok is currently the primary provider).
- **Provider Diversification**: Transition to using Claude for predictions and Gemini for synthesis as originally planned (currently using Grok for all roles as a stable baseline).
- **Historical Data Backfill**: Improve price history backfilling for newly discovered stocks to enable immediate accuracy tracking.
