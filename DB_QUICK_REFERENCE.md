# Database Quick Reference

## Import and Initialize

```python
from db import ForesightDB, get_db

# New instance (for workers, scripts)
db = ForesightDB('/path/to/foresight.db')

# Singleton (recommended)
db = get_db()

# Flask routes
from app.database import get_db
db = get_db()
```

## Common Operations

### Start a Prediction Cycle

```python
from datetime import datetime, timedelta

# Create cycle
cycle_id = db.create_cycle()

# Discover and add stocks
stock_id = db.add_stock('AAPL', 'Apple Inc.', {'sector': 'Technology'})

# Record initial price
price_id = db.add_price(
    stock_id=stock_id,
    cycle_id=cycle_id,
    price=150.25,
    volume=1000000
)

# Make prediction
prediction_id = db.add_prediction(
    cycle_id=cycle_id,
    stock_id=stock_id,
    provider='anthropic',
    predicted_direction='up',
    confidence=0.75,
    initial_price=150.25,
    target_time=datetime.now() + timedelta(minutes=10),
    reasoning='Strong upward momentum'
)

# Update cycle stats
db.update_cycle(
    cycle_id,
    stocks_discovered=1,
    predictions_made=1
)
```

### Evaluate Predictions

```python
# Get predictions ready to evaluate
pending = db.get_unevaluated_predictions(before_time=datetime.now())

for pred in pending:
    # Fetch actual outcome (e.g., from yfinance)
    actual_price = 156.0
    actual_direction = 'up' if actual_price > pred['initial_price'] else 'down'

    # Evaluate
    db.evaluate_prediction(
        prediction_id=pred['id'],
        actual_price=actual_price,
        actual_direction=actual_direction
    )
    # This automatically updates stock.avg_accuracy
```

### Complete Cycle

```python
# Mark cycle as completed
db.complete_cycle(cycle_id)

# Calculate accuracy stats for this cycle
stats = db.calculate_accuracy_stats(provider='anthropic', timeframe='1h')

# Store stats
db.add_accuracy_stats(
    provider='anthropic',
    timeframe='1h',
    total_predictions=stats['total_predictions'],
    correct_predictions=stats['correct_predictions'],
    avg_confidence=stats['avg_confidence']
)
```

### Get Dashboard Data

```python
# Single query for dashboard
summary = db.get_dashboard_summary()
# Returns: {
#   'current_cycle': {...},
#   'total_stocks': 50,
#   'overall_accuracy': 0.68,
#   'recent_predictions': [...]
# }

# Provider leaderboard
leaderboard = db.get_provider_leaderboard()
# Returns: [
#   {'provider': 'anthropic', 'total_predictions': 100, 'accuracy_rate': 0.75, ...},
#   {'provider': 'xai', 'total_predictions': 98, 'accuracy_rate': 0.71, ...}
# ]
```

### SSE Streaming

```python
from flask import Response
import json
import time

@app.route('/api/stream')
def stream():
    def generate():
        last_id = 0
        while True:
            # Get new events
            events = db.get_unprocessed_events(limit=50)

            if events:
                event_ids = []
                for event in events:
                    if event['id'] > last_id:
                        yield f"data: {json.dumps(event)}\n\n"
                        event_ids.append(event['id'])
                        last_id = event['id']

                # Mark as processed
                db.mark_events_processed(event_ids)

            time.sleep(1)

    return Response(generate(), mimetype='text/event-stream')
```

### Query Stock History

```python
# Get stock by ticker
stock = db.get_stock('AAPL')

# Get all predictions for this stock
predictions = db.get_predictions_for_stock(stock['id'], limit=100)

# Get price history
prices = db.get_price_history(stock['id'], limit=100)

# Get latest price
latest = db.get_latest_price(stock['id'])

# Get price at specific time
from datetime import datetime
price = db.get_price_at_time(stock['id'], datetime(2024, 1, 15, 14, 30))
```

## Event Types

Events are automatically emitted for:

- `cycle_start` - New cycle created
- `cycle_end` - Cycle completed
- `stock_discovered` - New stock added
- `prediction_made` - Prediction created
- `price_update` - Price snapshot added
- `accuracy_update` - Prediction evaluated

Access via:
```python
events = db.get_unprocessed_events(event_type='prediction_made')
```

## Cheat Sheet

| Task | Method |
|------|--------|
| Start cycle | `create_cycle()` |
| Get active cycle | `get_current_cycle()` |
| Add stock | `add_stock(ticker, name, metadata)` |
| Record price | `add_price(stock_id, cycle_id, price, ...)` |
| Make prediction | `add_prediction(cycle_id, stock_id, ...)` |
| Evaluate | `evaluate_prediction(pred_id, actual_price, actual_direction)` |
| Complete cycle | `complete_cycle(cycle_id)` |
| Get stats | `calculate_accuracy_stats(provider, timeframe)` |
| Dashboard | `get_dashboard_summary()` |
| Leaderboard | `get_provider_leaderboard()` |
| Stream events | `get_unprocessed_events()` |

## Testing

```bash
python test_db.py
```

## Full Documentation

- `DATABASE.md` - Complete schema and API reference
- `INTEGRATION_GUIDE.md` - Flask integration steps
- `DB_IMPLEMENTATION_SUMMARY.md` - Architecture overview
