"""
Background worker for stock prediction cycles
"""
import time
import json
import os
import logging
import threading
from typing import Optional, List, Dict, Tuple, Set
from datetime import date as date_cls, datetime, timedelta
from zoneinfo import ZoneInfo

from db import ForesightDB
from .services.stock_service import StockService
from .services.prediction_service import PredictionService

logger = logging.getLogger(__name__)


class PredictionWorker:
    """Background worker that executes prediction cycles on a schedule"""
    FULL_PROVIDER_ORDER = ['xai', 'gemini', 'anthropic', 'openai', 'perplexity', 'mistral', 'cohere']
    PROVIDER_STAGE = {
        'xai': 'core',
        'gemini': 'core',
        'anthropic': 'join',
        'openai': 'join',
        'perplexity': 'join',
        'mistral': 'side',
        'cohere': 'side',
    }

    def __init__(self, config: Dict):
        """
        Initialize the worker

        Args:
            config: Application configuration dictionary
        """
        self.config = config
        self.db_path = config['DB_PATH']
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.current_cycle_id: Optional[int] = None
        self.last_cycle_time: float = 0
        self.total_cycles_completed: int = 0
        self.next_scheduled_run: Optional[datetime] = None
        self.next_scheduled_reason: Optional[str] = None
        self.scheduler_lock_acquired: bool = False
        self.heartbeat_path = config.get('WORKER_HEARTBEAT_PATH', '/tmp/foresight.worker.heartbeat')
        self.heartbeat_max_age_seconds = max(15, int(config.get('WORKER_HEARTBEAT_MAX_AGE_SECONDS', 120)))
        self.provider_health_cooldown_seconds = max(
            0,
            int(config.get('PROVIDER_HEALTH_COOLDOWN_SECONDS', 3600))
        )

        # Scheduling configuration
        self.market_tz = ZoneInfo(config.get('MARKET_TIMEZONE', 'America/New_York'))
        self.market_open_hour = int(config.get('MARKET_OPEN_HOUR', 9))
        self.market_open_minute = int(config.get('MARKET_OPEN_MINUTE', 30))
        self.market_close_hour = int(config.get('MARKET_CLOSE_HOUR', 16))
        self.market_close_minute = int(config.get('MARKET_CLOSE_MINUTE', 0))
        self.nyse_early_close_hour = int(config.get('NYSE_EARLY_CLOSE_HOUR', 13))
        self.nyse_early_close_minute = int(config.get('NYSE_EARLY_CLOSE_MINUTE', 0))
        use_nyse_raw = config.get('USE_NYSE_CALENDAR', True)
        if isinstance(use_nyse_raw, str):
            self.use_nyse_calendar = use_nyse_raw.lower() not in ('0', 'false', 'no')
        else:
            self.use_nyse_calendar = bool(use_nyse_raw)
        self.market_open_interval_seconds = max(60, int(config.get('MARKET_OPEN_INTERVAL_SECONDS', 1800)))
        self.overnight_lookahead_hours = max(1, int(config.get('OVERNIGHT_LOOKAHEAD_HOURS', 18)))
        self.schedule_poll_seconds = max(5, int(config.get('SCHEDULE_POLL_SECONDS', 20)))
        self.overnight_check_times = self._parse_overnight_check_times(
            config.get('OVERNIGHT_CHECK_TIMES', '20:00,06:00')
        )
        overnight_light_raw = config.get('OVERNIGHT_LIGHT_MODE', True)
        if isinstance(overnight_light_raw, str):
            self.overnight_light_mode = overnight_light_raw.lower() not in ('0', 'false', 'no')
        else:
            self.overnight_light_mode = bool(overnight_light_raw)
        self.overnight_full_debate_every = max(1, int(config.get('OVERNIGHT_FULL_DEBATE_EVERY', 3)))
        self.overnight_light_provider_order = self._parse_provider_order(
            config.get('OVERNIGHT_LIGHT_PROVIDER_ORDER', 'xai,perplexity,mistral')
        )
        include_crypto_raw = config.get('INCLUDE_CRYPTO', True)
        if isinstance(include_crypto_raw, str):
            self.include_crypto = include_crypto_raw.lower() not in ('0', 'false', 'no')
        else:
            self.include_crypto = bool(include_crypto_raw)
        self.max_crypto_symbols = max(0, int(config.get('MAX_CRYPTO_SYMBOLS', 3)))
        self.crypto_symbols = self._parse_symbol_list(config.get('CRYPTO_SYMBOLS', 'BTC-USD,ETH-USD,SOL-USD'))
        self.crypto_symbol_set = set(self.crypto_symbols)
        self._overnight_cycles_since_full = 0
        self._nyse_holiday_cache: Dict[int, Set[date_cls]] = {}
        self._nyse_session_cache: Dict[date_cls, Optional[Tuple[datetime, datetime]]] = {}
        self._nyse_calendar = None
        self._init_nyse_calendar()

        # Initialize services
        self.stock_service = StockService()
        self.prediction_service = PredictionService(config)

    def start(self):
        """Start the background worker thread"""
        if self.running:
            logger.warning('Worker already running')
            return

        self.running = True
        self.thread = threading.Thread(
            target=self._run_worker,
            daemon=True,
            name='PredictionWorker'
        )
        self.thread.start()
        self._write_heartbeat()
        logger.info('Prediction worker started')

    def is_alive(self) -> bool:
        """Check if the worker thread is running"""
        return self.running and self.thread and self.thread.is_alive()

    def stop(self):
        """Stop the background worker gracefully"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self._write_heartbeat()
        logger.info('Prediction worker stopped')

    def get_status(self) -> dict:
        """Return current worker state for the /api/worker/status endpoint."""
        return {
            'running': self.running,
            'alive': self.thread.is_alive() if self.thread else False,
            'current_cycle_id': self.current_cycle_id,
            'last_cycle_time': self.last_cycle_time,
            'total_cycles_completed': self.total_cycles_completed,
            'next_scheduled_run': self.next_scheduled_run.isoformat() if self.next_scheduled_run else None,
            'next_scheduled_reason': self.next_scheduled_reason,
            'pid': os.getpid(),
            'scheduler_lock_acquired': self.scheduler_lock_acquired,
        }

    def get_cluster_status(self) -> dict:
        """
        Return process-safe worker status.
        In Gunicorn multi-worker mode, only one process owns the scheduler lock.
        """
        status = self.get_status()
        status['local_running'] = status['running']
        status['local_alive'] = status['alive']
        status['status_source'] = 'local'
        status['heartbeat_fresh'] = False
        status['heartbeat_age_seconds'] = None
        status['scheduler_pid'] = os.getpid() if self.scheduler_lock_acquired else None

        heartbeat = self._read_heartbeat()
        if not heartbeat:
            return status

        status['heartbeat_fresh'] = bool(heartbeat.get('fresh'))
        status['heartbeat_age_seconds'] = heartbeat.get('age_seconds')
        status['scheduler_pid'] = heartbeat.get('pid')

        if not heartbeat.get('fresh'):
            return status

        status['running'] = bool(heartbeat.get('running'))
        status['alive'] = bool(heartbeat.get('alive'))
        status['current_cycle_id'] = heartbeat.get('current_cycle_id')
        status['last_cycle_time'] = heartbeat.get('last_cycle_time')
        status['total_cycles_completed'] = heartbeat.get('total_cycles_completed', status['total_cycles_completed'])
        status['next_scheduled_run'] = heartbeat.get('next_scheduled_run')
        status['next_scheduled_reason'] = heartbeat.get('next_scheduled_reason')
        status['status_source'] = 'heartbeat'
        return status

    def _heartbeat_payload(self) -> Dict:
        return {
            'pid': os.getpid(),
            'updated_ts': time.time(),
            'updated_at': datetime.utcnow().isoformat() + 'Z',
            'running': self.running,
            'alive': self.thread.is_alive() if self.thread else False,
            'current_cycle_id': self.current_cycle_id,
            'last_cycle_time': self.last_cycle_time,
            'total_cycles_completed': self.total_cycles_completed,
            'next_scheduled_run': self.next_scheduled_run.isoformat() if self.next_scheduled_run else None,
            'next_scheduled_reason': self.next_scheduled_reason,
        }

    def _write_heartbeat(self):
        """Persist worker heartbeat for cross-process status checks."""
        if not self.scheduler_lock_acquired:
            return
        try:
            with open(self.heartbeat_path, 'w', encoding='utf-8') as f:
                json.dump(self._heartbeat_payload(), f)
        except Exception as e:
            logger.debug(f'Failed to write worker heartbeat: {e}')

    def _read_heartbeat(self) -> Optional[Dict]:
        try:
            with open(self.heartbeat_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.debug(f'Failed to read worker heartbeat: {e}')
            return None

        try:
            updated_ts = float(payload.get('updated_ts') or 0)
            age_seconds = max(0.0, time.time() - updated_ts) if updated_ts > 0 else float('inf')
            payload['age_seconds'] = age_seconds
            payload['fresh'] = age_seconds <= self.heartbeat_max_age_seconds
        except Exception:
            payload['age_seconds'] = None
            payload['fresh'] = False
        return payload

    def _recover_interrupted_cycles(self):
        """
        Mark any leftover active cycles as failed on scheduler startup.
        Active cycles cannot survive a process restart safely.
        """
        db = ForesightDB(self.db_path)
        try:
            with db.get_connection() as conn:
                rows = conn.execute(
                    "SELECT id FROM cycles WHERE status = 'active' ORDER BY start_time DESC"
                ).fetchall()
            if not rows:
                return

            recovered_ids = []
            for row in rows:
                cycle_id = int(row['id'])
                if db.fail_cycle(cycle_id, 'Recovered after worker restart'):
                    recovered_ids.append(cycle_id)
            if recovered_ids:
                logger.warning(
                    f'Marked interrupted active cycles as failed on startup: {recovered_ids}'
                )
        except Exception as e:
            logger.error(f'Failed to recover interrupted cycles: {e}', exc_info=True)

    @staticmethod
    def _seconds_since_timestamp(raw_timestamp: Optional[str]) -> Optional[float]:
        """Return age in seconds for an ISO/SQLite timestamp string."""
        if not raw_timestamp:
            return None

        text = str(raw_timestamp).strip()
        parsed: Optional[datetime] = None
        try:
            parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except Exception:
            for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except Exception:
                    continue
        if parsed is None:
            return None

        if parsed.tzinfo is not None:
            now = datetime.now(parsed.tzinfo)
        else:
            now = datetime.now()
        return max(0.0, (now - parsed).total_seconds())

    def _run_worker(self):
        """Main worker loop with market-aware scheduling."""
        self._recover_interrupted_cycles()
        now = self._et_now()
        self.next_scheduled_run, self.next_scheduled_reason = self._next_scheduled_run(after_dt=now)
        logger.info(
            f'Worker schedule initialized: next run at {self.next_scheduled_run.isoformat()} '
            f'({self.next_scheduled_reason})'
        )
        self._write_heartbeat()

        while self.running:
            try:
                now = self._et_now()
                self._write_heartbeat()
                if self.next_scheduled_run and now >= self.next_scheduled_run:
                    logger.info(
                        f'Scheduled cycle due at {self.next_scheduled_run.isoformat()} '
                        f'({self.next_scheduled_reason}); executing now'
                    )
                    self._run_prediction_cycle(run_reason=self.next_scheduled_reason)
                    self.next_scheduled_run, self.next_scheduled_reason = self._next_scheduled_run(
                        after_dt=self._et_now()
                    )
                    logger.info(
                        f'Next scheduled cycle at {self.next_scheduled_run.isoformat()} '
                        f'({self.next_scheduled_reason})'
                    )
                    self._write_heartbeat()
                    continue

                # Sleep in short increments so stop() remains responsive and schedule stays accurate.
                sleep_seconds = self.schedule_poll_seconds
                if self.next_scheduled_run:
                    until_next = (self.next_scheduled_run - now).total_seconds()
                    sleep_seconds = max(1, min(self.schedule_poll_seconds, until_next))
                time.sleep(sleep_seconds)

            except Exception as e:
                logger.error(f'Worker error: {e}', exc_info=True)
                self._write_heartbeat()
                time.sleep(min(60, self.schedule_poll_seconds))

    def _et_now(self) -> datetime:
        return datetime.now(self.market_tz)

    def _init_nyse_calendar(self):
        """Initialize optional external NYSE calendar provider when available."""
        if not self.use_nyse_calendar:
            logger.info('NYSE calendar integration disabled via USE_NYSE_CALENDAR=0')
            return
        try:
            import pandas_market_calendars as mcal
            self._nyse_calendar = mcal.get_calendar('NYSE')
            logger.info('Using pandas_market_calendars NYSE session calendar')
        except Exception:
            self._nyse_calendar = None
            logger.info('pandas_market_calendars unavailable; using built-in NYSE calendar rules')

    def _parse_overnight_check_times(self, raw: str) -> List[Tuple[int, int]]:
        """Parse comma-separated HH:MM times for overnight checks."""
        parsed: List[Tuple[int, int]] = []
        for token in (raw or '').split(','):
            token = token.strip()
            if not token:
                continue
            try:
                hour_str, minute_str = token.split(':', 1)
                hour, minute = int(hour_str), int(minute_str)
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    parsed.append((hour, minute))
            except ValueError:
                logger.warning(f'Ignoring invalid OVERNIGHT_CHECK_TIMES token: {token}')
        if not parsed:
            parsed = [(20, 0), (6, 0)]
        parsed = sorted(set(parsed), key=lambda hm: (hm[0], hm[1]))
        return parsed

    def _parse_symbol_list(self, raw: str) -> List[str]:
        """Parse comma-separated symbol list preserving order."""
        symbols: List[str] = []
        seen = set()
        for token in (raw or '').split(','):
            symbol = token.strip().upper()
            if not symbol or symbol in seen:
                continue
            symbols.append(symbol)
            seen.add(symbol)
        return symbols

    def _parse_provider_order(self, raw: str) -> List[str]:
        """Parse provider order and keep only known providers."""
        order: List[str] = []
        seen = set()
        for token in (raw or '').split(','):
            provider = token.strip().lower()
            if not provider or provider in seen:
                continue
            if provider not in self.PROVIDER_STAGE:
                logger.warning(f'Ignoring unknown provider in overnight order: {provider}')
                continue
            order.append(provider)
            seen.add(provider)
        if not order:
            return ['xai', 'perplexity', 'mistral']
        return order

    def _provider_order_for_run(self, run_reason: Optional[str]) -> Tuple[List[str], str]:
        """
        Select provider order for this cycle.
        Returns (provider_order, mode_label).
        """
        if not run_reason or not run_reason.startswith('overnight_'):
            return list(self.FULL_PROVIDER_ORDER), 'full_market'

        if not self.overnight_light_mode:
            return list(self.FULL_PROVIDER_ORDER), 'full_overnight'

        self._overnight_cycles_since_full += 1
        if self._overnight_cycles_since_full >= self.overnight_full_debate_every:
            self._overnight_cycles_since_full = 0
            return list(self.FULL_PROVIDER_ORDER), 'full_overnight_refresh'

        return list(self.overnight_light_provider_order), 'light_overnight'

    def _provider_groups_for_order(self, provider_order: List[str]) -> List[Tuple[str, List[str]]]:
        """Build ordered provider groups for council debate loops."""
        grouped: Dict[str, List[str]] = {'core': [], 'join': [], 'side': []}
        for provider in provider_order:
            stage = self.PROVIDER_STAGE.get(provider)
            if not stage:
                continue
            grouped[stage].append(provider)
        return [(stage, grouped[stage]) for stage in ('core', 'join', 'side') if grouped[stage]]

    def _observed_fixed_holiday(self, day: date_cls) -> date_cls:
        """Observed date for fixed-date NYSE holidays."""
        if day.weekday() == 5:  # Saturday -> Friday
            return day - timedelta(days=1)
        if day.weekday() == 6:  # Sunday -> Monday
            return day + timedelta(days=1)
        return day

    @staticmethod
    def _nth_weekday_of_month(year: int, month: int, weekday: int, nth: int) -> date_cls:
        first = date_cls(year, month, 1)
        delta_days = (weekday - first.weekday()) % 7 + (nth - 1) * 7
        return first + timedelta(days=delta_days)

    @staticmethod
    def _last_weekday_of_month(year: int, month: int, weekday: int) -> date_cls:
        if month == 12:
            first_next = date_cls(year + 1, 1, 1)
        else:
            first_next = date_cls(year, month + 1, 1)
        last = first_next - timedelta(days=1)
        delta_days = (last.weekday() - weekday) % 7
        return last - timedelta(days=delta_days)

    @staticmethod
    def _easter_sunday(year: int) -> date_cls:
        """Gregorian calendar Easter algorithm."""
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        return date_cls(year, month, day)

    def _nyse_holidays(self, year: int) -> Set[date_cls]:
        cached = self._nyse_holiday_cache.get(year)
        if cached is not None:
            return cached

        holidays: Set[date_cls] = set()

        # Fixed-date holidays (observed), including cross-year New Year's observation.
        fixed_candidates = [
            date_cls(year, 1, 1),       # New Year's Day
            date_cls(year, 6, 19),      # Juneteenth (NYSE since 2022)
            date_cls(year, 7, 4),       # Independence Day
            date_cls(year, 12, 25),     # Christmas Day
            date_cls(year + 1, 1, 1),   # Next year's New Year's observed may fall in current year
        ]
        for candidate in fixed_candidates:
            if candidate.month == 6 and candidate.day == 19 and candidate.year < 2022:
                continue
            observed = self._observed_fixed_holiday(candidate)
            if observed.year == year:
                holidays.add(observed)

        # Monday holidays
        holidays.add(self._nth_weekday_of_month(year, 1, 0, 3))   # MLK Day
        holidays.add(self._nth_weekday_of_month(year, 2, 0, 3))   # Washington's Birthday
        holidays.add(self._last_weekday_of_month(year, 5, 0))     # Memorial Day
        holidays.add(self._nth_weekday_of_month(year, 9, 0, 1))   # Labor Day

        # Thanksgiving
        thanksgiving = self._nth_weekday_of_month(year, 11, 3, 4)  # Thursday
        holidays.add(thanksgiving)

        # Good Friday
        easter = self._easter_sunday(year)
        holidays.add(easter - timedelta(days=2))

        self._nyse_holiday_cache[year] = holidays
        return holidays

    def _is_early_close_day_fallback(self, day: date_cls) -> bool:
        """
        Built-in NYSE early-close rules (1:00 PM ET):
        - Day after Thanksgiving
        - Christmas Eve (when it is a trading day)
        - Trading day before Independence Day observed holiday
        """
        if day.weekday() >= 5:
            return False

        holidays = self._nyse_holidays(day.year)
        if day in holidays:
            return False

        thanksgiving = self._nth_weekday_of_month(day.year, 11, 3, 4)
        if day == thanksgiving + timedelta(days=1):
            return True

        if day == date_cls(day.year, 12, 24):
            return True

        independence_observed = self._observed_fixed_holiday(date_cls(day.year, 7, 4))
        prev_trading_day = independence_observed - timedelta(days=1)
        while prev_trading_day.weekday() >= 5 or prev_trading_day in holidays:
            prev_trading_day -= timedelta(days=1)
        if day == prev_trading_day:
            return True

        return False

    def _nyse_session_for_date(self, day: date_cls) -> Optional[Tuple[datetime, datetime]]:
        """Return NYSE open/close datetimes in market timezone for a date."""
        if day in self._nyse_session_cache:
            return self._nyse_session_cache[day]

        # Preferred: external exchange session calendar if available.
        if self._nyse_calendar is not None:
            try:
                schedule = self._nyse_calendar.schedule(
                    start_date=day.isoformat(),
                    end_date=day.isoformat()
                )
                if not schedule.empty:
                    open_ts = schedule.iloc[0]['market_open']
                    close_ts = schedule.iloc[0]['market_close']
                    open_dt = open_ts.tz_convert(self.market_tz).to_pydatetime()
                    close_dt = close_ts.tz_convert(self.market_tz).to_pydatetime()
                    self._nyse_session_cache[day] = (open_dt, close_dt)
                    return self._nyse_session_cache[day]
                self._nyse_session_cache[day] = None
                return None
            except Exception as e:
                logger.warning(f'NYSE calendar provider failed for {day}: {e}; using built-in rules')
                self._nyse_calendar = None

        # Fallback: built-in NYSE holiday/session rules.
        if day.weekday() >= 5 or day in self._nyse_holidays(day.year):
            self._nyse_session_cache[day] = None
            return None

        open_dt = datetime(
            day.year,
            day.month,
            day.day,
            self.market_open_hour,
            self.market_open_minute,
            tzinfo=self.market_tz
        )

        close_hour = self.market_close_hour
        close_minute = self.market_close_minute
        if self._is_early_close_day_fallback(day):
            close_hour = self.nyse_early_close_hour
            close_minute = self.nyse_early_close_minute

        close_dt = datetime(
            day.year,
            day.month,
            day.day,
            close_hour,
            close_minute,
            tzinfo=self.market_tz
        )
        self._nyse_session_cache[day] = (open_dt, close_dt)
        return self._nyse_session_cache[day]

    def _market_window_for_date(self, day: date_cls) -> Optional[Tuple[datetime, datetime]]:
        return self._nyse_session_for_date(day)

    def _is_market_open(self, dt: datetime) -> bool:
        session = self._market_window_for_date(dt.date())
        if not session:
            return False
        open_dt, close_dt = session
        return open_dt <= dt < close_dt

    def _next_market_open(self, dt: datetime) -> datetime:
        """
        Return the next NYSE market-open datetime strictly after or containing `dt`.
        If `dt` is during a trading session, returns the following session open.
        """
        start_day = dt.date()
        for offset in range(0, 20):
            day = start_day + timedelta(days=offset)
            session = self._market_window_for_date(day)
            if not session:
                continue
            open_dt, close_dt = session
            if offset == 0:
                if dt < open_dt:
                    return open_dt
                if open_dt <= dt < close_dt:
                    # During session: next open is the next trading day.
                    continue
                # After close: continue searching.
                continue
            return open_dt

        # Defensive fallback if no session was found in the lookahead window.
        return datetime(
            dt.year,
            dt.month,
            dt.day,
            self.market_open_hour,
            self.market_open_minute,
            tzinfo=self.market_tz
        ) + timedelta(days=1)

    def _is_valid_overnight_slot(self, slot_dt: datetime) -> bool:
        if self._is_market_open(slot_dt):
            return False
        next_open = self._next_market_open(slot_dt)
        hours_until_open = (next_open - slot_dt).total_seconds() / 3600.0
        return 0 < hours_until_open <= self.overnight_lookahead_hours

    def _next_scheduled_run(self, after_dt: datetime) -> Tuple[datetime, str]:
        """
        Compute the next scheduled run time:
        - every MARKET_OPEN_INTERVAL_SECONDS during weekday market hours
        - overnight checks at configured times when next open is within lookahead window
        """
        search_start = after_dt + timedelta(seconds=1)
        candidates: List[Tuple[datetime, str]] = []
        interval = timedelta(seconds=self.market_open_interval_seconds)

        for day_offset in range(0, 8):
            day = (search_start + timedelta(days=day_offset)).date()
            session = self._market_window_for_date(day)
            if session:
                open_dt, close_dt = session
                slot = open_dt
                while slot < close_dt:
                    if slot >= search_start:
                        candidates.append((slot, 'market_open'))
                    slot += interval

            for hour, minute in self.overnight_check_times:
                overnight_slot = datetime(
                    day.year,
                    day.month,
                    day.day,
                    hour,
                    minute,
                    tzinfo=self.market_tz
                )
                if overnight_slot < search_start:
                    continue
                if self._is_valid_overnight_slot(overnight_slot):
                    candidates.append((overnight_slot, f'overnight_{hour:02d}:{minute:02d}'))

        if not candidates:
            fallback = search_start + timedelta(minutes=30)
            return fallback, 'fallback'

        return min(candidates, key=lambda x: x[0])

    def _bootstrap_cycle_blocklist(self, provider_order: List[str]) -> Set[str]:
        """
        Seed a per-cycle blocklist from persisted runtime failures.
        This avoids retrying providers that are already known hard-fail.
        """
        blocklist: Set[str] = set()
        try:
            runtime_status = self.prediction_service.get_provider_runtime_status()
        except Exception as e:
            logger.debug(f'Unable to load provider runtime status for blocklist bootstrap: {e}')
            return blocklist

        for provider_name in provider_order:
            state = runtime_status.get(provider_name, {})
            if not state:
                continue
            healthy = bool(state.get('healthy', True))
            error_text = str(state.get('last_error') or '')
            failed_age_seconds = self._seconds_since_timestamp(state.get('last_failed_at'))
            failed_recently = (
                failed_age_seconds is not None and
                failed_age_seconds <= self.provider_health_cooldown_seconds
            )
            hard_failure = self._should_block_provider(error_text)
            if (not healthy) and (hard_failure or failed_recently):
                blocklist.add(provider_name)
        return blocklist

    def _run_prediction_cycle(self, cycle_id: Optional[int] = None, run_reason: Optional[str] = None):
        """
        Execute a complete prediction cycle

        Args:
            cycle_id: Optional existing cycle ID to use
            run_reason: Optional scheduler reason label (market_open, overnight_*, manual, etc.)
        """
        db = ForesightDB(self.db_path)

        try:
            # Create new cycle if not provided
            if cycle_id is None:
                cycle_id = db.create_cycle()
                
            self.current_cycle_id = cycle_id
            provider_order, provider_mode = self._provider_order_for_run(run_reason)
            provider_groups = self._provider_groups_for_order(provider_order)
            provider_blocklist = self._bootstrap_cycle_blocklist(provider_order)
            if provider_blocklist:
                logger.info(
                    f'Initial cycle blocklist from runtime health: {sorted(provider_blocklist)}'
                )
            self._write_heartbeat()

            logger.info(
                f'Started processing prediction cycle {cycle_id} '
                f'(reason={run_reason or "unspecified"}, provider_mode={provider_mode})'
            )
            logger.info(f'Provider order for cycle {cycle_id}: {provider_order}')
            # Note: cycle_start event is auto-emitted by db.create_cycle()

            # Phase 1: Discover stocks
            logger.info('Phase 1: Discovering stocks')
            symbols = self._discover_stocks(db, cycle_id, provider_order=provider_order)
            db.set_stocks_discovered(cycle_id, len(symbols))

            if not symbols:
                logger.warning('No stocks discovered, completing cycle')
                db.complete_cycle(cycle_id)
                return

            # Phase 2: Generate predictions for discovered stocks
            logger.info(f'Phase 2: Generating predictions for {len(symbols)} stocks')
            for symbol in symbols:
                if run_reason != 'manual' and not self.running:
                    break
                self._process_stock(
                    db,
                    cycle_id,
                    symbol,
                    provider_groups=provider_groups,
                    synthesis_order=provider_order,
                    provider_blocklist=provider_blocklist
                )

            # Phase 3: Complete cycle
            db.complete_cycle(cycle_id)
            self.total_cycles_completed += 1
            logger.info(f'Completed prediction cycle {cycle_id} (total: {self.total_cycles_completed})')
            # Note: cycle_complete event is auto-emitted by db.complete_cycle()
            self._write_heartbeat()

            # Phase 4: Evaluate any predictions whose target window has passed
            self._evaluate_pending_predictions(db)

        except Exception as e:
            logger.error(f'Error in prediction cycle: {e}', exc_info=True)
            if self.current_cycle_id:
                db.fail_cycle(self.current_cycle_id, str(e))
                # Note: cycle_failed event is auto-emitted by db.fail_cycle()

        finally:
            self.current_cycle_id = None
            self.last_cycle_time = time.time()
            self._write_heartbeat()

    def _evaluate_pending_predictions(self, db: ForesightDB) -> None:
        """Fetch actual prices and evaluate predictions whose target window has passed."""
        try:
            import yfinance as yf
            pending = db.get_unevaluated_predictions(before_time=datetime.now())
            if not pending:
                return
            logger.info(f'Evaluating {len(pending)} pending predictions')

            # Group by stock_id so we only call yfinance once per ticker
            from collections import defaultdict
            by_stock: Dict[int, list] = defaultdict(list)
            for p in pending:
                by_stock[p['stock_id']].append(p)

            for stock_id, preds in by_stock.items():
                # Get the ticker from any prediction (they all share the same stock)
                stock = db.get_stock_by_id(stock_id)
                if not stock:
                    continue
                ticker = stock['ticker']
                try:
                    hist = yf.Ticker(ticker).history(period='5d')
                    if hist.empty:
                        continue
                    actual_price = float(hist['Close'].iloc[-1])
                except Exception as yf_err:
                    logger.warning(f'yfinance fetch failed for {ticker}: {yf_err}')
                    continue

                for pred in preds:
                    initial_price = pred.get('initial_price') or 0.0
                    if initial_price <= 0:
                        continue
                    actual_direction = (
                        'up' if actual_price > initial_price
                        else 'down' if actual_price < initial_price
                        else 'neutral'
                    )
                    db.evaluate_prediction(pred['id'], actual_price, actual_direction)
                    logger.debug(
                        f'Evaluated {ticker} pred {pred["id"]}: '
                        f'{pred["predicted_direction"]} vs {actual_direction} '
                        f'(initial={initial_price:.2f}, actual={actual_price:.2f})'
                    )
        except Exception as e:
            logger.error(f'Error evaluating pending predictions: {e}', exc_info=True)

    def _discover_stocks(
        self,
        db: ForesightDB,
        cycle_id: int,
        provider_order: Optional[List[str]] = None
    ) -> list:
        """
        Discover interesting symbols (equities + optional crypto list).

        Args:
            db: Database instance
            cycle_id: Current cycle ID
            provider_order: Provider sequence for discovery debate.

        Returns:
            List of validated symbols
        """
        try:
            max_stocks = int(self.config['MAX_STOCKS'])
            logger.debug(f'Calling discover_stocks_debate with max_stocks={max_stocks}')
            weights = self._get_provider_weights(db)
            discovered_symbols: List[str] = []

            if max_stocks > 0:
                discovered_symbols = self.prediction_service.discover_stocks_debate(
                    count=max_stocks,
                    provider_weights=weights,
                    stage_order=provider_order
                )
            logger.debug(f'Equity discovery returned: {discovered_symbols}')

            symbols: List[str] = []
            seen = set()
            for symbol in discovered_symbols:
                key = symbol.upper()
                if key in seen:
                    continue
                symbols.append(key)
                seen.add(key)

            if self.include_crypto and self.max_crypto_symbols > 0 and self.crypto_symbols:
                configured_crypto = self.crypto_symbols[:self.max_crypto_symbols]
                logger.info(f'Adding configured crypto symbols for cycle: {configured_crypto}')
                for symbol in configured_crypto:
                    key = symbol.upper()
                    if key in seen:
                        continue
                    symbols.append(key)
                    seen.add(key)

            if not symbols:
                logger.warning('Discovery returned no symbols')
                return []

            logger.info(f'Discovered {len(symbols)} candidate symbols: {symbols}')

            # Validate and add stocks to database
            valid_symbols = []
            for symbol in symbols:
                # Validate symbol exists
                if not self.stock_service.validate_symbol(symbol):
                    logger.warning(f'Invalid symbol: {symbol}')
                    continue

                # Fetch stock info
                stock_info = self.stock_service.fetch_stock_info(symbol)
                if not stock_info:
                    logger.warning(f'Could not fetch info for: {symbol}')
                    continue

                # Add to database
                stock_id = db.add_stock(
                    ticker=symbol,
                    name=stock_info.get('name', symbol),
                    metadata={
                        'asset_type': 'crypto' if symbol.upper() in self.crypto_symbol_set else 'equity',
                        'sector': stock_info.get('sector'),
                        'industry': stock_info.get('industry'),
                        'market_cap': stock_info.get('market_cap')
                    }
                )

                # Record initial price
                current_price = stock_info.get('current_price')
                if current_price:
                    db.add_price(
                        stock_id=stock_id,
                        cycle_id=cycle_id,
                        price=current_price
                    )

                valid_symbols.append(symbol)
                # Note: stock_added event is auto-emitted by db.add_stock()

            return valid_symbols

        except Exception as e:
            logger.error(f'Error discovering stocks: {e}', exc_info=True)
            return []

    def _get_provider_weights(self, db: ForesightDB) -> Dict[str, float]:
        """
        Build provider weights using historical evaluated accuracy.
        """
        leaderboard = db.get_provider_leaderboard()
        performance: Dict[str, float] = {}
        for row in leaderboard:
            provider = row.get('provider', '')
            # Ignore synthetic consensus rows for base provider performance.
            if provider.endswith('-consensus'):
                continue
            if row.get('accuracy_rate') is None:
                continue
            performance[provider] = float(row['accuracy_rate'])
        weights = self.prediction_service.build_provider_weights(performance)
        logger.info(f'Provider weights for cycle: {weights}')
        return weights

    def _process_stock(
        self,
        db: ForesightDB,
        cycle_id: int,
        symbol: str,
        provider_groups: Optional[List[Tuple[str, List[str]]]] = None,
        synthesis_order: Optional[List[str]] = None,
        provider_blocklist: Optional[Set[str]] = None
    ):
        """
        Process a single stock: fetch data, get multiple analyst reports, and a consensus
        """
        try:
            # Get stock from database
            stock = db.get_stock(symbol)
            if not stock:
                logger.error(f'Stock not found in database: {symbol}')
                return

            stock_id = stock['id']

            # Fetch historical data
            lookback_days = self.config['LOOKBACK_DAYS']
            historical = self.stock_service.fetch_historical_data(symbol, days=lookback_days)

            if not historical:
                logger.warning(f'No historical data for {symbol}')
                return

            # Prepare stock data for prediction
            stock_data = {
                'symbol': symbol,
                'current_price': historical['close'][-1] if historical['close'] else None,
                'close': historical['close'],
                'volume': historical['volume'],
                'dates': historical['dates']
            }

            # --- MULTI-AGENT COUNCIL PHASE ---
            analyst_reports = []
            current_price = stock_data.get('current_price')
            # Set target time to 7 days from now
            target_time = datetime.now() + timedelta(days=7)
            if provider_groups is None:
                provider_groups = self._provider_groups_for_order(self.FULL_PROVIDER_ORDER)
            if synthesis_order is None:
                synthesis_order = self.FULL_PROVIDER_ORDER
            if provider_blocklist is None:
                provider_blocklist = set()

            for stage_name, providers in provider_groups:
                for provider_name in providers:
                    if provider_name in provider_blocklist:
                        logger.info(
                            f'[{symbol}] [{stage_name}] Skipping blocked provider {provider_name} for this cycle'
                        )
                        continue
                    try:
                        logger.info(f'[{symbol}] [{stage_name}] Requesting analysis from {provider_name}')
                        report = self.prediction_service.generate_prediction_swarm(
                            symbol,
                            stock_data,
                            provider_name=provider_name
                        )
                        if not report:
                            runtime = self.prediction_service.get_provider_runtime_status().get(provider_name, {})
                            error_text = str(runtime.get('last_error') or '')
                            should_block = (not runtime.get('healthy', True)) or self._should_block_provider(error_text)
                            if should_block:
                                provider_blocklist.add(provider_name)
                                logger.warning(
                                    f'[{symbol}] [{stage_name}] Blocking provider {provider_name} '
                                    f'for remaining cycle due to error: {error_text}'
                                )
                            continue

                        report['stage'] = stage_name
                        analyst_reports.append(report)
                        db.add_prediction(
                            cycle_id=cycle_id,
                            stock_id=stock_id,
                            provider=report['provider'],
                            predicted_direction=report['prediction'],
                            confidence=report['confidence'],
                            initial_price=current_price,
                            target_time=target_time,
                            reasoning=f"[{stage_name}] {report['reasoning']}"
                        )
                    except Exception as e:
                        if self._should_block_provider(str(e)):
                            provider_blocklist.add(provider_name)
                            logger.warning(
                                f'[{symbol}] [{stage_name}] Blocking provider {provider_name} '
                                f'for remaining cycle due to exception: {e}'
                            )
                        logger.warning(
                            f'[{symbol}] [{stage_name}] Provider {provider_name} failed: {e}'
                        )

            # --- WEIGHTED COUNCIL VOTE + SYNTHESIS PHASE ---
            if analyst_reports:
                logger.info(f'[{symbol}] Moderating council debate between {len(analyst_reports)} analysts')

                weights = self._get_provider_weights(db)
                vote_totals = {'up': 0.0, 'down': 0.0, 'neutral': 0.0}
                per_provider_lines = []

                for report in analyst_reports:
                    provider = report['provider']
                    direction = report['prediction'] if report['prediction'] in vote_totals else 'neutral'
                    conf = float(report.get('confidence') or 0.5)
                    w = float(weights.get(provider, 1.0))
                    score = max(0.05, conf) * w
                    vote_totals[direction] += score
                    per_provider_lines.append(
                        f"{provider} [{report.get('stage','n/a')}]: dir={direction} conf={conf:.2f} weight={w:.2f} score={score:.2f}; reason={report.get('reasoning','')}"
                    )

                winning_direction = max(vote_totals.items(), key=lambda x: x[1])[0]
                total_score = sum(vote_totals.values()) or 1.0
                council_confidence = vote_totals[winning_direction] / total_score
                council_reasoning = (
                    f"Council weighted vote totals: up={vote_totals['up']:.2f}, down={vote_totals['down']:.2f}, neutral={vote_totals['neutral']:.2f}. "
                    f"Winner={winning_direction}. Individual reports: " + " | ".join(per_provider_lines)
                )

                db.add_prediction(
                    cycle_id=cycle_id,
                    stock_id=stock_id,
                    provider='council-weighted',
                    predicted_direction=winning_direction,
                    confidence=council_confidence,
                    initial_price=current_price,
                    target_time=target_time,
                    reasoning=council_reasoning
                )

                # Final-stage democratic synthesis (no single lead model)
                active_synthesis_order = [p for p in synthesis_order if p not in provider_blocklist]
                if not active_synthesis_order:
                    logger.warning(f'[{symbol}] No providers left for synthesis after cycle blocklist filtering')
                    active_synthesis_order = synthesis_order
                consensus = self.prediction_service.synthesize_council_swarm(
                    symbol,
                    stock_data,
                    analyst_reports,
                    provider_weights=weights,
                    stage_order=active_synthesis_order
                )
                if consensus:
                    # Persist each synthesis vote for transparency
                    for report in consensus.get('reports', []):
                        db.add_prediction(
                            cycle_id=cycle_id,
                            stock_id=stock_id,
                            provider=f"{report['provider']}-synthesis",
                            predicted_direction=report['prediction'],
                            confidence=report['confidence'],
                            initial_price=current_price,
                            target_time=target_time,
                            reasoning=f"[{report.get('stage','n/a')}] {report.get('reasoning','')}"
                        )

                    db.add_prediction(
                        cycle_id=cycle_id,
                        stock_id=stock_id,
                        provider=f"{consensus['provider']}-consensus",
                        predicted_direction=consensus['prediction'],
                        confidence=consensus['confidence'],
                        initial_price=current_price,
                        target_time=target_time,
                        reasoning=(
                            f"{consensus['reasoning']} | Council vote: {winning_direction} ({council_confidence:.2f}). "
                            f"Vote totals: {vote_totals}. Individual reports: {' | '.join(per_provider_lines)}"
                        )
                    )
                    logger.info(
                        f'Consensus reached for {symbol}: {consensus["prediction"]} '
                        f'(confidence: {consensus["confidence"]}) via {consensus["provider"]}; '
                        f'council winner={winning_direction} ({council_confidence:.2f})'
                    )
            else:
                logger.warning(f'No analyst reports available for {symbol}, skipping consensus')

        except Exception as e:
            logger.error(f'Error processing stock {symbol}: {e}', exc_info=True)

    @staticmethod
    def _should_block_provider(error_text: str) -> bool:
        """Return True for hard-failure classes we should skip for the rest of this cycle."""
        if not error_text:
            return False
        lowered = error_text.lower()
        hard_failure_markers = (
            "status_code: 429",
            "429",
            "trial key",
            "rate limit",
            "authorization required",
            "invalid api key",
            "unexpected keyword argument 'proxies'",
        )
        return any(marker in lowered for marker in hard_failure_markers)
