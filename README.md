# Foresight

Stock prediction dashboard. Runs three language models in a structured debate cycle — discovery, analysis, contrarian review, consensus — then tracks whether the predictions were right.

## Stack

- **Backend**: Flask + SQLite (WAL mode) + SSE streaming
- **Frontend**: D3.js v7, vanilla JS, Oracle Terminal aesthetic
- **Models**: Grok (discovery + contrarian), Claude (primary analysis), Gemini (synthesis)
- **Port**: 5062 · **URL**: https://dr.eamer.dev/foresight/

## Quick Start

```bash
source venv/bin/activate
export PYTHONPATH=/home/coolhand/shared:$PYTHONPATH
python run.py
```

Service manager: `sm start foresight-api` / `sm logs foresight-api`

## Layout

```
app/
  routes/api.py       REST endpoints + SSE stream
  routes/main.py      Dashboard HTML route
  services/
    stock_service.py      Price fetching (yfinance)
    prediction_service.py LLM debate cycle
  worker.py           Background cycle runner
  config.py
db.py                 ForesightDB (SQLite)
static/               Frontend
  index.html
  css/  style.css · layout.css · animations.css
  js/   app.js · grid.js · detail.js · sidebar.js · api.js
run.py
```

## Prediction Cycle

1. **Discovery** — Grok selects 10–50 stocks worth watching
2. **Analysis** — Claude generates directional predictions with confidence
3. **Debate** — Grok argues the contrarian case for each
4. **Consensus** — Gemini synthesizes a final direction and confidence score

Accuracy is tracked per-provider against actual closing prices.

## Tests

```bash
pytest tests/ -q
```
