"""
Worker scheduling tests
"""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from app import worker as worker_module


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
