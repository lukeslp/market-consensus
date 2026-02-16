# Foresight Quick Reference

## Project Structure

```
foresight/
├── app/
│   ├── __init__.py              # Application factory
│   ├── config.py                # Configuration classes
│   ├── database.py              # SQLite with WAL mode
│   ├── errors.py                # Error handlers
│   ├── routes/
│   │   ├── main.py              # UI routes (/health, /)
│   │   └── api.py               # API routes (/api/*)
│   └── services/
│       ├── stock_service.py     # yfinance wrapper
│       └── prediction_service.py # LLM predictions
├── static/                      # Frontend assets
├── run.py                       # Entry point
├── start.sh                     # Production startup
└── foresight.db                 # SQLite database (WAL mode)
```

## Commands

```bash
# Development
python run.py

# Production
./start.sh

# Service management
sm start/stop/restart/logs foresight

# Database check
sqlite3 foresight.db "PRAGMA journal_mode; .tables"
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with DB status |
| `/api/current` | GET | Current cycle data |
| `/api/stats` | GET | Accuracy statistics |
| `/api/history?page=1` | GET | Historical cycles (paginated) |
| `/api/stock/<symbol>` | GET | Stock prediction history |
| `/api/stream` | GET | SSE real-time updates |
| `/api/cycle/start` | POST | Start new cycle |
| `/api/cycle/<id>/stop` | POST | Stop cycle |

## Database Schema

- **cycles** - Prediction cycles
- **stocks** - Discovered stocks
- **predictions** - LLM predictions
- **results** - Actual outcomes

WAL mode enabled for concurrent reads.

## Configuration

Environment variables (`.env` or `/home/coolhand/.env`):
- `PORT` - Server port (5062)
- `FLASK_ENV` - development/production
- `XAI_API_KEY` - Grok (discovery)
- `ANTHROPIC_API_KEY` - Claude (prediction)
- `GEMINI_API_KEY` - Gemini (synthesis)

## Flask Best Practices Implemented

✅ Application factory pattern
✅ Blueprint structure (main, api)
✅ Environment-based configuration
✅ Error handlers with JSON responses
✅ SQLite WAL mode for concurrency
✅ SSE streaming endpoint
✅ Services layer for business logic
✅ Proper logging with rotation
✅ ProxyFix middleware for Caddy
✅ Health check endpoint
✅ Database connection pooling

## Next Steps

1. Implement background worker for prediction cycles
2. Wire SSE stream to real-time events
3. Add result validation logic
4. Build frontend dashboard
5. Add authentication
6. Implement rate limiting
