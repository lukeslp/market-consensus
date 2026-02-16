"""
Background worker for prediction cycles
Runs prediction workflows in a separate thread
"""
import sys
import threading
import time
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

# Add project root for db.py import
root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from db import ForesightDB
from app.services.stock_service import StockService
from app.services.prediction_service import PredictionService

logger = logging.getLogger(__name__)


class PredictionWorker:
    """Background worker for running prediction cycles"""

    def __init__(self, config):
        """
        Initialize worker

        Args:
            config: Flask config object
        """
        self.config = config
        self.db_path = config['DB_PATH']
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.current_cycle_id: Optional[int] = None

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

    def stop(self):
        """Stop the background worker gracefully"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        logger.info('Prediction worker stopped')

    def _run_worker(self):
        """Main worker loop"""
        cycle_interval = self.config['CYCLE_INTERVAL']

        while self.running:
            try:
                # Run a prediction cycle
                self._run_prediction_cycle()

                # Wait for next cycle
                logger.info(f'Waiting {cycle_interval}s until next cycle')
                time.sleep(cycle_interval)

            except Exception as e:
                logger.error(f'Worker error: {e}', exc_info=True)
                # Wait a bit before retrying
                time.sleep(60)

    def _run_prediction_cycle(self):
        """Execute a complete prediction cycle"""
        db = ForesightDB(self.db_path)

        try:
            # Create new cycle
            cycle_id = db.create_cycle()
            self.current_cycle_id = cycle_id
            logger.info(f'Started prediction cycle {cycle_id}')
            # Note: cycle_start event is auto-emitted by db.create_cycle()

            # Phase 1: Discover stocks
            logger.info('Phase 1: Discovering stocks')
            symbols = self._discover_stocks(db, cycle_id)

            if not symbols:
                logger.warning('No stocks discovered, completing cycle')
                db.complete_cycle(cycle_id)
                return

            # Phase 2: Generate predictions for each stock
            logger.info(f'Phase 2: Generating predictions for {len(symbols)} stocks')
            for symbol in symbols:
                self._process_stock(db, cycle_id, symbol)

            # Phase 3: Complete cycle
            db.complete_cycle(cycle_id)
            logger.info(f'Completed prediction cycle {cycle_id}')
            # Note: cycle_complete event is auto-emitted by db.complete_cycle()

        except Exception as e:
            logger.error(f'Error in prediction cycle: {e}', exc_info=True)
            if self.current_cycle_id:
                db.fail_cycle(self.current_cycle_id, str(e))
                # Note: cycle_failed event is auto-emitted by db.fail_cycle()

        finally:
            self.current_cycle_id = None

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
            symbols = self.prediction_service.discover_stocks(count=max_stocks)

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
        Process a single stock: fetch data and generate predictions

        Args:
            db: Database instance
            cycle_id: Current cycle ID
            symbol: Stock ticker symbol
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

            # Generate prediction
            prediction = self.prediction_service.generate_prediction(symbol, stock_data)

            if not prediction:
                logger.warning(f'Failed to generate prediction for {symbol}')
                return

            # Get current price for initial_price
            current_price = stock_data['current_price']

            # Map prediction direction to database format
            direction_map = {
                'UP': 'up',
                'DOWN': 'down',
                'NEUTRAL': 'neutral'
            }
            predicted_direction = direction_map.get(
                prediction['prediction'].upper(),
                'neutral'
            )

            # Store prediction in database
            # Target time is 7 days from now (can be configured later)
            from datetime import timedelta
            target_time = datetime.now() + timedelta(days=7)

            prediction_id = db.add_prediction(
                cycle_id=cycle_id,
                stock_id=stock_id,
                provider=prediction['provider'],
                predicted_direction=predicted_direction,
                confidence=prediction['confidence'],
                reasoning=prediction['reasoning'],
                initial_price=current_price,
                target_time=target_time
            )

            logger.info(f'Generated prediction for {symbol}: {predicted_direction} (confidence: {prediction["confidence"]:.2f})')
            # Note: prediction_added event is auto-emitted by db.add_prediction()

        except Exception as e:
            logger.error(f'Error processing stock {symbol}: {e}', exc_info=True)

    def is_alive(self) -> bool:
        """Check if worker thread is alive"""
        return self.thread.is_alive() if self.thread else False

    def get_status(self) -> dict:
        """Get worker status"""
        return {
            'running': self.running,
            'thread_alive': self.is_alive(),
            'current_cycle_id': self.current_cycle_id
        }
