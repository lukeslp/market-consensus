"""
Worker scheduling tests
"""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from app import worker as worker_module
from db import ForesightDB


class _DummyStockService:
    pass


class _DummyPredictionService:
    def __init__(self, _config):
        pass


@pytest.fixture
def schedule_worker(monkeypatch):
    monkeypatch.setattr(worker_module, 'StockService', _DummyStockService)
    monkeypatch.setattr(worker_module, 'PredictionService', _DummyPredictionService)

    config = {
        'DB_PATH': '/tmp/test_foresight_schedule.db',
        'MARKET_TIMEZONE': 'America/New_York',
        'USE_NYSE_CALENDAR': True,
        'MARKET_OPEN_HOUR': 9,
        'MARKET_OPEN_MINUTE': 30,
        'MARKET_CLOSE_HOUR': 16,
        'MARKET_CLOSE_MINUTE': 0,
        'NYSE_EARLY_CLOSE_HOUR': 13,
        'NYSE_EARLY_CLOSE_MINUTE': 0,
        'MARKET_OPEN_INTERVAL_SECONDS': 1800,
        'OVERNIGHT_CHECK_TIMES': '20:00,06:00',
        'OVERNIGHT_LOOKAHEAD_HOURS': 18,
        'SCHEDULE_POLL_SECONDS': 20,
    }
    return worker_module.PredictionWorker(config)


@pytest.mark.unit
def test_next_run_is_half_hour_during_market_hours(schedule_worker):
    tz = ZoneInfo('America/New_York')
    after_dt = datetime(2025, 1, 8, 10, 5, tzinfo=tz)  # Wednesday

    run_at, reason = schedule_worker._next_scheduled_run(after_dt=after_dt)

    assert run_at == datetime(2025, 1, 8, 10, 30, tzinfo=tz)
    assert reason == 'market_open'


@pytest.mark.unit
def test_next_run_after_close_uses_evening_overnight_slot(schedule_worker):
    tz = ZoneInfo('America/New_York')
    after_dt = datetime(2025, 1, 8, 16, 5, tzinfo=tz)  # Wednesday

    run_at, reason = schedule_worker._next_scheduled_run(after_dt=after_dt)

    assert run_at == datetime(2025, 1, 8, 20, 0, tzinfo=tz)
    assert reason == 'overnight_20:00'


@pytest.mark.unit
def test_next_run_overnight_prefers_morning_slot(schedule_worker):
    tz = ZoneInfo('America/New_York')
    after_dt = datetime(2025, 1, 9, 0, 15, tzinfo=tz)  # Thursday just after midnight

    run_at, reason = schedule_worker._next_scheduled_run(after_dt=after_dt)

    assert run_at == datetime(2025, 1, 9, 6, 0, tzinfo=tz)
    assert reason == 'overnight_06:00'


@pytest.mark.unit
def test_friday_after_close_skips_to_sunday_evening(schedule_worker):
    tz = ZoneInfo('America/New_York')
    after_dt = datetime(2025, 1, 10, 16, 5, tzinfo=tz)  # Friday

    run_at, reason = schedule_worker._next_scheduled_run(after_dt=after_dt)

    assert run_at == datetime(2025, 1, 12, 20, 0, tzinfo=tz)  # Sunday evening
    assert reason == 'overnight_20:00'


@pytest.mark.unit
def test_new_year_holiday_skips_to_next_trading_open(schedule_worker):
    tz = ZoneInfo('America/New_York')
    after_dt = datetime(2026, 1, 1, 8, 0, tzinfo=tz)  # New Year's Day (holiday)

    run_at, reason = schedule_worker._next_scheduled_run(after_dt=after_dt)

    # Holiday daytime should still use low-frequency overnight refresh before next open.
    assert run_at == datetime(2026, 1, 1, 20, 0, tzinfo=tz)
    assert reason == 'overnight_20:00'


@pytest.mark.unit
def test_day_after_thanksgiving_uses_early_close_session(schedule_worker):
    tz = ZoneInfo('America/New_York')
    # 2025-11-28 is the day after Thanksgiving (NYSE early close at 1:00 PM ET).
    run_at_midday, reason_midday = schedule_worker._next_scheduled_run(
        after_dt=datetime(2025, 11, 28, 12, 15, tzinfo=tz)
    )
    run_at_after_close, reason_after_close = schedule_worker._next_scheduled_run(
        after_dt=datetime(2025, 11, 28, 12, 45, tzinfo=tz)
    )

    assert run_at_midday == datetime(2025, 11, 28, 12, 30, tzinfo=tz)
    assert reason_midday == 'market_open'
    # Weekend gap means next overnight refresh should be Sunday evening.
    assert run_at_after_close == datetime(2025, 11, 30, 20, 0, tzinfo=tz)
    assert reason_after_close == 'overnight_20:00'


@pytest.mark.unit
def test_overnight_light_mode_runs_periodic_full_debate(schedule_worker):
    schedule_worker.overnight_light_mode = True
    schedule_worker.overnight_full_debate_every = 3
    schedule_worker.overnight_light_provider_order = ['xai', 'perplexity', 'mistral']

    order_1, mode_1 = schedule_worker._provider_order_for_run('overnight_20:00')
    order_2, mode_2 = schedule_worker._provider_order_for_run('overnight_06:00')
    order_3, mode_3 = schedule_worker._provider_order_for_run('overnight_20:00')

    assert order_1 == ['xai', 'perplexity', 'mistral']
    assert mode_1 == 'light_overnight'
    assert order_2 == ['xai', 'perplexity', 'mistral']
    assert mode_2 == 'light_overnight'
    assert order_3 == schedule_worker.FULL_PROVIDER_ORDER
    assert mode_3 == 'full_overnight_refresh'


@pytest.mark.unit
def test_market_open_reason_uses_full_provider_order(schedule_worker):
    order, mode = schedule_worker._provider_order_for_run('market_open')

    assert order == schedule_worker.FULL_PROVIDER_ORDER
    assert mode == 'full_market'


@pytest.mark.unit
def test_discovery_includes_configured_crypto(monkeypatch, tmp_path):
    class _CryptoStockService:
        @staticmethod
        def validate_symbol(_symbol):
            return True

        @staticmethod
        def fetch_stock_info(symbol):
            return {
                'name': symbol,
                'current_price': 100.0,
                'sector': 'Digital Assets',
                'industry': 'Crypto',
                'market_cap': 1000000,
            }

    class _DiscoveryPredictionService:
        def __init__(self, _config):
            pass

        @staticmethod
        def build_provider_weights(_performance_map):
            return {'xai': 1.0}

        @staticmethod
        def discover_stocks_debate(count, provider_weights, stage_order=None):
            assert count >= 0
            assert isinstance(provider_weights, dict)
            assert stage_order == ['xai']
            return []

    monkeypatch.setattr(worker_module, 'StockService', _CryptoStockService)
    monkeypatch.setattr(worker_module, 'PredictionService', _DiscoveryPredictionService)

    config = {
        'DB_PATH': str(tmp_path / 'crypto_cycle.db'),
        'MARKET_TIMEZONE': 'America/New_York',
        'USE_NYSE_CALENDAR': False,
        'MARKET_OPEN_HOUR': 9,
        'MARKET_OPEN_MINUTE': 30,
        'MARKET_CLOSE_HOUR': 16,
        'MARKET_CLOSE_MINUTE': 0,
        'NYSE_EARLY_CLOSE_HOUR': 13,
        'NYSE_EARLY_CLOSE_MINUTE': 0,
        'MARKET_OPEN_INTERVAL_SECONDS': 1800,
        'OVERNIGHT_CHECK_TIMES': '20:00,06:00',
        'OVERNIGHT_LOOKAHEAD_HOURS': 18,
        'SCHEDULE_POLL_SECONDS': 20,
        'MAX_STOCKS': 0,
        'INCLUDE_CRYPTO': True,
        'MAX_CRYPTO_SYMBOLS': 2,
        'CRYPTO_SYMBOLS': 'BTC-USD,ETH-USD,SOL-USD',
    }

    worker = worker_module.PredictionWorker(config)
    db = ForesightDB(config['DB_PATH'])
    cycle_id = db.create_cycle()

    symbols = worker._discover_stocks(db, cycle_id, provider_order=['xai'])

    assert symbols == ['BTC-USD', 'ETH-USD']


@pytest.mark.unit
def test_recover_interrupted_cycles_marks_active_as_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(worker_module, 'StockService', _DummyStockService)
    monkeypatch.setattr(worker_module, 'PredictionService', _DummyPredictionService)

    db_path = str(tmp_path / 'recover_cycles.db')
    config = {
        'DB_PATH': db_path,
        'MARKET_TIMEZONE': 'America/New_York',
        'USE_NYSE_CALENDAR': False,
        'MARKET_OPEN_HOUR': 9,
        'MARKET_OPEN_MINUTE': 30,
        'MARKET_CLOSE_HOUR': 16,
        'MARKET_CLOSE_MINUTE': 0,
        'NYSE_EARLY_CLOSE_HOUR': 13,
        'NYSE_EARLY_CLOSE_MINUTE': 0,
        'MARKET_OPEN_INTERVAL_SECONDS': 1800,
        'OVERNIGHT_CHECK_TIMES': '20:00,06:00',
        'OVERNIGHT_LOOKAHEAD_HOURS': 18,
        'SCHEDULE_POLL_SECONDS': 20,
    }

    db = ForesightDB(db_path)
    first = db.create_cycle()
    second = db.create_cycle()

    worker = worker_module.PredictionWorker(config)
    worker._recover_interrupted_cycles()

    assert db.get_cycle(first)['status'] == 'failed'
    assert db.get_cycle(second)['status'] == 'failed'


@pytest.mark.unit
def test_process_stock_continues_after_provider_failure(monkeypatch):
    class _StockServiceForProcess:
        @staticmethod
        def fetch_historical_data(_symbol, days=30):
            return {
                'close': [100.0, 101.0, 102.0],
                'volume': [1000, 1200, 1100],
                'dates': ['2026-02-16', '2026-02-17', '2026-02-18'],
            }

    class _PredictionServiceForProcess:
        def __init__(self, _config):
            pass

        @staticmethod
        def build_provider_weights(_performance_map):
            return {'xai': 1.0, 'gemini': 1.0}

        @staticmethod
        def generate_prediction_swarm(_symbol, _stock_data, provider_name):
            if provider_name == 'xai':
                raise RuntimeError('xai unavailable')
            return {
                'provider': provider_name,
                'prediction': 'up',
                'confidence': 0.7,
                'reasoning': 'fallback provider succeeded',
            }

        @staticmethod
        def synthesize_council_swarm(*_args, **_kwargs):
            return None

    class _FakeDB:
        def __init__(self):
            self.predictions = []

        @staticmethod
        def get_stock(_symbol):
            return {'id': 1}

        @staticmethod
        def get_provider_leaderboard():
            return []

        def add_prediction(self, **kwargs):
            self.predictions.append(kwargs)
            return len(self.predictions)

    monkeypatch.setattr(worker_module, 'StockService', _StockServiceForProcess)
    monkeypatch.setattr(worker_module, 'PredictionService', _PredictionServiceForProcess)

    config = {
        'DB_PATH': '/tmp/test_foresight_process.db',
        'MARKET_TIMEZONE': 'America/New_York',
        'USE_NYSE_CALENDAR': False,
        'MARKET_OPEN_HOUR': 9,
        'MARKET_OPEN_MINUTE': 30,
        'MARKET_CLOSE_HOUR': 16,
        'MARKET_CLOSE_MINUTE': 0,
        'NYSE_EARLY_CLOSE_HOUR': 13,
        'NYSE_EARLY_CLOSE_MINUTE': 0,
        'MARKET_OPEN_INTERVAL_SECONDS': 1800,
        'OVERNIGHT_CHECK_TIMES': '20:00,06:00',
        'OVERNIGHT_LOOKAHEAD_HOURS': 18,
        'SCHEDULE_POLL_SECONDS': 20,
        'MAX_STOCKS': 5,
        'LOOKBACK_DAYS': 30,
    }

    worker = worker_module.PredictionWorker(config)
    db = _FakeDB()

    worker._process_stock(
        db,
        cycle_id=1,
        symbol='AAPL',
        provider_groups=[('core', ['xai', 'gemini'])],
        synthesis_order=['xai', 'gemini']
    )

    providers = [row['provider'] for row in db.predictions]
    assert 'gemini' in providers


@pytest.mark.unit
def test_cycle_blocklist_skips_rate_limited_provider(monkeypatch):
    class _StockServiceForBlocklist:
        @staticmethod
        def fetch_historical_data(_symbol, days=30):
            return {
                'close': [100.0, 101.0, 102.0],
                'volume': [1000, 1200, 1100],
                'dates': ['2026-02-16', '2026-02-17', '2026-02-18'],
            }

    class _PredictionServiceForBlocklist:
        def __init__(self, _config):
            self.calls = []

        @staticmethod
        def build_provider_weights(_performance_map):
            return {'xai': 1.0, 'cohere': 0.6}

        def generate_prediction_swarm(self, symbol, _stock_data, provider_name):
            self.calls.append((symbol, provider_name))
            if provider_name == 'cohere':
                return None
            return {
                'provider': provider_name,
                'prediction': 'up',
                'confidence': 0.7,
                'reasoning': 'ok',
            }

        @staticmethod
        def get_provider_runtime_status():
            return {
                'cohere': {
                    'healthy': False,
                    'last_error': 'status_code: 429 trial key limit reached',
                    'last_failed_at': '2026-02-18T18:31:41'
                }
            }

        @staticmethod
        def synthesize_council_swarm(*_args, **_kwargs):
            return None

    class _FakeDB:
        def __init__(self):
            self.predictions = []

        @staticmethod
        def get_stock(_symbol):
            return {'id': 1}

        @staticmethod
        def get_provider_leaderboard():
            return []

        def add_prediction(self, **kwargs):
            self.predictions.append(kwargs)
            return len(self.predictions)

    monkeypatch.setattr(worker_module, 'StockService', _StockServiceForBlocklist)
    monkeypatch.setattr(worker_module, 'PredictionService', _PredictionServiceForBlocklist)

    config = {
        'DB_PATH': '/tmp/test_foresight_blocklist.db',
        'MARKET_TIMEZONE': 'America/New_York',
        'USE_NYSE_CALENDAR': False,
        'MARKET_OPEN_HOUR': 9,
        'MARKET_OPEN_MINUTE': 30,
        'MARKET_CLOSE_HOUR': 16,
        'MARKET_CLOSE_MINUTE': 0,
        'NYSE_EARLY_CLOSE_HOUR': 13,
        'NYSE_EARLY_CLOSE_MINUTE': 0,
        'MARKET_OPEN_INTERVAL_SECONDS': 1800,
        'OVERNIGHT_CHECK_TIMES': '20:00,06:00',
        'OVERNIGHT_LOOKAHEAD_HOURS': 18,
        'SCHEDULE_POLL_SECONDS': 20,
        'MAX_STOCKS': 5,
        'LOOKBACK_DAYS': 30,
    }

    worker = worker_module.PredictionWorker(config)
    db = _FakeDB()
    blocklist = set()

    worker._process_stock(
        db,
        cycle_id=1,
        symbol='AAPL',
        provider_groups=[('core', ['xai']), ('side', ['cohere'])],
        synthesis_order=['xai', 'cohere'],
        provider_blocklist=blocklist
    )
    worker._process_stock(
        db,
        cycle_id=1,
        symbol='MSFT',
        provider_groups=[('core', ['xai']), ('side', ['cohere'])],
        synthesis_order=['xai', 'cohere'],
        provider_blocklist=blocklist
    )

    cohere_calls = [call for call in worker.prediction_service.calls if call[1] == 'cohere']
    assert len(cohere_calls) == 1


@pytest.mark.unit
def test_bootstrap_cycle_blocklist_from_runtime(monkeypatch):
    class _StockServiceForBootstrap:
        pass

    class _PredictionServiceForBootstrap:
        def __init__(self, _config):
            pass

        @staticmethod
        def get_provider_runtime_status():
            return {
                'cohere': {
                    'healthy': False,
                    'last_error': 'status_code: 429 trial key limit reached',
                    'last_failed_at': '2026-02-18T18:31:41'
                },
                'gemini': {
                    'healthy': False,
                    'last_error': 'socket timeout',
                    'last_failed_at': '2026-02-18T18:31:42'
                },
                'xai': {
                    'healthy': True,
                    'last_error': None,
                    'last_failed_at': None
                }
            }

    monkeypatch.setattr(worker_module, 'StockService', _StockServiceForBootstrap)
    monkeypatch.setattr(worker_module, 'PredictionService', _PredictionServiceForBootstrap)

    config = {
        'DB_PATH': '/tmp/test_foresight_bootstrap_blocklist.db',
        'MARKET_TIMEZONE': 'America/New_York',
        'USE_NYSE_CALENDAR': False,
        'MARKET_OPEN_HOUR': 9,
        'MARKET_OPEN_MINUTE': 30,
        'MARKET_CLOSE_HOUR': 16,
        'MARKET_CLOSE_MINUTE': 0,
        'NYSE_EARLY_CLOSE_HOUR': 13,
        'NYSE_EARLY_CLOSE_MINUTE': 0,
        'MARKET_OPEN_INTERVAL_SECONDS': 1800,
        'OVERNIGHT_CHECK_TIMES': '20:00,06:00',
        'OVERNIGHT_LOOKAHEAD_HOURS': 18,
        'SCHEDULE_POLL_SECONDS': 20,
    }

    worker = worker_module.PredictionWorker(config)
    blocklist = worker._bootstrap_cycle_blocklist(['xai', 'gemini', 'cohere'])

    assert blocklist == {'cohere'}


@pytest.mark.unit
def test_cluster_status_uses_fresh_heartbeat(schedule_worker, monkeypatch):
    monkeypatch.setattr(
        schedule_worker,
        '_read_heartbeat',
        lambda: {
            'fresh': True,
            'age_seconds': 2.5,
            'pid': 4321,
            'running': True,
            'alive': True,
            'current_cycle_id': 987,
            'last_cycle_time': 123.45,
            'total_cycles_completed': 12,
            'next_scheduled_run': '2026-02-19T09:30:00-05:00',
            'next_scheduled_reason': 'market_open',
        }
    )

    status = schedule_worker.get_cluster_status()

    assert status['status_source'] == 'heartbeat'
    assert status['running'] is True
    assert status['alive'] is True
    assert status['current_cycle_id'] == 987
    assert status['scheduler_pid'] == 4321
    assert status['heartbeat_fresh'] is True


@pytest.mark.unit
def test_cluster_status_falls_back_to_local_when_stale(schedule_worker, monkeypatch):
    monkeypatch.setattr(
        schedule_worker,
        '_read_heartbeat',
        lambda: {
            'fresh': False,
            'age_seconds': 999.0,
            'pid': 4321,
            'running': True,
            'alive': True,
        }
    )

    status = schedule_worker.get_cluster_status()

    assert status['status_source'] == 'local'
    assert status['running'] == status['local_running']
    assert status['alive'] == status['local_alive']
    assert status['heartbeat_fresh'] is False
