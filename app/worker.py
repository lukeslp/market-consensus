"""
Background worker for stock prediction cycles
"""
import time
import logging
import threading
from typing import Optional, List, Dict
from datetime import datetime, timedelta

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

    def _run_worker(self):
        """Main worker loop"""
        cycle_interval = self.config['CYCLE_INTERVAL']
        first_cycle = True

        while self.running:
            try:
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
            logger.debug(f'Calling discover_stocks with max_stocks={max_stocks}')
            symbols = self.prediction_service.discover_stocks(count=max_stocks)
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

            # --- MULTI-AGENT DEBATE PHASE ---
            analyst_reports = []
            current_price = stock_data.get('current_price')
            # Set target time to 7 days from now
            target_time = datetime.now() + timedelta(days=7)
            
            # 1. Claude (Primary Analyst)
            logger.info(f'[{symbol}] Requesting analysis from Primary Analyst (Claude)')
            primary_report = self.prediction_service.generate_prediction(symbol, stock_data, provider_name='anthropic')
            if primary_report:
                analyst_reports.append(primary_report)
                db.add_prediction(
                    cycle_id=cycle_id,
                    stock_id=stock_id,
                    provider=primary_report['provider'],
                    predicted_direction=primary_report['prediction'],
                    confidence=primary_report['confidence'],
                    initial_price=current_price,
                    target_time=target_time,
                    reasoning=primary_report['reasoning']
                )

            # 2. Grok (Alternative Analyst)
            logger.info(f'[{symbol}] Requesting analysis from Alternative Analyst (Grok)')
            alternative_report = self.prediction_service.generate_prediction(symbol, stock_data, provider_name='xai')
            if alternative_report:
                analyst_reports.append(alternative_report)
                db.add_prediction(
                    cycle_id=cycle_id,
                    stock_id=stock_id,
                    provider=alternative_report['provider'],
                    predicted_direction=alternative_report['prediction'],
                    confidence=alternative_report['confidence'],
                    initial_price=current_price,
                    target_time=target_time,
                    reasoning=alternative_report['reasoning']
                )

            # 3. Mistral (European Perspective)
            logger.info(f'[{symbol}] Requesting analysis from European Perspective (Mistral)')
            mistral_report = self.prediction_service.generate_prediction(symbol, stock_data, provider_name='mistral')
            if mistral_report:
                analyst_reports.append(mistral_report)
                db.add_prediction(
                    cycle_id=cycle_id,
                    stock_id=stock_id,
                    provider=mistral_report['provider'],
                    predicted_direction=mistral_report['prediction'],
                    confidence=mistral_report['confidence'],
                    initial_price=current_price,
                    target_time=target_time,
                    reasoning=mistral_report['reasoning']
                )

            # 4. Perplexity (Search-Augmented Perspective)
            logger.info(f'[{symbol}] Requesting analysis from Search-Augmented Analyst (Perplexity)')
            perplexity_report = self.prediction_service.generate_prediction(symbol, stock_data, provider_name='perplexity')
            if perplexity_report:
                analyst_reports.append(perplexity_report)
                db.add_prediction(
                    cycle_id=cycle_id,
                    stock_id=stock_id,
                    provider=perplexity_report['provider'],
                    predicted_direction=perplexity_report['prediction'],
                    confidence=perplexity_report['confidence'],
                    initial_price=current_price,
                    target_time=target_time,
                    reasoning=perplexity_report['reasoning']
                )

            # --- CONSENSUS PHASE (Head of Research / Gemini) ---
            if analyst_reports:
                logger.info(f'[{symbol}] Moderating debate between {len(analyst_reports)} analysts')
                consensus = self.prediction_service.debate_and_vote(symbol, stock_data, analyst_reports)
                
                if consensus:
                    # Mark this as the final consensus prediction
                    db.add_prediction(
                        cycle_id=cycle_id,
                        stock_id=stock_id,
                        provider=f"{consensus['provider']}-consensus",
                        predicted_direction=consensus['prediction'],
                        confidence=consensus['confidence'],
                        initial_price=current_price,
                        target_time=target_time,
                        reasoning=consensus['reasoning']
                    )
                    logger.info(f'Consensus reached for {symbol}: {consensus["prediction"]} (confidence: {consensus["confidence"]}) via {consensus["model"]}')
            else:
                logger.warning(f'No analyst reports available for {symbol}, skipping consensus')

        except Exception as e:
            logger.error(f'Error processing stock {symbol}: {e}', exc_info=True)
