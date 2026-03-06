# Consensus

![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)
![Flask](https://img.shields.io/badge/flask-3.0%2B-lightgrey?style=flat-square)
![D3.js](https://img.shields.io/badge/d3.js-v7-orange?style=flat-square)
![SQLite](https://img.shields.io/badge/sqlite-WAL-lightblue?style=flat-square)
![SSE](https://img.shields.io/badge/streaming-SSE-purple?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
[![Live](https://img.shields.io/badge/live-dr.eamer.dev%2Fconsensus-amber?style=flat-square)](https://dr.eamer.dev/consensus/)

### UNFINISHED EXPERIMENT 

A LLM stock market prediction board that runs a staged multi-provider swarm debate on a configurable cycle. Providers debate at discovery, analysis, council voting, and synthesis. Accuracy is measured against actual closing prices and tracked indefinitely.

<img width="2616" height="1604" alt="CleanShot 2026-03-06 at 11 44 08@2x" src="https://github.com/user-attachments/assets/9fc6288f-f3c1-4c82-a4cf-fe80acf67698" />

---

## Features

- **Democratic provider swarm** — providers participate in `core` (xAI, Gemini), `join` (Anthropic, OpenAI, Perplexity), and `side` (Mistral, Cohere, HuggingFace/Llama) stages
- **Sub-agent analysis** — each provider can run internal specialist sub-agents, then emit a provider-level vote with reasoning
- **Council + synthesis voting** — weighted democratic votes happen twice: analyst council vote and final synthesis vote across all providers
- **Continuous cycles** — a background daemon thread runs prediction cycles on a configurable interval; each cycle discovers equities, optionally adds configured crypto symbols, fetches live prices via yfinance, and logs everything to SQLite
- **Accuracy tracking** — predictions are evaluated against actual prices after the target window (30 min during market hours, 2.5h after hours/crypto); per-provider accuracy stats accumulate over time
- **Real-time dashboard** — D3.js v7 visualizations stream live events over SSE; no page refresh needed to watch a cycle run
- **Oracle Terminal aesthetic** — Cinzel display font, JetBrains Mono for data, amber accent on near-black
- **Persistent SQLite store** — WAL mode for concurrent reads during background writes; six normalized tables; no external database required

---

## Quick Start

```bash
# Clone and set up
git clone https://github.com/lukeslp/consensus.git
cd consensus
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set API keys (or source from a file)
export XAI_API_KEY=your_xai_key
export ANTHROPIC_API_KEY=your_anthropic_key
export GEMINI_API_KEY=your_gemini_key
export MISTRAL_API_KEY=your_mistral_key
export PERPLEXITY_API_KEY=your_perplexity_key
export COHERE_API_KEY=your_cohere_key
export OPENAI_API_KEY=your_openai_key
# Optional: export HUGGINGFACE_API_KEY=your_hf_key

# Run (llm_providers is bundled in the repo)
python run.py
```

Open http://localhost:5062 in a browser.

### Production (service manager)

```bash
sm start consensus-api
sm status
sm logs consensus-api
```

---

## Configuration

All settings are environment variables with sensible defaults.

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | `5062` | Server port |
| `DB_PATH` | `consensus.db` | SQLite database file |
| `MARKET_TIMEZONE` | `America/New_York` | Market schedule timezone |
| `USE_NYSE_CALENDAR` | `true` | Enable NYSE trading-day logic (holidays + early closes) |
| `MARKET_OPEN_INTERVAL_SECONDS` | `1800` | Run cadence while market is open (30 minutes) |
| `NYSE_EARLY_CLOSE_HOUR` | `13` | Early-close hour (ET) for supported NYSE half-days |
| `NYSE_EARLY_CLOSE_MINUTE` | `00` | Early-close minute (ET) |
| `OVERNIGHT_CHECK_TIMES` | `20:00,06:00` | Two overnight refresh runs before next open |
| `OVERNIGHT_LOOKAHEAD_HOURS` | `18` | Only run overnight checks when next open is close enough |
| `SCHEDULE_POLL_SECONDS` | `20` | Worker polling granularity for scheduled runs |
| `OVERNIGHT_LIGHT_MODE` | `true` | Use cheaper/light provider set for overnight runs |
| `OVERNIGHT_FULL_DEBATE_EVERY` | `3` | Force one full all-provider overnight run every N overnight cycles |
| `OVERNIGHT_LIGHT_PROVIDER_ORDER` | `xai,perplexity,mistral` | Provider order for light overnight cycles |
| `CYCLE_INTERVAL` | `1800` | Legacy compatibility var; used as fallback for market-open cadence |
| `MAX_STOCKS` | `10` | Stocks to discover per cycle |
| `LOOKBACK_DAYS` | `30` | Historical price window sent to each analyst |
| `INCLUDE_CRYPTO` | `true` | Include configured crypto symbols in each cycle |
| `MAX_CRYPTO_SYMBOLS` | `3` | Cap on configured crypto symbols per cycle |
| `CRYPTO_SYMBOLS` | `BTC-USD,ETH-USD,SOL-USD` | Comma-separated crypto tickers (yfinance format) |
| `DISCOVERY_PROVIDER` | `mistral` | Preferred default provider for non-swarm discovery fallback |
| `PREDICTION_PROVIDER` | `anthropic` | Preferred default provider for non-swarm prediction fallback |
| `SYNTHESIS_PROVIDER` | `gemini` | Preferred default provider for non-swarm confidence synthesis fallback |

Model overrides (set in `app/config.py`):

| Provider | Default model |
|----------|--------------|
| xai | `grok-4-1-fast-reasoning` |
| anthropic | `claude-sonnet-4-6-20250514` |
| gemini | `gemini-3.5-flash` |
| openai | `gpt-5.4` |
| mistral | `mistral-small-latest` |
| perplexity | `sonar` |
| cohere | `command-r-08-2024` |
| huggingface | `meta-llama/Llama-3.3-70B-Instruct` |

---

## Scheduler Behavior

- During market hours (default `09:30-16:00` ET), the worker runs a new cycle every 30 minutes.
- During closed hours, the worker runs two low-frequency refresh cycles (`20:00` and `06:00` ET by default) to refresh news/catalyst context before the next open.
- Overnight runs use a lighter provider order by default, with periodic full-debate refresh cycles so top agents are still used regularly.
- Weekend behavior follows the same logic and naturally schedules pre-open refreshes for Monday (for example, Sunday evening + Monday early morning).
- NYSE holiday and early-close session logic is applied to scheduling (for example, New Year holiday closure and Black Friday early close).
- If `pandas_market_calendars` is available, it is used for exchange-exact session windows; otherwise built-in NYSE rules are used.

---

## Prediction Cycle

Each cycle runs through four democratic phases in sequence.

### Phase 1 — Discovery

Providers vote on discovery candidates by stage (`core`, `join`, `side`), and each provider can run internal discovery sub-agents. The system combines results into a weighted symbol shortlist, then appends configured crypto symbols (if enabled).

### Phase 2 — Validation

Each symbol is validated via yfinance. Symbols that cannot be fetched, return no price history, or are otherwise malformed are silently dropped. Valid symbols are written to the `stocks` table and their current prices are recorded in `prices`.

### Phase 3 — Multi-Model Debate

For each surviving symbol, providers are called by stage:

| Stage | Providers | Role |
|------|-----------|------|
| Core | xAI, Gemini | fast low-cost first-pass analysis |
| Join | Anthropic, OpenAI, Perplexity | deep reasoning and grounded context |
| Side | Mistral, Cohere, HuggingFace (Llama) | additional diversity and dissent |

Each analyst receives the ticker symbol, current price, and the last 10 closing prices. Each returns a JSON object with `prediction` (UP/DOWN/NEUTRAL), `confidence` (0.0–1.0), and `reasoning`.

All analyst reports that run in that cycle are stored individually in the `predictions` table.

### Phase 4 — Democratic Synthesis

All providers cast final synthesis votes using the full debate transcript. Those votes are weighted and persisted as `*-synthesis`, then aggregated into `council-swarm-consensus`.

The cycle is then marked `completed` and a `cycle_complete` SSE event is broadcast to all connected clients.

---

## Architecture

```
consensus/
├── llm_providers/               # Bundled LLM provider library (self-contained)
│   ├── __init__.py              # Message, CompletionResponse, ProviderFactory
│   ├── factory.py               # Provider registry and initialization
│   ├── anthropic_provider.py    # Anthropic (Claude)
│   ├── openai_provider.py       # OpenAI (GPT-4o)
│   ├── gemini_provider.py       # Google Gemini
│   ├── xai_provider.py          # xAI (Grok)
│   ├── perplexity_provider.py   # Perplexity (Sonar)
│   ├── mistral_provider.py      # Mistral
│   ├── cohere_provider.py       # Cohere (Command)
│   └── huggingface_provider.py  # HuggingFace (Llama)
├── app/
│   ├── __init__.py              # Application factory, worker startup
│   ├── config.py                # Environment-based configuration
│   ├── database.py              # Flask integration for ConsensusDB
│   ├── errors.py                # Error handlers
│   ├── worker.py                # PredictionWorker daemon thread
│   ├── routes/
│   │   ├── main.py              # Dashboard UI route
│   │   └── api.py               # REST + SSE endpoints
│   └── services/
│       ├── stock_service.py     # yfinance price fetching and validation
│       └── prediction_service.py  # LLM prediction and debate orchestration
├── static/
│   ├── index.html               # Dashboard shell
│   ├── css/                     # Terminal aesthetic styles
│   └── js/
│       ├── app.js               # Entry point — SSE, routing, button wiring
│       ├── grid.js              # 50-tile stock grid (D3 enter/update/exit)
│       ├── detail.js            # Stock detail price chart
│       ├── sidebar.js           # Provider accuracy leaderboard (D3 SVG)
│       └── api.js               # REST client (loaded, available for extension)
├── db.py                        # ConsensusDB — SQLite with WAL mode
├── run.py                       # Entry point
└── start.sh                     # Production startup script
```

### Database Schema

Six tables managed by `ConsensusDB` in `db.py`:

| Table | Purpose |
|-------|---------|
| `cycles` | One row per prediction cycle; status: `active`, `completed`, `failed` |
| `stocks` | Global ticker registry, deduplicated (`UNIQUE COLLATE NOCASE`) |
| `prices` | Price snapshots per stock per cycle, used for accuracy evaluation |
| `predictions` | Per-provider directional predictions, per-provider synthesis votes (`*-synthesis`), and final consensus rows (`*-consensus`) |
| `accuracy_stats` | Aggregate win/loss counts and accuracy ratios per provider |
| `events` | SSE event queue; populated automatically by DB write methods |

SSE events are emitted by the database layer, not by the worker — `create_cycle`, `complete_cycle`, `add_stock`, and `add_prediction` each emit their corresponding event automatically.

### SSE Streaming

`GET /api/stream` — long-lived connection, one event per database write.

Event types: `connected`, `heartbeat`, `cycle_start`, `cycle_complete`, `prediction`, `price_update`.

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Worker status, database status, cycle count |
| `/api/current` | GET | Active cycle and its predictions |
| `/api/stats` | GET | Per-provider accuracy leaderboard |
| `/api/history` | GET | Historical cycles, paginated |
| `/api/stock/<symbol>` | GET | Full prediction history for a ticker |
| `/api/cycle/start` | POST | Manually trigger a new cycle |
| `/api/cycle/<id>/stop` | POST | Stop a running cycle |
| `/api/stream` | GET | SSE event stream |

---

## Tests

```bash
# All tests
./run_tests.sh all

# By category
./run_tests.sh unit
./run_tests.sh integration
./run_tests.sh api
./run_tests.sh db

# Coverage report (HTML output to htmlcov/)
./run_tests.sh coverage

# Single file
./run_tests.sh file tests/test_services.py
```

The test suite covers the database layer, both services, all API endpoints, and end-to-end cycle execution. The background worker is disabled in `TESTING` mode; integration tests trigger cycles manually via the API.

Key fixtures in `tests/conftest.py`:

| Fixture | Purpose |
|---------|---------|
| `db` | Fresh `ConsensusDB` with temp file, reset before each test |
| `mock_provider` | Mock with `.complete()` returning a canned UP/0.75 JSON response |
| `mock_provider_factory` | Monkeypatches `ProviderFactory.get_provider` |
| `mock_yfinance` | Monkeypatches `app.services.stock_service.yf` |
| `sample_cycle` / `sample_stock` / `sample_prediction` | Pre-populated DB records |

---

## Author

Luke Steuber
- Web: [dr.eamer.dev](https://dr.eamer.dev)
- Bluesky: [@lukesteuber.com](https://bsky.app/profile/lukesteuber.com)
- Email: luke@lukesteuber.com

---

## License

MIT
