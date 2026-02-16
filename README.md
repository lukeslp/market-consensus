# Foresight - Stock Prediction Dashboard

Real-time stock prediction dashboard using multi-provider LLM agents.

## Architecture

- **Port**: 5062
- **Backend**: Flask + SQLite + SSE streaming
- **Frontend**: D3.js + vanilla JavaScript
- **Agents**:
  - Grok (xAI) for stock discovery
  - Claude (Anthropic) for predictions
  - Gemini for synthesis

## Quick Start

```bash
cd /home/coolhand/projects/foresight
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Visit: https://dr.eamer.dev/foresight/

## Structure

- `db.py` - Database module (SQLite)
- `agents.py` - LLM agent integration
- `price_fetcher.py` - Stock price fetching (yfinance)
- `worker.py` - Background prediction worker
- `app.py` - Flask API server
- `static/` - Frontend (HTML/CSS/JS/D3.js)

## Status

This project was recreated from implementation plans after the original dashcam code was lost.
Core architecture is in place. Needs implementation of LLM agents and frontend visualization.

