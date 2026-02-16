"""
Pytest configuration and shared fixtures
Provides test database, Flask app, and mock LLM providers
"""
import pytest
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Add shared library to path
if '/home/coolhand/shared' not in sys.path:
    sys.path.insert(0, '/home/coolhand/shared')

from db import ForesightDB
from app import create_app
from app.config import Config


class TestConfig(Config):
    """Test configuration"""
    TESTING = True
    DEBUG = True
    # Use in-memory database for tests
    DB_PATH = ':memory:'
    # Disable SSE retry for faster tests
    SSE_RETRY = 100


@pytest.fixture(scope='session')
def temp_db_file():
    """Create temporary database file for session"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)
    for suffix in ['-shm', '-wal']:
        wal_file = db_path + suffix
        if os.path.exists(wal_file):
            os.unlink(wal_file)


@pytest.fixture
def db(temp_db_file):
    """Provide fresh ForesightDB instance for each test"""
    database = ForesightDB(temp_db_file)
    yield database
    # Clean up between tests
    with database.get_connection() as conn:
        cursor = conn.cursor()
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        # Clear all tables
        for table in tables:
            if table != 'sqlite_sequence':
                cursor.execute(f"DELETE FROM {table}")


@pytest.fixture
def app():
    """Provide Flask application with test config"""
    app = create_app(TestConfig)
    return app


@pytest.fixture
def client(app):
    """Provide Flask test client"""
    return app.test_client()


@pytest.fixture
def app_context(app):
    """Provide Flask application context"""
    with app.app_context():
        yield app


@pytest.fixture
def mock_provider():
    """Mock LLM provider for testing"""
    provider = Mock()
    provider.model = 'mock-model-1'
    provider.generate = Mock(return_value='{"prediction": "UP", "confidence": 0.75, "reasoning": "Test reasoning"}')
    return provider


@pytest.fixture
def mock_provider_factory(monkeypatch, mock_provider):
    """Mock ProviderFactory to return mock provider"""
    def mock_get_provider(name):
        return mock_provider

    # This requires llm_providers to be imported
    from llm_providers import ProviderFactory
    monkeypatch.setattr(ProviderFactory, 'get_provider', staticmethod(mock_get_provider))

    return mock_provider


@pytest.fixture
def mock_yfinance(monkeypatch):
    """Mock yfinance for stock data fetching"""
    mock_ticker = MagicMock()
    mock_ticker.info = {
        'symbol': 'AAPL',
        'shortName': 'Apple Inc.',
        'regularMarketPrice': 150.25,
        'regularMarketVolume': 1000000,
        'regularMarketChangePercent': 2.5
    }

    # Mock historical data
    import pandas as pd
    dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
    mock_ticker.history.return_value = pd.DataFrame({
        'Close': [150 + i for i in range(30)],
        'Volume': [1000000] * 30
    }, index=dates)

    def mock_ticker_func(symbol):
        return mock_ticker

    # Mock yfinance.Ticker
    mock_yf = Mock()
    mock_yf.Ticker = mock_ticker_func

    monkeypatch.setattr('app.services.stock_service.yf', mock_yf)

    return mock_ticker


@pytest.fixture
def sample_cycle(db):
    """Create sample prediction cycle"""
    cycle_id = db.create_cycle()
    return db.get_cycle(cycle_id)


@pytest.fixture
def sample_stock(db):
    """Create sample stock"""
    stock_id = db.add_stock('AAPL', 'Apple Inc.', {'sector': 'Technology'})
    return db.get_stock('AAPL')


@pytest.fixture
def sample_prediction(db, sample_cycle, sample_stock):
    """Create sample prediction"""
    pred_id = db.add_prediction(
        cycle_id=sample_cycle['id'],
        stock_id=sample_stock['id'],
        provider='anthropic',
        predicted_direction='up',
        confidence=0.75,
        initial_price=150.0,
        target_time=datetime.now() + timedelta(hours=1),
        reasoning='Test prediction'
    )
    return db.get_prediction(pred_id)


# Pytest markers for test categorization
def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated)")
    config.addinivalue_line("markers", "integration: Integration tests (medium speed)")
    config.addinivalue_line("markers", "api: API endpoint tests")
    config.addinivalue_line("markers", "database: Database tests")
    config.addinivalue_line("markers", "slow: Slow tests (skip with -m 'not slow')")
