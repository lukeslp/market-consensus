# Foresight Database Schema

SQLite database module with WAL mode, foreign keys, and comprehensive indexing.

## Schema Overview

### Tables

1. **cycles** - Prediction cycles (every 10 minutes)
2. **stocks** - Discovered stock tickers with metadata
3. **prices** - Historical price snapshots
4. **predictions** - LLM predictions with accuracy tracking
5. **accuracy_stats** - Rolling accuracy metrics by provider/timeframe
6. **events** - SSE event bridge for real-time updates

## Table Definitions

### cycles

Tracks prediction cycles.

```sql
CREATE TABLE cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'active',  -- active|completed|failed
    stocks_discovered INTEGER DEFAULT 0,
    predictions_made INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Indexes:**
- `idx_cycles_status` on status
- `idx_cycles_start_time` on start_time DESC

### stocks

Discovered stock tickers with running statistics.

```sql
CREATE TABLE stocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL UNIQUE,
    name TEXT,
    first_discovered TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    times_predicted INTEGER DEFAULT 0,
    avg_accuracy REAL,
    last_price REAL,
    last_updated TIMESTAMP,
    metadata TEXT  -- JSON: sector, market_cap, etc.
)
```

**Indexes:**
- `idx_stocks_ticker` on ticker
- `idx_stocks_avg_accuracy` on avg_accuracy DESC

### prices

Historical price snapshots for stocks.

```sql
CREATE TABLE prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id INTEGER NOT NULL,
    cycle_id INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    price REAL NOT NULL,
    volume INTEGER,
    change_percent REAL,
    source TEXT DEFAULT 'yfinance',
    FOREIGN KEY (stock_id) REFERENCES stocks(id) ON DELETE CASCADE,
    FOREIGN KEY (cycle_id) REFERENCES cycles(id) ON DELETE CASCADE
)
```

**Indexes:**
- `idx_prices_stock_id` on stock_id
- `idx_prices_cycle_id` on cycle_id
- `idx_prices_timestamp` on timestamp DESC
- `idx_prices_stock_timestamp` on (stock_id, timestamp DESC)

### predictions

LLM predictions with evaluation results.

```sql
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER NOT NULL,
    stock_id INTEGER NOT NULL,
    provider TEXT NOT NULL,  -- xai|anthropic|gemini
    prediction_time TIMESTAMP NOT NULL,
    target_time TIMESTAMP NOT NULL,
    predicted_direction TEXT NOT NULL,  -- up|down|neutral
    predicted_price REAL,
    confidence REAL,
    reasoning TEXT,
    initial_price REAL NOT NULL,
    actual_price REAL,
    actual_direction TEXT,
    accuracy REAL,  -- 1.0 = correct, 0.0 = incorrect
    evaluated_at TIMESTAMP,
    raw_response TEXT,  -- Full LLM response for debugging
    FOREIGN KEY (cycle_id) REFERENCES cycles(id) ON DELETE CASCADE,
    FOREIGN KEY (stock_id) REFERENCES stocks(id) ON DELETE CASCADE
)
```

**Indexes:**
- `idx_predictions_cycle_id` on cycle_id
- `idx_predictions_stock_id` on stock_id
- `idx_predictions_provider` on provider
- `idx_predictions_accuracy` on accuracy DESC
- `idx_predictions_evaluated` on evaluated_at

### accuracy_stats

Pre-calculated accuracy statistics by provider and timeframe.

```sql
CREATE TABLE accuracy_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    timeframe TEXT NOT NULL,  -- 1h|6h|24h|7d|30d
    total_predictions INTEGER DEFAULT 0,
    correct_predictions INTEGER DEFAULT 0,
    accuracy_rate REAL,
    avg_confidence REAL,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT  -- JSON: additional metrics
)
```

**Indexes:**
- `idx_accuracy_provider` on provider
- `idx_accuracy_timeframe` on timeframe
- `idx_accuracy_calculated` on calculated_at DESC

### events

Event log for SSE streaming (real-time dashboard updates).

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,  -- cycle_start|cycle_end|stock_discovered|prediction_made|price_update|accuracy_update
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data TEXT NOT NULL,  -- JSON event data
    processed INTEGER DEFAULT 0
)
```

**Indexes:**
- `idx_events_type` on event_type
- `idx_events_processed` on processed
- `idx_events_timestamp` on timestamp DESC

## API Reference

### Initialization

```python
from db import ForesightDB, get_db

# Create new instance
db = ForesightDB('/path/to/database.db')

# Use singleton (recommended)
db = get_db()
```

### Cycle Operations

```python
# Create new cycle
cycle_id = db.create_cycle()

# Get current active cycle
cycle = db.get_current_cycle()

# Update cycle stats
db.update_cycle(cycle_id, stocks_discovered=10, predictions_made=50)

# Complete cycle
db.complete_cycle(cycle_id)

# Get recent cycles
cycles = db.get_recent_cycles(limit=10)
```

### Stock Operations

```python
# Add or update stock
stock_id = db.add_stock('AAPL', 'Apple Inc.', {'sector': 'Technology'})

# Get stock by ticker
stock = db.get_stock('AAPL')

# Get stock by ID
stock = db.get_stock_by_id(stock_id)

# Update stock statistics
db.update_stock_stats(stock_id, avg_accuracy=0.75, last_price=150.0)

# Get all stocks
stocks = db.get_all_stocks(order_by='avg_accuracy')
```

### Price Operations

```python
# Add price snapshot
price_id = db.add_price(
    stock_id=stock_id,
    cycle_id=cycle_id,
    price=150.25,
    volume=1000000,
    change_percent=2.5
)

# Get latest price for stock
latest = db.get_latest_price(stock_id)

# Get price at specific time
price = db.get_price_at_time(stock_id, target_datetime)

# Get price history
history = db.get_price_history(stock_id, limit=100, cycle_id=cycle_id)
```

### Prediction Operations

```python
from datetime import datetime, timedelta

# Add prediction
prediction_id = db.add_prediction(
    cycle_id=cycle_id,
    stock_id=stock_id,
    provider='anthropic',
    predicted_direction='up',
    confidence=0.75,
    initial_price=150.0,
    target_time=datetime.now() + timedelta(minutes=10),
    predicted_price=155.0,
    reasoning='Strong momentum indicators'
)

# Evaluate prediction (after target_time)
db.evaluate_prediction(
    prediction_id=prediction_id,
    actual_price=156.0,
    actual_direction='up'
)

# Get prediction
prediction = db.get_prediction(prediction_id)

# Get predictions for cycle
predictions = db.get_predictions_for_cycle(cycle_id)

# Get predictions for stock
predictions = db.get_predictions_for_stock(stock_id, limit=50)

# Get unevaluated predictions (ready to evaluate)
pending = db.get_unevaluated_predictions(before_time=datetime.now())
```

### Accuracy Stats

```python
# Calculate current stats
stats = db.calculate_accuracy_stats(provider='anthropic', timeframe='24h')
# Returns: {'total_predictions': 100, 'correct_predictions': 75, 'accuracy_rate': 0.75, 'avg_confidence': 0.68}

# Store calculated stats
stats_id = db.add_accuracy_stats(
    provider='anthropic',
    timeframe='24h',
    total_predictions=100,
    correct_predictions=75,
    avg_confidence=0.68,
    metadata={'model': 'claude-sonnet-4'}
)

# Get historical stats
stats = db.get_accuracy_stats(provider='anthropic', timeframe='24h', limit=10)

# Get provider leaderboard
leaderboard = db.get_provider_leaderboard()
# Returns list sorted by accuracy_rate DESC
```

### Event Operations (SSE Bridge)

```python
# Get unprocessed events (for SSE streaming)
events = db.get_unprocessed_events(event_type='prediction_made', limit=100)

# Mark events as sent to clients
event_ids = [e['id'] for e in events]
db.mark_events_processed(event_ids)

# Clean up old events
deleted_count = db.cleanup_old_events(days=7)
```

### Utility Methods

```python
# Get dashboard summary (current cycle, total stocks, accuracy, recent predictions)
summary = db.get_dashboard_summary()

# Get provider leaderboard (all providers ranked by accuracy)
leaderboard = db.get_provider_leaderboard()
```

## Database Features

### WAL Mode
Write-Ahead Logging enabled for better concurrency.

```python
PRAGMA journal_mode = WAL
```

### Foreign Keys
All relationships enforced with CASCADE deletes.

```python
PRAGMA foreign_keys = ON
```

### Connection Management
Context manager ensures proper commit/rollback.

```python
with db.get_connection() as conn:
    # Your queries here
    # Automatic commit on success, rollback on error
```

### Row Factory
Column access by name (dict-like).

```python
conn.row_factory = sqlite3.Row
```

## Event Types

Events emitted automatically for SSE streaming:

- `cycle_start` - New prediction cycle started
- `cycle_end` - Cycle completed
- `stock_discovered` - New stock added to database
- `prediction_made` - LLM made a prediction
- `price_update` - Stock price updated
- `accuracy_update` - Prediction evaluated

## Performance Considerations

### Indexes
- 18 indexes cover all common query patterns
- Composite index on (stock_id, timestamp) for price queries
- Descending indexes for latest-first queries

### Cleanup
- Run `cleanup_old_events(days=7)` periodically to prune event log
- Consider VACUUM after large deletions

### Queries
- All foreign keys indexed for join performance
- `LIMIT` clauses on all list queries
- `ORDER BY` uses indexed columns

## Migration Notes

If schema changes are needed, use SQLite's ALTER TABLE or create new tables and migrate data. WAL mode allows reads during migration.

## Testing

Run comprehensive tests:

```bash
python test_db.py
```

Tests cover:
- Cycle CRUD operations
- Stock CRUD with metadata
- Price snapshots and history
- Predictions with evaluation
- Accuracy calculations
- Event emission and processing
- Dashboard summary
- Provider leaderboard
