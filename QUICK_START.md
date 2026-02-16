## Foresight - Quick Start Guide

### Installation

```bash
cd /home/coolhand/projects/foresight
source venv/bin/activate

# Core dependencies (required)
pip install flask yfinance requests gunicorn python-dotenv

# LLM providers (optional, for predictions)
pip install openai anthropic google-generativeai
```

### Start the Server

```bash
# Option 1: Service manager (recommended for production)
sm start foresight
sm logs foresight -f

# Option 2: Manually with Gunicorn
./start.sh

# Option 3: Development mode
python run.py
```

**Access**: http://localhost:5062 or https://dr.eamer.dev/foresight

### Quick Test

```bash
# Run integration tests
python test_integration.py

# Test health endpoint
curl http://localhost:5062/health

# Test current cycle
curl http://localhost:5062/api/current

# Test stats
curl http://localhost:5062/api/stats

# Test SSE streaming
curl -N http://localhost:5062/api/stream
```

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /api/current` | Current prediction cycle |
| `GET /api/stats` | Accuracy statistics |
| `GET /api/history?page=1&per_page=20` | Historical cycles |
| `GET /api/stock/<SYMBOL>` | Stock detail with predictions |
| `GET /api/stream` | SSE event stream |
| `GET /api/worker/status` | Background worker status |
| `POST /api/cycle/start` | Check worker status |
| `POST /api/cycle/<id>/stop` | Stop prediction cycle |

### SSE Events

Connect to `/api/stream` to receive real-time events:

```javascript
const eventSource = new EventSource('/api/stream');
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  switch(data.type) {
    case 'cycle_start':
      console.log('Cycle started:', data.data.cycle_id);
      break;
    case 'stock_discovered':
      console.log('Stock found:', data.data.symbol);
      break;
    case 'prediction':
      console.log('Prediction:', data.data);
      break;
    case 'cycle_complete':
      console.log('Cycle complete');
      break;
  }
};
```

### Configuration

Edit `.env` or use environment variables:

```bash
# Server
PORT=5062
FLASK_ENV=production

# Prediction Cycle
CYCLE_INTERVAL=600      # 10 minutes between cycles
MAX_STOCKS=10           # Stocks per cycle
LOOKBACK_DAYS=30        # Historical data window

# LLM Providers
DISCOVERY_PROVIDER=xai        # Grok for stock discovery
PREDICTION_PROVIDER=anthropic # Claude for predictions
SYNTHESIS_PROVIDER=gemini     # Gemini for confidence

# API Keys (load from /home/coolhand/.env)
XAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
```

### How It Works

1. **Background Worker** starts automatically when server launches
2. Every **10 minutes** (configurable), worker runs a prediction cycle:
   - **Phase 1**: Grok discovers 10 interesting stocks
   - **Phase 2**: Claude generates predictions for each stock
   - **Phase 3**: Stores predictions in database
3. **SSE Stream** broadcasts events to connected clients in real-time
4. **API Endpoints** provide access to current and historical data

### Database

**Location**: `foresight.db` (SQLite with WAL mode)

**Schema**:
- `cycles` - Prediction cycles
- `stocks` - Stock registry
- `prices` - Historical price snapshots
- `predictions` - LLM predictions
- `accuracy_stats` - Provider performance
- `events` - SSE event queue

**Backup**:
```bash
sqlite3 foresight.db ".backup foresight_backup.db"
```

### Troubleshooting

**Worker not starting predictions**:
- Check that LLM provider packages are installed
- Verify API keys in environment
- Check logs: `sm logs foresight -f`

**SSE events not streaming**:
- Check that `/api/stream` endpoint is accessible
- Verify Caddy is not buffering SSE responses
- Check browser console for connection errors

**Database locked errors**:
```bash
# Check WAL mode is enabled
sqlite3 foresight.db "PRAGMA journal_mode;"
# Should return: wal
```

**Port already in use**:
```bash
lsof -i :5062
sm stop foresight
```

### Service Manager Commands

```bash
sm status foresight        # Check if running
sm start foresight         # Start service
sm stop foresight          # Stop service
sm restart foresight       # Restart service
sm logs foresight          # View logs
sm logs foresight -f       # Follow logs
sm health foresight        # Health check
```

### Next Steps

1. **Frontend**: Build D3.js visualizations in `static/js/`
2. **Evaluation**: Create scheduled job to evaluate prediction accuracy
3. **Authentication**: Add JWT tokens for cycle control endpoints
4. **Rate Limiting**: Protect API endpoints
5. **Monitoring**: Add Sentry or error tracking

### Files to Know

- `app/__init__.py` - Application factory
- `app/worker.py` - Background worker
- `app/routes/api.py` - API endpoints
- `app/services/prediction_service.py` - LLM integration
- `app/services/stock_service.py` - Stock data fetching
- `db.py` - Database implementation
- `run.py` - Server entry point
- `start.sh` - Production startup script
- `test_integration.py` - Integration tests

### Architecture Diagram

```
┌─────────────────────────────────────────────┐
│  Client (Browser)                            │
│  ├─ HTTP Requests → /api/*                  │
│  └─ SSE Connection → /api/stream            │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│  Caddy Reverse Proxy                        │
│  /foresight/* → localhost:5062              │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│  Flask App (Gunicorn)                       │
│  ├─ API Routes Blueprint                    │
│  ├─ Main Routes Blueprint                   │
│  └─ Error Handlers                          │
└──────┬───────────────────────┬──────────────┘
       │                       │
┌──────▼──────┐       ┌────────▼─────────┐
│  ForesightDB │       │ PredictionWorker │
│  (SQLite)    │       │ (Background)     │
└──────────────┘       └────────┬─────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Services             │
                    ├─ StockService         │
                    │  └─ yfinance          │
                    └─ PredictionService    │
                       └─ LLM Providers     │
                          ├─ Grok (xAI)     │
                          ├─ Claude         │
                          └─ Gemini         │
```

### Support

- **Documentation**: `CLAUDE.md`, `DATABASE.md`, `IMPLEMENTATION_STATUS.md`
- **Tests**: `test_integration.py`, `test_db.py`
- **Logs**: `foresight.log` or `sm logs foresight`
