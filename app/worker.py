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
        self.last_cycle_time: Optional[float] = None
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

            # Phase 2: Generate predictions for each stock
            logger.info(f'Phase 2: Generating predictions for {len(symbols)} stocks')
            for symbol in symbols:
                self._process_stock(db, cycle_id, symbol)

            # Phase 3: Complete cycle
            db.complete_cycle(cycle_id)
            self.total_cycles_completed += 1
            self.last_cycle_time = time.time()
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
            
            # 1. Primary technical analysis (usually Claude)
            logger.info(f'[{symbol}] Requesting technical analysis from primary analyst')
            primary_pred = self.prediction_service.generate_prediction(symbol, stock_data)
            if primary_pred:
                analyst_reports.append(primary_pred)
            
            # 2. Add second analyst for debate (using xAI/Grok)
            # Temporarily reuse PredictionService with a different provider role if needed
            # but for now we'll just use the primary and a secondary if available
            logger.info(f'[{symbol}] Requesting alternative analysis from secondary analyst')
            
            # Let's use xAI explicitly as the "contrarian" for the debate
            try:
                from llm_providers import ProviderFactory
                xai_provider = ProviderFactory.get_provider('xai')
                # Simple prompt for the second analyst
                from llm_providers import Message
                import json
                prompt = f"Contrarian analysis for {symbol} at ${stock_data['current_price']}. Predict UP/DOWN/NEUTRAL with JSON: {{\"prediction\": \"UP\", \"confidence\": 0.7, \"reasoning\": \"...\"}}"
                resp = xai_provider.complete(messages=[Message(role='user', content=prompt)])
                # Basic parsing
                try:
                    alt_data = json.loads(resp.content)
                    analyst_reports.append({
                        'provider': 'xai',
                        'prediction': alt_data.get('prediction', 'NEUTRAL'),
                        'confidence': alt_data.get('confidence', 0.5),
                        'reasoning': alt_data.get('reasoning', 'No reasoning')
                    })
                except:
                    pass
            except Exception as e:
                logger.warning(f'Secondary analyst failed: {e}')

            if not analyst_reports:
                logger.warning(f'No analyst reports generated for {symbol}')
                return

            # 3. Head of Research (Gemini) Debate and Consensus
            logger.info(f'[{symbol}] Moderating debate between {len(analyst_reports)} analysts')
            consensus = self.prediction_service.debate_and_vote(symbol, stock_data, analyst_reports)
            
            if not consensus:
                logger.warning(f'Failed to reach consensus for {symbol}')
                return

            # --- STORAGE PHASE ---
            # Get current price for initial_price
            current_price = stock_data['current_price']
            from datetime import timedelta
            target_time = datetime.now() + timedelta(days=7)

            # Map prediction direction to database format
            direction_map = {'UP': 'up', 'DOWN': 'down', 'NEUTRAL': 'neutral'}
            
            # Store individual analyst reports
            for report in analyst_reports:
                db.add_prediction(
                    cycle_id=cycle_id,
                    stock_id=stock_id,
                    provider=report['provider'],
                    predicted_direction=direction_map.get(report['prediction'].upper(), 'neutral'),
                    confidence=report['confidence'],
                    reasoning=report['reasoning'],
                    initial_price=current_price,
                    target_time=target_time
                )

            # Store the final consensus prediction
            prediction_id = db.add_prediction(
                cycle_id=cycle_id,
                stock_id=stock_id,
                provider=f"{consensus['provider']}-consensus",
                predicted_direction=direction_map.get(consensus['prediction'].upper(), 'neutral'),
                confidence=consensus['confidence'],
                reasoning=consensus['reasoning'],
                initial_price=current_price,
                target_time=target_time
            )

            logger.info(f'Consensus reached for {symbol}: {consensus["prediction"]} (confidence: {consensus["confidence"]:.2f})')

        except Exception as e:
            logger.error(f'Error processing stock {symbol}: {e}', exc_info=True)

        except Exception as e:
            logger.error(f'Error processing stock {symbol}: {e}', exc_info=True)

    def is_alive(self) -> bool:
        """Check if worker thread is alive"""
        return self.thread.is_alive() if self.thread else False

    def get_status(self) -> dict:
        """Get worker status"""
        import time
        status = {
            'running': self.running,
            'thread_alive': self.is_alive(),
            'current_cycle_id': self.current_cycle_id,
            'total_cycles_completed': self.total_cycles_completed,
            'last_cycle_time': self.last_cycle_time
        }

        # Check if worker is stale (no cycle in >2x interval)
        if self.last_cycle_time:
            time_since_last = time.time() - self.last_cycle_time
            max_allowed = self.config['CYCLE_INTERVAL'] * 2
            status['is_healthy'] = time_since_last < max_allowed
            status['seconds_since_last_cycle'] = int(time_since_last)
        else:
            status['is_healthy'] = True if self.is_alive() else False
            status['seconds_since_last_cycle'] = None

        return status
