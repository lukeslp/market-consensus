"""
Database management for Foresight
SQLite with WAL mode for concurrent access
"""
import sqlite3
from flask import g, current_app
from contextlib import contextmanager
import threading

_db_lock = threading.Lock()


def get_db():
    """Get database connection from Flask g object"""
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DB_PATH'],
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False
        )
        g.db.row_factory = sqlite3.Row

        # Enable WAL mode for concurrent reads
        g.db.execute('PRAGMA journal_mode=WAL')
        g.db.execute('PRAGMA busy_timeout=5000')

    return g.db


def close_db(e=None):
    """Close database connection"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


@contextmanager
def get_db_context():
    """Context manager for database operations outside request context"""
    conn = sqlite3.connect(
        current_app.config['DB_PATH'],
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=5000')

    try:
        yield conn
    finally:
        conn.close()


def init_db(app):
    """Initialize database schema"""
    with app.app_context():
        db = get_db()

        # Cycles table - prediction cycles
        db.execute('''
            CREATE TABLE IF NOT EXISTS cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'running',
                stocks_discovered INTEGER DEFAULT 0,
                predictions_made INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Stocks table - discovered stocks
        db.execute('''
            CREATE TABLE IF NOT EXISTS stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT,
                current_price REAL,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cycle_id) REFERENCES cycles(id),
                UNIQUE(cycle_id, symbol)
            )
        ''')

        # Predictions table - LLM predictions
        db.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                prediction TEXT NOT NULL,
                confidence REAL,
                reasoning TEXT,
                predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (stock_id) REFERENCES stocks(id)
            )
        ''')

        # Results table - actual outcomes
        db.execute('''
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_id INTEGER NOT NULL,
                actual_outcome TEXT,
                price_change REAL,
                was_correct BOOLEAN,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (prediction_id) REFERENCES predictions(id)
            )
        ''')

        # Create indexes for common queries
        db.execute('''
            CREATE INDEX IF NOT EXISTS idx_cycles_status
            ON cycles(status)
        ''')

        db.execute('''
            CREATE INDEX IF NOT EXISTS idx_stocks_cycle
            ON stocks(cycle_id)
        ''')

        db.execute('''
            CREATE INDEX IF NOT EXISTS idx_predictions_stock
            ON predictions(stock_id)
        ''')

        db.execute('''
            CREATE INDEX IF NOT EXISTS idx_results_prediction
            ON results(prediction_id)
        ''')

        db.commit()
        app.logger.info('Database initialized with WAL mode enabled')
