# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Foresight is a stock prediction dashboard. A background worker runs continuous prediction cycles where 8 language model providers debate as a weighted democracy — no fixed roles. All providers participate in every phase (discovery, analysis, synthesis). Premium tier (Claude/ChatGPT/Gemini) carry 1.5× weight, xai 1.1×, others lower. Accuracy is tracked over time.

**Port**: 5062 | **URL**: https://dr.eamer.dev/foresight

## Quick Start

```bash
source venv/bin/activate
# llm_providers is bundled in the repo — no external shared library needed
python run.py
```

**Production** (service manager):
```bash
sm start foresight-api
sm logs foresight-api
```

## Architecture

### Prediction Cycle Flow

The `PredictionWorker` (`app/worker.py`) runs in a background daemon thread:

1. **Phase 1 — Discovery**: `PredictionService.discover_stocks_debate()` runs a provider swarm and returns weighted ticker candidates
2. **Phase 2 — Validation**: Each symbol is validated via yfinance; invalid or unfetchable symbols are dropped
3. **Phase 3 — Multi-Agent Debate**: For each stock, each provider runs sub-agent analysis via `generate_prediction_swarm()`
4. **Phase 4 — Voting + Synthesis**: Weighted council vote plus weighted multi-provider synthesis via `synthesize_council_swarm()`

### LLM Provider Council (Weighted Democracy)

All 8 providers participate in every phase. No fixed roles. Weights are adjustable via env vars.

| Provider | Tier | Default Weight | Override Env Var |
|----------|------|---------------|-----------------|
| `anthropic` | premium | 1.5 | `PROVIDER_WEIGHT_ANTHROPIC` |
| `openai` | premium | 1.5 | `PROVIDER_WEIGHT_OPENAI` |
| `gemini` | premium | 1.5 | `PROVIDER_WEIGHT_GEMINI` |
| `xai` | mid | 1.1 | `PROVIDER_WEIGHT_XAI` |
| `perplexity` | standard | 0.9 | `PROVIDER_WEIGHT_PERPLEXITY` |
| `huggingface` | standard | 0.85 | `PROVIDER_WEIGHT_HUGGINGFACE` |
| `mistral` | standard | 0.8 | `PROVIDER_WEIGHT_MISTRAL` |
| `cohere` | standard | 0.6 | `PROVIDER_WEIGHT_COHERE` |

Provider call order: `PROVIDER_ORDER` env var (default: `anthropic,openai,gemini,xai,...`).
Overnight light mode uses premium tier by default: `OVERNIGHT_LIGHT_PROVIDER_ORDER=anthropic,openai,gemini`.

**Critical**: All providers use `provider.complete(messages=[Message(...)])` from the bundled `llm_providers/` package. Never call `provider.generate()` — it does not exist.

### Key Configuration

```python
CYCLE_INTERVAL = 30   # seconds — set to 600 for production
MAX_STOCKS = 10       # stocks discovered per cycle
LOOKBACK_DAYS = 30    # yfinance history window
```

Required env vars: `XAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`.

### Database Schema (`db.py`)

`ForesightDB` manages SQLite with WAL mode. Key tables:
- `cycles` — status: `active` | `completed` | `failed`
- `stocks` — deduplicated by `ticker` (UNIQUE COLLATE NOCASE)
- `prices` — snapshots per stock per cycle
- `predictions` — per-provider predictions; consensus stored as `{provider}-consensus`
- `events` — SSE event queue (auto-populated by `db.create_cycle()`, `db.complete_cycle()`, etc.)
- `accuracy_stats` — provider accuracy aggregates

Events are emitted automatically by DB methods — do not duplicate by calling them from the worker.

### SSE Streaming

`GET /api/stream` — the generator must run inside `with app.app_context():`. Omitting this causes `RuntimeError: Working outside of application context`. See `app/routes/api.py` for the implementation pattern.

## Testing

```bash
./run_tests.sh all                    # All tests
./run_tests.sh unit                   # Unit tests only
./run_tests.sh integration            # Integration tests only
./run_tests.sh api                    # API endpoint tests
./run_tests.sh db                     # DB tests (also runs test_db.py)
./run_tests.sh coverage               # HTML coverage report → htmlcov/
./run_tests.sh file tests/test_foo.py # Single file

# Direct pytest (same venv + PYTHONPATH required)
pytest tests/test_services.py::TestPredictionService::test_discover_stocks -v
pytest -m "not slow" -v
```

Test fixtures (in `tests/conftest.py`):
- `db` — fresh `ForesightDB` with temp file, tables cleared before/after each test
- `mock_provider` — Mock with `.complete()` returning UP/0.75 JSON
- `mock_provider_factory` — monkeypatches `ProviderFactory.get_provider`
- `mock_yfinance` — monkeypatches `app.services.stock_service.yf`
- `sample_cycle`, `sample_stock`, `sample_prediction` — pre-populated DB records

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Worker + database status |
| `/api/current` | GET | Current cycle + predictions |
| `/api/stats` | GET | Provider leaderboard + accuracy |
| `/api/history` | GET | Historical cycles (paginated) |
| `/api/stock/<symbol>` | GET | Stock detail + prediction history |
| `/api/cycle/start` | POST | Manually trigger a new cycle |
| `/api/cycle/<id>/stop` | POST | Stop a running cycle |
| `/api/stream` | GET | SSE event stream |

## Known Issues

- **Duplicate `except` block** in `worker.py:_process_stock()` — lines 325–328 shadow 309–311 with an identical handler; dead code.
- The worker thread is disabled in `TESTING` mode — do not rely on it in integration tests; trigger cycles manually if needed.

## Reusable Patterns

- **LLM calls**: `provider.complete(messages=[Message(role='user', content=prompt)])` — response is a `CompletionResponse` with `.content` str
- **JSON from LLM**: strip markdown code fences before `json.loads()` (see `generate_prediction()` regex pattern)
- **Prediction windows**: Crypto = 2.5h, Equities during market = 30min, Equities after hours = 2.5h (see `worker.py` target_time logic)
