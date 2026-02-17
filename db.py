"""
Foresight Database Module
SQLite database with WAL mode, proper indexes, and foreign keys
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from contextlib import contextmanager

# Try to import settings, but allow db_path to be passed explicitly
try:
    import settings
    DEFAULT_DB_PATH = settings.DB_PATH
except ImportError:
    DEFAULT_DB_PATH = 'foresight.db'


class ForesightDB:
    """SQLite database manager for stock predictions"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._init_db()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        conn.execute("PRAGMA foreign_keys = ON")  # Enforce foreign keys
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema with WAL mode and indexes"""
        with self.get_connection() as conn:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode = WAL")

            # Cycles table - prediction cycles
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cycles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    status TEXT NOT NULL DEFAULT 'active',
                    stocks_discovered INTEGER DEFAULT 0,
                    predictions_made INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT status_check CHECK (status IN ('active', 'completed', 'failed'))
                )
            """)

            # Stocks table - discovered tickers
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    name TEXT,
                    first_discovered TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    times_predicted INTEGER DEFAULT 0,
                    avg_accuracy REAL,
                    last_price REAL,
                    last_updated TIMESTAMP,
                    metadata TEXT  -- JSON for additional info
                )
            """)

            # Prices table - historical price snapshots
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prices (
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
            """)

            # Predictions table - LLM predictions with accuracy tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_id INTEGER NOT NULL,
                    stock_id INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    prediction_time TIMESTAMP NOT NULL,
                    target_time TIMESTAMP NOT NULL,
                    predicted_direction TEXT NOT NULL,
                    predicted_price REAL,
                    confidence REAL,
                    reasoning TEXT,
                    initial_price REAL NOT NULL,
                    actual_price REAL,
                    actual_direction TEXT,
                    accuracy REAL,
                    evaluated_at TIMESTAMP,
                    raw_response TEXT,  -- Full LLM response
                    FOREIGN KEY (cycle_id) REFERENCES cycles(id) ON DELETE CASCADE,
                    FOREIGN KEY (stock_id) REFERENCES stocks(id) ON DELETE CASCADE,
                    CONSTRAINT direction_check CHECK (predicted_direction IN ('up', 'down', 'neutral'))
                )
            """)

            # Accuracy stats table - rolling metrics
            conn.execute("""
                CREATE TABLE IF NOT EXISTS accuracy_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    total_predictions INTEGER DEFAULT 0,
                    correct_predictions INTEGER DEFAULT 0,
                    accuracy_rate REAL,
                    avg_confidence REAL,
                    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT  -- JSON for additional metrics
                )
            """)

            # Events table - SSE bridge for real-time updates
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    data TEXT NOT NULL,  -- JSON data
                    processed INTEGER DEFAULT 0,
                    CONSTRAINT event_type_check CHECK (event_type IN (
                        'cycle_start', 'cycle_end', 'stock_discovered',
                        'prediction_made', 'price_update', 'accuracy_update'
                    ))
                )
            """)

            # Create indexes for performance
            self._create_indexes(conn)

    def _create_indexes(self, conn):
        """Create indexes on frequently queried columns"""
        indexes = [
            # Cycles
            "CREATE INDEX IF NOT EXISTS idx_cycles_status ON cycles(status)",
            "CREATE INDEX IF NOT EXISTS idx_cycles_start_time ON cycles(start_time DESC)",

            # Stocks
            "CREATE INDEX IF NOT EXISTS idx_stocks_ticker ON stocks(ticker)",
            "CREATE INDEX IF NOT EXISTS idx_stocks_avg_accuracy ON stocks(avg_accuracy DESC)",

            # Prices
            "CREATE INDEX IF NOT EXISTS idx_prices_stock_id ON prices(stock_id)",
            "CREATE INDEX IF NOT EXISTS idx_prices_cycle_id ON prices(cycle_id)",
            "CREATE INDEX IF NOT EXISTS idx_prices_timestamp ON prices(timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_prices_stock_timestamp ON prices(stock_id, timestamp DESC)",

            # Predictions
            "CREATE INDEX IF NOT EXISTS idx_predictions_cycle_id ON predictions(cycle_id)",
            "CREATE INDEX IF NOT EXISTS idx_predictions_stock_id ON predictions(stock_id)",
            "CREATE INDEX IF NOT EXISTS idx_predictions_provider ON predictions(provider)",
            "CREATE INDEX IF NOT EXISTS idx_predictions_accuracy ON predictions(accuracy DESC)",
            "CREATE INDEX IF NOT EXISTS idx_predictions_evaluated ON predictions(evaluated_at)",

            # Accuracy stats
            "CREATE INDEX IF NOT EXISTS idx_accuracy_provider ON accuracy_stats(provider)",
            "CREATE INDEX IF NOT EXISTS idx_accuracy_timeframe ON accuracy_stats(timeframe)",
            "CREATE INDEX IF NOT EXISTS idx_accuracy_calculated ON accuracy_stats(calculated_at DESC)",

            # Events
            "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)",
            "CREATE INDEX IF NOT EXISTS idx_events_processed ON events(processed)",
            "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC)"
        ]

        for index_sql in indexes:
            conn.execute(index_sql)

    # ========== Cycle CRUD ==========

    def create_cycle(self, start_time: datetime = None) -> int:
        """Create a new prediction cycle"""
        start_time = start_time or datetime.now()
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO cycles (start_time, status) VALUES (?, 'active')",
                (start_time,)
            )
            cycle_id = cursor.lastrowid
            self._emit_event(conn, 'cycle_start', {'cycle_id': cycle_id, 'start_time': str(start_time)})
            return cycle_id

    def get_current_cycle(self) -> Optional[Dict[str, Any]]:
        """Get the currently active cycle"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM cycles WHERE status = 'active' ORDER BY start_time DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def get_cycle(self, cycle_id: int) -> Optional[Dict[str, Any]]:
        """Get cycle by ID"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
            return dict(row) if row else None

    def update_cycle(self, cycle_id: int, **kwargs) -> bool:
        """Update cycle fields"""
        if not kwargs:
            return False

        valid_fields = {'end_time', 'status', 'stocks_discovered', 'predictions_made'}
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}

        if not updates:
            return False

        set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [cycle_id]

        with self.get_connection() as conn:
            cursor = conn.execute(
                f"UPDATE cycles SET {set_clause} WHERE id = ?",
                values
            )
            if cursor.rowcount > 0:
                self._emit_event(conn, 'cycle_end', {'cycle_id': cycle_id, **updates})
                return True
            return False

    def complete_cycle(self, cycle_id: int) -> bool:
        """Mark cycle as completed"""
        return self.update_cycle(
            cycle_id,
            end_time=datetime.now(),
            status='completed'
        )

    def get_recent_cycles(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent cycles"""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM cycles ORDER BY start_time DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    # ========== Stock CRUD ==========

    def add_stock(self, ticker: str, name: str = None, metadata: Dict = None) -> int:
        """Add or update a stock ticker"""
        ticker = ticker.upper()
        with self.get_connection() as conn:
            # Try to insert, on conflict update
            cursor = conn.execute("""
                INSERT INTO stocks (ticker, name, metadata)
                VALUES (?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    name = COALESCE(excluded.name, stocks.name),
                    metadata = COALESCE(excluded.metadata, stocks.metadata)
            """, (ticker, name, json.dumps(metadata) if metadata else None))

            # Get the stock_id
            row = conn.execute("SELECT id FROM stocks WHERE ticker = ?", (ticker,)).fetchone()
            stock_id = row['id']

            if cursor.rowcount > 0 and cursor.lastrowid == stock_id:
                # New stock discovered
                self._emit_event(conn, 'stock_discovered', {
                    'stock_id': stock_id,
                    'ticker': ticker,
                    'name': name
                })

            return stock_id

    def get_stock(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get stock by ticker"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM stocks WHERE ticker = ?", (ticker,)).fetchone()
            if row:
                result = dict(row)
                if result.get('metadata'):
                    result['metadata'] = json.loads(result['metadata'])
                return result
            return None

    def get_stock_by_id(self, stock_id: int) -> Optional[Dict[str, Any]]:
        """Get stock by ID"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM stocks WHERE id = ?", (stock_id,)).fetchone()
            if row:
                result = dict(row)
                if result.get('metadata'):
                    result['metadata'] = json.loads(result['metadata'])
                return result
            return None

    def update_stock_stats(self, stock_id: int, **kwargs) -> bool:
        """Update stock statistics"""
        valid_fields = {'times_predicted', 'avg_accuracy', 'last_price', 'last_updated'}
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}

        if not updates:
            return False

        set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [stock_id]

        with self.get_connection() as conn:
            cursor = conn.execute(
                f"UPDATE stocks SET {set_clause} WHERE id = ?",
                values
            )
            return cursor.rowcount > 0

    def get_all_stocks(self, order_by: str = 'ticker') -> List[Dict[str, Any]]:
        """Get all stocks, optionally ordered"""
        valid_orders = {'ticker', 'avg_accuracy', 'times_predicted', 'last_updated'}
        if order_by not in valid_orders:
            order_by = 'ticker'

        with self.get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM stocks ORDER BY {order_by} DESC"
            ).fetchall()
            results = []
            for row in rows:
                result = dict(row)
                if result.get('metadata'):
                    result['metadata'] = json.loads(result['metadata'])
                results.append(result)
            return results

    # ========== Price CRUD ==========

    def add_price(
        self,
        stock_id: int,
        cycle_id: int,
        price: float,
        timestamp: datetime = None,
        volume: int = None,
        change_percent: float = None,
        source: str = 'yfinance'
    ) -> int:
        """Add a price snapshot"""
        timestamp = timestamp or datetime.now()

        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO prices (stock_id, cycle_id, timestamp, price, volume, change_percent, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (stock_id, cycle_id, timestamp, price, volume, change_percent, source))

            # Update stock's last price
            conn.execute(
                "UPDATE stocks SET last_price = ?, last_updated = ? WHERE id = ?",
                (price, timestamp, stock_id)
            )

            self._emit_event(conn, 'price_update', {
                'stock_id': stock_id,
                'price': price,
                'timestamp': str(timestamp)
            })

            return cursor.lastrowid

    def get_latest_price(self, stock_id: int) -> Optional[Dict[str, Any]]:
        """Get most recent price for a stock"""
        with self.get_connection() as conn:
            row = conn.execute("""
                SELECT * FROM prices
                WHERE stock_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (stock_id,)).fetchone()
            return dict(row) if row else None

    def get_price_at_time(
        self,
        stock_id: int,
        timestamp: datetime
    ) -> Optional[Dict[str, Any]]:
        """Get price closest to a specific timestamp"""
        with self.get_connection() as conn:
            # Get closest price before or at the timestamp
            row = conn.execute("""
                SELECT * FROM prices
                WHERE stock_id = ? AND timestamp <= ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (stock_id, timestamp)).fetchone()
            return dict(row) if row else None

    def get_price_history(
        self,
        stock_id: int,
        limit: int = 100,
        cycle_id: int = None
    ) -> List[Dict[str, Any]]:
        """Get price history for a stock"""
        with self.get_connection() as conn:
            if cycle_id:
                rows = conn.execute("""
                    SELECT * FROM prices
                    WHERE stock_id = ? AND cycle_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (stock_id, cycle_id, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM prices
                    WHERE stock_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (stock_id, limit)).fetchall()

            return [dict(row) for row in rows]

    # ========== Prediction CRUD ==========

    def add_prediction(
        self,
        cycle_id: int,
        stock_id: int,
        provider: str,
        predicted_direction: str,
        confidence: float,
        initial_price: float,
        target_time: datetime,
        predicted_price: float = None,
        reasoning: str = None,
        raw_response: str = None,
        prediction_time: datetime = None
    ) -> int:
        """Add a new prediction"""
        prediction_time = prediction_time or datetime.now()

        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO predictions (
                    cycle_id, stock_id, provider, prediction_time, target_time,
                    predicted_direction, predicted_price, confidence, reasoning,
                    initial_price, raw_response
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cycle_id, stock_id, provider, prediction_time, target_time,
                predicted_direction, predicted_price, confidence, reasoning,
                initial_price, raw_response
            ))

            # Update stock prediction count
            conn.execute(
                "UPDATE stocks SET times_predicted = times_predicted + 1 WHERE id = ?",
                (stock_id,)
            )

            # Update cycle prediction count
            conn.execute(
                "UPDATE cycles SET predictions_made = predictions_made + 1 WHERE id = ?",
                (cycle_id,)
            )

            self._emit_event(conn, 'prediction_made', {
                'prediction_id': cursor.lastrowid,
                'stock_id': stock_id,
                'provider': provider,
                'direction': predicted_direction,
                'confidence': confidence
            })

            return cursor.lastrowid

    def evaluate_prediction(
        self,
        prediction_id: int,
        actual_price: float,
        actual_direction: str
    ) -> bool:
        """Evaluate a prediction with actual results"""
        with self.get_connection() as conn:
            # Get prediction details
            pred = conn.execute(
                "SELECT * FROM predictions WHERE id = ?",
                (prediction_id,)
            ).fetchone()

            if not pred:
                return False

            # Calculate accuracy (1.0 for correct direction, 0.0 for incorrect)
            accuracy = 1.0 if pred['predicted_direction'] == actual_direction else 0.0

            # Update prediction
            conn.execute("""
                UPDATE predictions
                SET actual_price = ?, actual_direction = ?, accuracy = ?, evaluated_at = ?
                WHERE id = ?
            """, (actual_price, actual_direction, accuracy, datetime.now(), prediction_id))

            # Recalculate stock average accuracy
            avg_row = conn.execute("""
                SELECT AVG(accuracy) as avg_acc
                FROM predictions
                WHERE stock_id = ? AND accuracy IS NOT NULL
            """, (pred['stock_id'],)).fetchone()

            if avg_row and avg_row['avg_acc'] is not None:
                conn.execute(
                    "UPDATE stocks SET avg_accuracy = ? WHERE id = ?",
                    (avg_row['avg_acc'], pred['stock_id'])
                )

            self._emit_event(conn, 'accuracy_update', {
                'prediction_id': prediction_id,
                'accuracy': accuracy,
                'provider': pred['provider']
            })

            return True

    def get_prediction(self, prediction_id: int) -> Optional[Dict[str, Any]]:
        """Get prediction by ID"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM predictions WHERE id = ?",
                (prediction_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_predictions_for_cycle(self, cycle_id: int) -> List[Dict[str, Any]]:
        """Get all predictions for a cycle"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT p.*, s.ticker, s.name
                FROM predictions p
                JOIN stocks s ON p.stock_id = s.id
                WHERE p.cycle_id = ?
                ORDER BY p.prediction_time DESC
            """, (cycle_id,)).fetchall()
            return [dict(row) for row in rows]

    def get_predictions_for_stock(
        self,
        stock_id: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get predictions for a specific stock"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM predictions
                WHERE stock_id = ?
                ORDER BY prediction_time DESC
                LIMIT ?
            """, (stock_id, limit)).fetchall()
            return [dict(row) for row in rows]

    def get_unevaluated_predictions(
        self,
        before_time: datetime = None
    ) -> List[Dict[str, Any]]:
        """Get predictions that haven't been evaluated yet"""
        before_time = before_time or datetime.now()

        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM predictions
                WHERE evaluated_at IS NULL
                AND target_time <= ?
                ORDER BY target_time ASC
            """, (before_time,)).fetchall()
            return [dict(row) for row in rows]

    # ========== Accuracy Stats CRUD ==========

    def add_accuracy_stats(
        self,
        provider: str,
        timeframe: str,
        total_predictions: int,
        correct_predictions: int,
        avg_confidence: float = None,
        metadata: Dict = None
    ) -> int:
        """Add accuracy statistics entry"""
        accuracy_rate = correct_predictions / total_predictions if total_predictions > 0 else 0.0

        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO accuracy_stats (
                    provider, timeframe, total_predictions, correct_predictions,
                    accuracy_rate, avg_confidence, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                provider, timeframe, total_predictions, correct_predictions,
                accuracy_rate, avg_confidence, json.dumps(metadata) if metadata else None
            ))
            return cursor.lastrowid

    def calculate_accuracy_stats(
        self,
        provider: str = None,
        timeframe: str = '24h'
    ) -> Dict[str, Any]:
        """Calculate accuracy statistics from predictions"""
        timeframe_hours = {
            '1h': 1, '6h': 6, '24h': 24, '7d': 168, '30d': 720
        }.get(timeframe, 24)

        cutoff_time = datetime.now().timestamp() - (timeframe_hours * 3600)
        cutoff_datetime = datetime.fromtimestamp(cutoff_time)

        with self.get_connection() as conn:
            if provider:
                row = conn.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN accuracy = 1.0 THEN 1 ELSE 0 END) as correct,
                        AVG(confidence) as avg_conf,
                        AVG(accuracy) as avg_acc
                    FROM predictions
                    WHERE provider = ?
                    AND evaluated_at IS NOT NULL
                    AND evaluated_at >= ?
                """, (provider, cutoff_datetime)).fetchone()
            else:
                row = conn.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN accuracy = 1.0 THEN 1 ELSE 0 END) as correct,
                        AVG(confidence) as avg_conf,
                        AVG(accuracy) as avg_acc
                    FROM predictions
                    WHERE evaluated_at IS NOT NULL
                    AND evaluated_at >= ?
                """, (cutoff_datetime,)).fetchone()

            if row and row['total'] > 0:
                return {
                    'total_predictions': row['total'],
                    'correct_predictions': row['correct'],
                    'accuracy_rate': row['avg_acc'],
                    'avg_confidence': row['avg_conf']
                }

            return {
                'total_predictions': 0,
                'correct_predictions': 0,
                'accuracy_rate': 0.0,
                'avg_confidence': 0.0
            }

    def get_accuracy_stats(
        self,
        provider: str = None,
        timeframe: str = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get historical accuracy stats"""
        with self.get_connection() as conn:
            query = "SELECT * FROM accuracy_stats WHERE 1=1"
            params = []

            if provider:
                query += " AND provider = ?"
                params.append(provider)

            if timeframe:
                query += " AND timeframe = ?"
                params.append(timeframe)

            query += " ORDER BY calculated_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                result = dict(row)
                if result.get('metadata'):
                    result['metadata'] = json.loads(result['metadata'])
                results.append(result)
            return results

    # ========== Event CRUD (SSE Bridge) ==========

    def _emit_event(self, conn, event_type: str, data: Dict[str, Any]):
        """Internal method to emit an event (requires existing connection)"""
        # Convert datetime objects to ISO format strings for JSON serialization
        serialized_data = {}
        for key, value in data.items():
            if isinstance(value, datetime):
                serialized_data[key] = value.isoformat()
            else:
                serialized_data[key] = value

        conn.execute(
            "INSERT INTO events (event_type, data) VALUES (?, ?)",
            (event_type, json.dumps(serialized_data))
        )

    def get_unprocessed_events(
        self,
        event_type: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get unprocessed events for SSE streaming"""
        with self.get_connection() as conn:
            if event_type:
                rows = conn.execute("""
                    SELECT * FROM events
                    WHERE processed = 0 AND event_type = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                """, (event_type, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM events
                    WHERE processed = 0
                    ORDER BY timestamp ASC
                    LIMIT ?
                """, (limit,)).fetchall()

            results = []
            for row in rows:
                result = dict(row)
                result['data'] = json.loads(result['data'])
                results.append(result)
            return results

    def mark_events_processed(self, event_ids: List[int]) -> bool:
        """Mark events as processed"""
        if not event_ids:
            return False

        placeholders = ','.join('?' * len(event_ids))
        with self.get_connection() as conn:
            cursor = conn.execute(
                f"UPDATE events SET processed = 1 WHERE id IN ({placeholders})",
                event_ids
            )
            return cursor.rowcount > 0

    def cleanup_old_events(self, days: int = 7) -> int:
        """Delete old processed events"""
        cutoff_time = datetime.now().timestamp() - (days * 86400)
        cutoff_datetime = datetime.fromtimestamp(cutoff_time)

        with self.get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE processed = 1 AND timestamp < ?",
                (cutoff_datetime,)
            )
            return cursor.rowcount

    # ========== Utility Methods ==========

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get summary data for dashboard"""
        with self.get_connection() as conn:
            # Current cycle
            current_cycle = conn.execute(
                "SELECT * FROM cycles WHERE status = 'active' ORDER BY start_time DESC LIMIT 1"
            ).fetchone()

            # Total stocks
            total_stocks = conn.execute("SELECT COUNT(*) as count FROM stocks").fetchone()['count']

            # Overall accuracy
            accuracy = conn.execute("""
                SELECT AVG(accuracy) as avg_acc
                FROM predictions
                WHERE accuracy IS NOT NULL
            """).fetchone()

            # Recent predictions
            recent_predictions = conn.execute("""
                SELECT p.*, s.ticker
                FROM predictions p
                JOIN stocks s ON p.stock_id = s.id
                ORDER BY p.prediction_time DESC
                LIMIT 5
            """).fetchall()

            return {
                'current_cycle': dict(current_cycle) if current_cycle else None,
                'total_stocks': total_stocks,
                'overall_accuracy': accuracy['avg_acc'] if accuracy else 0.0,
                'recent_predictions': [dict(p) for p in recent_predictions]
            }

    def get_provider_leaderboard(self) -> List[Dict[str, Any]]:
        """Get provider accuracy leaderboard"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    provider,
                    COUNT(*) as total_predictions,
                    SUM(CASE WHEN accuracy = 1.0 THEN 1 ELSE 0 END) as correct_predictions,
                    AVG(accuracy) as accuracy_rate,
                    AVG(confidence) as avg_confidence
                FROM predictions
                WHERE accuracy IS NOT NULL
                GROUP BY provider
                ORDER BY accuracy_rate DESC
            """).fetchall()
            return [dict(row) for row in rows]

    def emit_event(self, event_type: str, data: Dict[str, Any]) -> int:
        """
        Emit an event to the events table for SSE streaming

        Args:
            event_type: Type of event (e.g., 'prediction', 'cycle_start')
            data: Event data dictionary

        Returns:
            Event ID
        """
        with self.get_connection() as conn:
            self._emit_event(conn, event_type, data)
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_pending_events(self, since_id: int = 0, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get pending events since a given ID for SSE streaming

        Args:
            since_id: Get events with ID greater than this
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries
        """
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM events
                WHERE id > ? AND processed = 0
                ORDER BY id ASC
                LIMIT ?
            """, (since_id, limit)).fetchall()

            results = []
            for row in rows:
                result = dict(row)
                # Parse JSON data
                if result['data']:
                    result['data'] = json.loads(result['data'])
                results.append(result)
            return results

    def mark_event_processed(self, event_id: int) -> bool:
        """
        Mark a single event as processed

        Args:
            event_id: ID of event to mark

        Returns:
            True if successful
        """
        return self.mark_events_processed([event_id])

    def fail_cycle(self, cycle_id: int, error: str) -> bool:
        """
        Mark a cycle as failed

        Args:
            cycle_id: ID of cycle to mark failed
            error: Error message

        Returns:
            True if successful
        """
        with self.get_connection() as conn:
            cursor = conn.execute("""
                UPDATE cycles
                SET status = 'failed',
                    end_time = ?
                WHERE id = ?
            """, (datetime.now(), cycle_id))
            return cursor.rowcount > 0

    def mark_cycle_failed(self, cycle_id: int, reason: str) -> bool:
        """
        Mark a cycle as failed (alias for fail_cycle for backward compatibility)

        Args:
            cycle_id: ID of cycle to mark failed
            reason: Reason for failure

        Returns:
            True if successful
        """
        return self.fail_cycle(cycle_id, reason)

    def record_price(self, stock_id: int, cycle_id: int, price: float, **kwargs) -> int:
        """
        Record a price snapshot (alias for add_price)

        Args:
            stock_id: Stock ID
            cycle_id: Cycle ID
            price: Stock price
            **kwargs: Additional fields (volume, change_percent, source)

        Returns:
            Price record ID
        """
        return self.add_price(
            stock_id=stock_id,
            cycle_id=cycle_id,
            price=price,
            volume=kwargs.get('volume'),
            change_percent=kwargs.get('change_percent'),
            source=kwargs.get('source', 'yfinance')
        )

    def add_price_snapshot(self, stock_id: int, cycle_id: int, price: float, volume: int = None, change_percent: float = None) -> int:
        """
        Add a price snapshot (alias for add_price)

        Args:
            stock_id: Stock ID
            cycle_id: Cycle ID
            price: Stock price
            volume: Trading volume
            change_percent: Percent change

        Returns:
            Price record ID
        """
        return self.add_price(
            stock_id=stock_id,
            cycle_id=cycle_id,
            price=price,
            volume=volume,
            change_percent=change_percent
        )


# Singleton instance
_db_instance = None

def get_db() -> ForesightDB:
    """Get singleton database instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = ForesightDB()
    return _db_instance
