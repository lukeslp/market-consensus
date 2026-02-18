"""
Background worker for stock prediction cycles
"""
import time
import logging
import threading
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from db import ForesightDB
from .services.stock_service import StockService
from .services.prediction_service import PredictionService

logger = logging.getLogger(__name__)


class PredictionWorker:
    """Background worker that executes prediction cycles on a schedule"""

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

        # Scheduling configuration
        self.market_tz = ZoneInfo(config.get('MARKET_TIMEZONE', 'America/New_York'))
        self.market_open_hour = int(config.get('MARKET_OPEN_HOUR', 9))
        self.market_open_minute = int(config.get('MARKET_OPEN_MINUTE', 30))
        self.market_close_hour = int(config.get('MARKET_CLOSE_HOUR', 16))
        self.market_close_minute = int(config.get('MARKET_CLOSE_MINUTE', 0))
        self.market_open_interval_seconds = max(60, int(config.get('MARKET_OPEN_INTERVAL_SECONDS', 1800)))
        self.overnight_lookahead_hours = max(1, int(config.get('OVERNIGHT_LOOKAHEAD_HOURS', 18)))
        self.schedule_poll_seconds = max(5, int(config.get('SCHEDULE_POLL_SECONDS', 20)))
        self.overnight_check_times = self._parse_overnight_check_times(
            config.get('OVERNIGHT_CHECK_TIMES', '20:00,06:00')
        )

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
        logger.info('Prediction worker started')

    def is_alive(self) -> bool:
        """Check if the worker thread is running"""
        return self.running and self.thread and self.thread.is_alive()

    def stop(self):
        """Stop the background worker gracefully"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
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
        }

    def _run_worker(self):
        """Main worker loop with market-aware scheduling."""
        now = self._et_now()
        self.next_scheduled_run, self.next_scheduled_reason = self._next_scheduled_run(after_dt=now)
        logger.info(
            f'Worker schedule initialized: next run at {self.next_scheduled_run.isoformat()} '
            f'({self.next_scheduled_reason})'
        )

        while self.running:
            try:
                now = self._et_now()
                if self.next_scheduled_run and now >= self.next_scheduled_run:
                    logger.info(
                        f'Scheduled cycle due at {self.next_scheduled_run.isoformat()} '
                        f'({self.next_scheduled_reason}); executing now'
                    )
                    self._run_prediction_cycle()
                    self.next_scheduled_run, self.next_scheduled_reason = self._next_scheduled_run(
                        after_dt=self._et_now()
                    )
                    logger.info(
                        f'Next scheduled cycle at {self.next_scheduled_run.isoformat()} '
                        f'({self.next_scheduled_reason})'
                    )
                    continue

                # Sleep in short increments so stop() remains responsive and schedule stays accurate.
                sleep_seconds = self.schedule_poll_seconds
                if self.next_scheduled_run:
                    until_next = (self.next_scheduled_run - now).total_seconds()
                    sleep_seconds = max(1, min(self.schedule_poll_seconds, until_next))
                time.sleep(sleep_seconds)

            except Exception as e:
                logger.error(f'Worker error: {e}', exc_info=True)
                time.sleep(min(60, self.schedule_poll_seconds))

    def _et_now(self) -> datetime:
        return datetime.now(self.market_tz)

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

    def _market_window_for_date(self, day) -> Tuple[datetime, datetime]:
        open_dt = datetime(
            day.year,
            day.month,
            day.day,
            self.market_open_hour,
            self.market_open_minute,
            tzinfo=self.market_tz
        )
        close_dt = datetime(
            day.year,
            day.month,
            day.day,
            self.market_close_hour,
            self.market_close_minute,
            tzinfo=self.market_tz
        )
        return open_dt, close_dt

    def _is_market_open(self, dt: datetime) -> bool:
        if dt.weekday() >= 5:
            return False
        open_dt, close_dt = self._market_window_for_date(dt.date())
        return open_dt <= dt < close_dt

    def _next_market_open(self, dt: datetime) -> datetime:
        """
        Return the next weekday market-open datetime after `dt`.
        Uses weekday logic only (no holiday calendar).
        """
        cursor = dt
        while True:
            if cursor.weekday() < 5:
                open_dt, close_dt = self._market_window_for_date(cursor.date())
                if cursor < open_dt:
                    return open_dt
                if open_dt <= cursor < close_dt:
                    # If currently open, "next open" is the next trading day.
                    cursor = close_dt + timedelta(seconds=1)
                else:
                    cursor = datetime(
                        cursor.year,
                        cursor.month,
                        cursor.day,
                        23,
                        59,
                        59,
                        tzinfo=self.market_tz
                    ) + timedelta(seconds=1)
            else:
                cursor = datetime(
                    cursor.year,
                    cursor.month,
                    cursor.day,
                    23,
                    59,
                    59,
                    tzinfo=self.market_tz
                ) + timedelta(seconds=1)

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

            if day.weekday() < 5:
                open_dt, close_dt = self._market_window_for_date(day)
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

    def _run_prediction_cycle(self, cycle_id: Optional[int] = None):
        """
        Execute a complete prediction cycle

        Args:
            cycle_id: Optional existing cycle ID to use
        """
        db = ForesightDB(self.db_path)

        try:
            # Create new cycle if not provided
            if cycle_id is None:
                cycle_id = db.create_cycle()
                
            self.current_cycle_id = cycle_id
            logger.info(f'Started processing prediction cycle {cycle_id}')
            # Note: cycle_start event is auto-emitted by db.create_cycle()

            # Phase 1: Discover stocks
            logger.info('Phase 1: Discovering stocks')
            symbols = self._discover_stocks(db, cycle_id)

            if not symbols:
                logger.warning('No stocks discovered, completing cycle')
                db.complete_cycle(cycle_id)
                return

            # Phase 2: Generate predictions for discovered stocks
            logger.info(f'Phase 2: Generating predictions for {len(symbols)} stocks')
            for symbol in symbols:
                if not self.running:
                    break
                self._process_stock(db, cycle_id, symbol)

            # Phase 3: Complete cycle
            db.complete_cycle(cycle_id)
            self.total_cycles_completed += 1
            logger.info(f'Completed prediction cycle {cycle_id} (total: {self.total_cycles_completed})')
            # Note: cycle_complete event is auto-emitted by db.complete_cycle()

        except Exception as e:
            logger.error(f'Error in prediction cycle: {e}', exc_info=True)
            if self.current_cycle_id:
                db.fail_cycle(self.current_cycle_id, str(e))
                # Note: cycle_failed event is auto-emitted by db.fail_cycle()

        finally:
            self.current_cycle_id = None
            self.last_cycle_time = time.time()

    def _discover_stocks(self, db: ForesightDB, cycle_id: int) -> list:
        """
        Discover interesting stocks using LLM

        Args:
            db: Database instance
            cycle_id: Current cycle ID

        Returns:
            List of stock symbols
        """
        try:
            max_stocks = self.config['MAX_STOCKS']
            logger.debug(f'Calling discover_stocks_debate with max_stocks={max_stocks}')
            weights = self._get_provider_weights(db)
            symbols = self.prediction_service.discover_stocks_debate(count=max_stocks, provider_weights=weights)
            logger.debug(f'Discovery returned: {symbols}')

            if not symbols:
                logger.warning('Discovery returned no stocks')
                return []

            logger.info(f'Discovered {len(symbols)} stocks: {symbols}')

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

    def _process_stock(self, db: ForesightDB, cycle_id: int, symbol: str):
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
            provider_groups = [
                ('core', ['xai', 'gemini']),
                ('join', ['anthropic', 'openai', 'perplexity']),
                ('side', ['mistral', 'cohere']),
            ]

            for stage_name, providers in provider_groups:
                for provider_name in providers:
                    logger.info(f'[{symbol}] [{stage_name}] Requesting analysis from {provider_name}')
                    report = self.prediction_service.generate_prediction_swarm(
                        symbol,
                        stock_data,
                        provider_name=provider_name
                    )
                    if not report:
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
                consensus = self.prediction_service.synthesize_council_swarm(
                    symbol,
                    stock_data,
                    analyst_reports,
                    provider_weights=weights
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
