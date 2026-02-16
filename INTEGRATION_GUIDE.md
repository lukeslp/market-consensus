# Foresight Database Integration Guide

## What Was Implemented

I've created a comprehensive SQLite database module (db.py) for Foresight with the following features:

### Database Module (db.py)

- **WAL Mode**: Write-Ahead Logging enabled for better concurrency
- **Foreign Keys**: All relationships enforced with CASCADE deletes
- **18 Indexes**: Optimized for common query patterns
- **6 Tables**: cycles, stocks, prices, predictions, accuracy_stats, events
- **Complete CRUD API**: 50+ methods covering all database operations
- **Event System**: SSE bridge for real-time updates
- **Context Managers**: Automatic commit/rollback handling

### Test Suite (test_db.py)

- Comprehensive tests covering all CRUD operations
- Tests for accuracy calculations and leaderboards
- Event system validation
- All tests passing

### Documentation (DATABASE.md)

- Complete schema documentation
- API reference with examples
- Performance considerations
- Migration notes

## Integration Options

You have two options for integrating the new database module:

### Option 1: Update app/database.py (Recommended)

Replace the contents of `app/database.py` with:

```python
"""
Database management for Foresight
SQLite with WAL mode for concurrent access

This module provides Flask integration for the ForesightDB class.
The actual database implementation is in the root-level db.py module.
"""
import sys
from pathlib import Path

# Add parent directory to path to import db.py
root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from db import ForesightDB
from flask import g, current_app


def get_db():
    """Get ForesightDB instance from Flask g object"""
    if 'foresight_db' not in g:
        g.foresight_db = ForesightDB(current_app.config['DB_PATH'])
    return g.foresight_db


def close_db(e=None):
    """Close database connection (cleanup if needed)"""
    # ForesightDB uses context managers, no persistent connection to close
    g.pop('foresight_db', None)


def init_db(app):
    """Initialize database schema"""
    with app.app_context():
        db = get_db()
        # Schema is automatically initialized in ForesightDB.__init__
        app.logger.info(f'ForesightDB initialized at {app.config["DB_PATH"]} with WAL mode enabled')
```

### Option 2: Use db_bridge.py

If you want to keep the existing `app/database.py`, you can use `app/db_bridge.py` instead:

1. Import from db_bridge in routes:
```python
from app.db_bridge import get_foresight_db

@api_bp.route('/current')
def current():
    db = get_foresight_db()
    cycle = db.get_current_cycle()
    ...
```

2. Register teardown in `app/__init__.py`:
```python
from app.db_bridge import close_foresight_db
app.teardown_appcontext(close_foresight_db)
```

## Updated API Routes

I've already updated `app/routes/api.py` to use the new ForesightDB methods:

- `/api/current` - Uses `get_current_cycle()`, `get_predictions_for_cycle()`
- `/api/stats` - Uses `get_provider_leaderboard()`, `get_dashboard_summary()`
- `/api/history` - Uses `get_recent_cycles()`
- `/api/stock/<symbol>` - Uses `get_stock()`, `get_predictions_for_stock()`, `get_price_history()`

The cycle start/stop endpoints still need updating.

## Migration Steps

1. **Back up your existing database** (if any):
   ```bash
   cp foresight.db foresight.db.backup
   ```

2. **Choose integration option** (see above)

3. **Update remaining routes** in `app/routes/api.py`:

   Replace the `/cycle/start` endpoint:
   ```python
   @api_bp.route('/cycle/start', methods=['POST'])
   def start_cycle():
       """Manually trigger a new prediction cycle"""
       db = get_db()

       # Check for active cycle
       current = db.get_current_cycle()
       if current and current['status'] == 'active':
           return jsonify({
               'error': 'Cycle already running',
               'cycle_id': current['id']
           }), 409

       # Create new cycle
       cycle_id = db.create_cycle()

       current_app.logger.info(f'Started prediction cycle {cycle_id}')

       return jsonify({
           'status': 'started',
           'cycle_id': cycle_id,
           'message': 'Prediction cycle started'
       }), 201
   ```

   Replace the `/cycle/<id>/stop` endpoint:
   ```python
   @api_bp.route('/cycle/<int:cycle_id>/stop', methods=['POST'])
   def stop_cycle(cycle_id):
       """Manually stop a prediction cycle"""
       db = get_db()

       cycle = db.get_cycle(cycle_id)
       if not cycle or cycle['status'] != 'active':
           return jsonify({
               'error': 'Cycle not found or already stopped'
           }), 404

       success = db.complete_cycle(cycle_id)

       if success:
           current_app.logger.info(f'Stopped prediction cycle {cycle_id}')
           return jsonify({
               'status': 'stopped',
               'cycle_id': cycle_id
           })
       else:
           return jsonify({
               'error': 'Failed to stop cycle'
           }), 500
   ```

4. **Update SSE streaming** to use events table:

   Add to `/api/stream`:
   ```python
   @api_bp.route('/stream')
   def stream():
       """SSE endpoint for real-time prediction updates"""
       db = get_db()

       def generate():
           yield f"retry: {current_app.config.get('SSE_RETRY', 3000)}\n\n"
           yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.now().isoformat()})}\n\n"

           last_event_id = 0

           while True:
               # Get new unprocessed events
               events = db.get_unprocessed_events(limit=50)

               if events:
                   event_ids = []
                   for event in events:
                       if event['id'] > last_event_id:
                           yield f"data: {json.dumps(event)}\n\n"
                           event_ids.append(event['id'])
                           last_event_id = event['id']

                   # Mark events as processed
                   if event_ids:
                       db.mark_events_processed(event_ids)

               time.sleep(1)

       return Response(generate(), mimetype='text/event-stream')
   ```

5. **Test the integration**:
   ```bash
   source venv/bin/activate
   python run.py
   ```

   Visit `http://localhost:5062/health` and check logs.

## Database Schema Differences

The new schema has improvements over the old one:

| Feature | Old Schema | New Schema |
|---------|------------|------------|
| Stocks | Per-cycle (cycle_id FK) | Global (unique by ticker) |
| Prices | Not tracked | Full history table |
| Predictions | Simple | Includes initial_price, target_time, accuracy tracking |
| Events | Not tracked | SSE event bridge |
| Accuracy Stats | Manual calculation | Pre-calculated + real-time |
| Indexes | 4 indexes | 18 indexes |

### Migrating Old Data

If you have existing data in the old schema, you'll need to:

1. Export old data:
   ```python
   import sqlite3
   old_db = sqlite3.connect('foresight.db.backup')
   # Export cycles, stocks, predictions...
   ```

2. Transform to new schema:
   - Consolidate stocks across cycles (use first occurrence)
   - Add placeholder prices from stock.current_price
   - Map predictions to new structure

3. Or start fresh (recommended for development)

## Key Differences in Usage

### Old Way (Raw SQL)
```python
db = get_db()
cycle = db.execute('SELECT * FROM cycles WHERE status = ? LIMIT 1', ('running',)).fetchone()
```

### New Way (ForesightDB API)
```python
db = get_db()
cycle = db.get_current_cycle()
```

### Benefits
- **Type safety**: Returns Dict[str, Any] instead of Row objects
- **Automatic JSON handling**: metadata fields auto-serialized/deserialized
- **Error handling**: Context managers handle commit/rollback
- **Event emission**: Changes automatically emit SSE events
- **Stats calculation**: Built-in accuracy calculations

## Testing

Run the test suite to verify everything works:

```bash
source venv/bin/activate
python test_db.py
```

Expected output:
```
✓ Database initialized with schema
✓ Created cycle: 1
✓ Got current cycle: 1
...
✅ All database tests passed!
```

## Next Steps

1. **Worker Integration**: Use ForesightDB in prediction worker
   ```python
   from db import get_db  # Use singleton

   def run_prediction_cycle():
       db = get_db()
       cycle_id = db.create_cycle()
       # ... discover stocks, make predictions
       db.complete_cycle(cycle_id)
   ```

2. **Frontend Integration**: Connect SSE to dashboard
   ```javascript
   const eventSource = new EventSource('/api/stream');
   eventSource.onmessage = (event) => {
       const data = JSON.parse(event.data);
       if (data.type === 'prediction_made') {
           updateDashboard(data);
       }
   };
   ```

3. **Accuracy Tracking**: Implement prediction evaluation
   ```python
   # After target_time
   pending = db.get_unevaluated_predictions()
   for pred in pending:
       actual_price = fetch_current_price(pred['stock_id'])
       actual_direction = calculate_direction(pred['initial_price'], actual_price)
       db.evaluate_prediction(pred['id'], actual_price, actual_direction)
   ```

## Troubleshooting

### Import Error: "No module named 'db'"
- Check that db.py is in /home/coolhand/projects/foresight/
- Verify sys.path includes the project root

### Database Locked Error
- WAL mode should prevent this, but if it occurs:
  ```bash
  sqlite3 foresight.db "PRAGMA journal_mode;"  # Should show "wal"
  ```

### Schema Mismatch
- Delete database and reinitialize:
  ```bash
  rm foresight.db foresight.db-shm foresight.db-wal
  python run.py  # Will recreate with new schema
  ```

### Events Not Streaming
- Check that events are being emitted:
  ```python
  db = get_db()
  events = db.get_unprocessed_events(limit=10)
  print(f"Found {len(events)} unprocessed events")
  ```

## Files Created

- `/home/coolhand/projects/foresight/db.py` - Main database module (850 lines)
- `/home/coolhand/projects/foresight/test_db.py` - Test suite (250 lines)
- `/home/coolhand/projects/foresight/DATABASE.md` - Schema documentation
- `/home/coolhand/projects/foresight/app/db_bridge.py` - Flask bridge (alternative)
- `/home/coolhand/projects/foresight/INTEGRATION_GUIDE.md` - This file

## Questions?

- See DATABASE.md for complete API reference
- Check test_db.py for usage examples
- Existing app/routes/api.py shows integration patterns
