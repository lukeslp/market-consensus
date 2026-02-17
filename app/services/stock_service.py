"""
Stock data service
Handles fetching and processing stock data
"""
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class StockService:
    """Service for stock data operations"""

    @staticmethod
    def fetch_stock_info(symbol: str) -> Optional[Dict]:
        """
        Fetch basic stock information

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with stock info or None if not found
        """
        try:
            stock = yf.Ticker(symbol)
            info = stock.info

            if not info or ('regularMarketPrice' not in info and 'currentPrice' not in info and 'longName' not in info):
                return None

            current_price = info.get('currentPrice', info.get('regularMarketPrice'))
            return {
                'symbol': symbol.upper(),
                'name': info.get('longName', symbol),
                'current_price': current_price,
                'price': current_price,  # Alias for compatibility
                'market_cap': info.get('marketCap'),
                'sector': info.get('sector'),
                'industry': info.get('industry')
            }

        except Exception as e:
            logger.error(f'Error fetching stock info for {symbol}: {str(e)}')
            return None

    @staticmethod
    def fetch_historical_data(symbol: str, days: int = 30) -> Optional[Dict]:
        """
        Fetch historical price data

        Args:
            symbol: Stock ticker symbol
            days: Number of days to look back

        Returns:
            Dict with historical data or None if not found
        """
        try:
            stock = yf.Ticker(symbol)
            start_date = datetime.now() - timedelta(days=days)

            hist = stock.history(start=start_date)

            if hist.empty:
                return None

            return {
                'symbol': symbol.upper(),
                'start_date': start_date.isoformat(),
                'end_date': datetime.now().isoformat(),
                'data_points': len(hist),
                'open': hist['Open'].tolist(),
                'high': hist['High'].tolist(),
                'low': hist['Low'].tolist(),
                'close': hist['Close'].tolist(),
                'volume': hist['Volume'].tolist(),
                'dates': [d.isoformat() for d in hist.index]
            }

        except Exception as e:
            logger.error(f'Error fetching historical data for {symbol}: {str(e)}')
            return None

    @staticmethod
    def validate_symbol(symbol: str) -> bool:
        """
        Validate if a stock symbol exists

        Args:
            symbol: Stock ticker symbol

        Returns:
            True if valid, False otherwise
        """
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            return 'symbol' in info or 'regularMarketPrice' in info

        except:
            return False

    @staticmethod
    def get_market_status() -> Dict:
        """
        Get current market status

        Returns:
            Dict with market status information
        """
        try:
            # Use SPY as a proxy for market hours
            spy = yf.Ticker('SPY')
            info = spy.info

            return {
                'is_open': info.get('marketState', 'CLOSED') == 'REGULAR',
                'market_state': info.get('marketState', 'UNKNOWN'),
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f'Error getting market status: {str(e)}')
            return {
                'is_open': False,
                'market_state': 'UNKNOWN',
                'timestamp': datetime.now().isoformat()
            }
