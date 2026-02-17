"""
Background worker for stock prediction cycles
"""
import time
import logging
import threading
from typing import Optional, List, Dict
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
        self.last_premarket_cycle_date = None

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
        }

    def _run_worker(self):
        """Main worker loop"""
        cycle_interval = self.config['CYCLE_INTERVAL']
        first_cycle = True

        while self.running:
            try:
                # Ensure there is at least one cycle before US market open on weekdays.
                self._ensure_premarket_cycle()

                # Run a prediction cycle
                self._run_prediction_cycle()

                # For first cycle, short wait; then use normal interval
                if first_cycle:
                    logger.info('First cycle complete, entering normal schedule')
                    first_cycle = False
                    # Brief wait before next cycle
                    time.sleep(5)
                else:
                    logger.info(f'Waiting {cycle_interval}s until next cycle')
                    time.sleep(cycle_interval)

            except Exception as e:
                logger.error(f'Worker error: {e}', exc_info=True)
                # Wait a bit before retrying
                time.sleep(60)

    def _ensure_premarket_cycle(self):
        """
        Force at least one cycle during the pre-market window (04:00-09:30 ET),
        once per weekday, so the DB has fresh pre-open data.
        """
        et_now = datetime.now(ZoneInfo('America/New_York'))
        if et_now.weekday() >= 5:  # Sat/Sun
            return

        premarket_start = et_now.replace(hour=4, minute=0, second=0, microsecond=0)
        market_open = et_now.replace(hour=9, minute=30, second=0, microsecond=0)
        if not (premarket_start <= et_now < market_open):
            return

        today = et_now.date()
        if self.last_premarket_cycle_date == today:
            return

        db = ForesightDB(self.db_path)
        recent_cycles = db.get_recent_cycles(limit=50)

        has_today_premarket_cycle = False
        for cycle in recent_cycles:
            start_raw = cycle.get('start_time')
            if not start_raw:
                continue
            try:
                # SQLite timestamps are naive strings; interpret as local server time.
                start_dt = datetime.fromisoformat(str(start_raw))
            except Exception:
                continue
            if start_dt.date() == today and start_dt.time() < market_open.time():
                has_today_premarket_cycle = True
                break

        if has_today_premarket_cycle:
            self.last_premarket_cycle_date = today
            return

        logger.info('No pre-market cycle found for today; triggering pre-open cycle')
        self._run_prediction_cycle()
        self.last_premarket_cycle_date = today

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
                    report = self.prediction_service.generate_prediction(symbol, stock_data, provider_name=provider_name)
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

                # Optional head-of-research synthesis
                consensus = self.prediction_service.debate_and_vote(symbol, stock_data, analyst_reports)
                if consensus:
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
                        f'(confidence: {consensus["confidence"]}) via {consensus["model"]}; '
                        f'council winner={winning_direction} ({council_confidence:.2f})'
                    )
            else:
                logger.warning(f'No analyst reports available for {symbol}, skipping consensus')

        except Exception as e:
            logger.error(f'Error processing stock {symbol}: {e}', exc_info=True)
