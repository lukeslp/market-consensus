"""
Prediction service
Handles LLM-based stock predictions
"""
import sys
from typing import Dict, Optional
import logging

# Import from shared library
from llm_providers import ProviderFactory

logger = logging.getLogger(__name__)


class PredictionService:
    """Service for generating stock predictions using language models"""

    def __init__(self, config):
        """
        Initialize prediction service

        Args:
            config: Flask config object
        """
        self.config = config
        self.providers = {}

        # Initialize configured providers
        self._init_providers()

    def _init_providers(self):
        """Initialize LLM providers from config"""
        for role, provider_name in self.config['PROVIDERS'].items():
            try:
                provider = ProviderFactory.get_provider(provider_name)
                self.providers[role] = provider
                logger.info(f'Initialized {provider_name} for {role}')

            except Exception as e:
                logger.error(f'Failed to initialize {provider_name} for {role}: {str(e)}')

    def discover_stocks(self, count: int = 10) -> list:
        """
        Use LLM to discover interesting stocks

        Args:
            count: Number of stocks to discover

        Returns:
            List of stock symbols
        """
        if 'discovery' not in self.providers:
            logger.error('Discovery provider not configured')
            return []

        try:
            provider = self.providers['discovery']

            prompt = f"""You are a stock market analyst. Identify {count} publicly traded stocks
that are currently interesting for short-term trading (next 1-7 days).

Focus on stocks with:
- Recent news or events
- High volatility
- Strong market interest
- Clear trading signals

Return ONLY a JSON array of ticker symbols, nothing else.
Example: ["AAPL", "MSFT", "TSLA"]"""

            response = provider.generate(prompt)

            # Parse JSON response
            import json
            symbols = json.loads(response)

            if isinstance(symbols, list):
                return [s.upper() for s in symbols[:count]]

            return []

        except Exception as e:
            logger.error(f'Error discovering stocks: {str(e)}')
            return []

    def generate_prediction(self, symbol: str, stock_data: Dict) -> Optional[Dict]:
        """
        Generate prediction for a stock

        Args:
            symbol: Stock ticker symbol
            stock_data: Historical stock data

        Returns:
            Dict with prediction details or None
        """
        if 'prediction' not in self.providers:
            logger.error('Prediction provider not configured')
            return None

        try:
            provider = self.providers['prediction']

            prompt = f"""Analyze this stock and make a short-term prediction (1-7 days):

Symbol: {symbol}
Current Price: ${stock_data.get('current_price', 'N/A')}
Recent Price Data: {stock_data.get('close', [])[-10:]}

Based on technical analysis of the recent price action, predict:
1. Direction (UP/DOWN/NEUTRAL)
2. Confidence (0.0 to 1.0)
3. Brief reasoning (2-3 sentences)

Return your response as JSON:
{{
    "prediction": "UP|DOWN|NEUTRAL",
    "confidence": 0.75,
    "reasoning": "Your reasoning here"
}}"""

            response = provider.generate(prompt)

            # Parse JSON response
            import json
            prediction = json.loads(response)

            return {
                'provider': self.config['PROVIDERS']['prediction'],
                'model': provider.model,
                'prediction': prediction.get('prediction', 'NEUTRAL'),
                'confidence': prediction.get('confidence', 0.5),
                'reasoning': prediction.get('reasoning', 'No reasoning provided')
            }

        except Exception as e:
            logger.error(f'Error generating prediction for {symbol}: {str(e)}')
            return None

    def synthesize_confidence(self, predictions: list) -> Optional[float]:
        """
        Use LLM to synthesize confidence from multiple predictions

        Args:
            predictions: List of prediction dicts

        Returns:
            Synthesized confidence score (0.0 to 1.0) or None
        """
        if 'synthesis' not in self.providers:
            logger.error('Synthesis provider not configured')
            return None

        try:
            provider = self.providers['synthesis']

            prompt = f"""You are analyzing multiple stock predictions.
Synthesize these predictions into a single confidence score (0.0 to 1.0).

Predictions:
{predictions}

Consider:
- Agreement between predictions
- Confidence levels
- Quality of reasoning

Return ONLY a number between 0.0 and 1.0, nothing else."""

            response = provider.generate(prompt)

            # Parse float response
            confidence = float(response.strip())
            return max(0.0, min(1.0, confidence))

        except Exception as e:
            logger.error(f'Error synthesizing confidence: {str(e)}')
            return None
