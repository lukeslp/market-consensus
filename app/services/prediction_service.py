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
        overrides = self.config.get('MODEL_OVERRIDES', {})
        for role, provider_name in self.config['PROVIDERS'].items():
            try:
                # Use model override if specified for this provider
                model = overrides.get(provider_name)
                
                # We need to use ProviderFactory to get the provider
                provider = ProviderFactory.get_provider(provider_name)
                
                # Manually override the model if specified
                if model:
                    provider.model = model
                    logger.info(f'Initialized {provider_name} for {role} using model {model}')
                else:
                    logger.info(f'Initialized {provider_name} for {role}')
                
                self.providers[role] = provider

            except Exception as e:
                logger.error(f'Failed to initialize {provider_name} for {role}: {str(e)}')

    def debate_and_vote(self, symbol: str, stock_data: Dict, analyst_predictions: list) -> Optional[Dict]:
        """
        Have a lead agent synthesize multiple predictions into a final consensus

        Args:
            symbol: Stock symbol
            stock_data: Technical data
            analyst_predictions: List of individual analyses

        Returns:
            Consensus prediction dict
        """
        if 'synthesis' not in self.providers:
            logger.error('Synthesis provider not configured')
            return None

        try:
            provider = self.providers['synthesis']
            provider_name = self.config['PROVIDERS']['synthesis']
            model = self.config.get('MODEL_OVERRIDES', {}).get(provider_name)
            
            # Format predictions for the prompt
            debate_context = ""
            for i, pred in enumerate(analyst_predictions):
                debate_context += f"Analyst {i+1} ({pred['provider']}):\n"
                debate_context += f"Direction: {pred['prediction']}\n"
                debate_context += f"Confidence: {pred['confidence']}\n"
                debate_context += f"Reasoning: {pred['reasoning']}\n\n"

            prompt = f"""You are the Head of Research at a top-tier hedge fund. 
Your analysts have provided conflicting technical reports on {symbol}.

Symbol: {symbol}
Current Price: ${stock_data.get('current_price', 'N/A')}

Analyst Reports:
{debate_context}

Your task is to:
1. Moderate the debate between these perspectives.
2. Evaluate which reasoning is most grounded in the technical data.
3. Provide a final 'Hedge Fund Consensus' vote.

Return your final decision as JSON:
{{
    "consensus_direction": "UP|DOWN|NEUTRAL",
    "consensus_confidence": 0.82,
    "synthesis_reasoning": "A brief summary of the debate and why this conclusion was reached."
}}"""

            from llm_providers import Message
            response = provider.complete(
                messages=[Message(role='user', content=prompt)],
                model=model
            )

            import json
            import re
            
            # Clean response if it contains markdown code blocks
            content = response.content.strip()
            if content.startswith('```'):
                content = re.sub(r'^```json\s*|\s*```$', '', content, flags=re.MULTILINE)
            
            result = json.loads(content)

            return {
                'provider': self.config['PROVIDERS']['synthesis'],
                'model': getattr(provider, 'model', 'unknown'),
                'prediction': str(result.get('consensus_direction', 'NEUTRAL')).upper(),
                'confidence': result.get('consensus_confidence', 0.5),
                'reasoning': result.get('synthesis_reasoning', 'No synthesis reasoning provided')
            }

        except Exception as e:
            logger.error(f'Error in debate/vote for {symbol}: {str(e)}')
            return None

    def discover_stocks(self, count: int = 10) -> list:
        """
        Use LLM to discover interesting stocks

        Args:
            count: Number of stocks to discover

        Returns:
            List of stock symbols
        """
        if 'discovery' not in self.providers:
            logger.error('Discovery provider not configured. Available providers: %s', list(self.providers.keys()))
            return []

        try:
            provider = self.providers['discovery']
            provider_name = self.config['PROVIDERS']['discovery']
            model = self.config.get('MODEL_OVERRIDES', {}).get(provider_name)
            logger.debug(f'Using {provider.__class__.__name__} ({model or "default"}) for stock discovery')

            prompt = f"""You are a stock market analyst. Identify {count} publicly traded stocks
that are currently interesting for short-term trading (next 1-7 days).

Focus on stocks with:
- Recent news or events
- High volatility
- Strong market interest
- Clear trading signals

Return ONLY a JSON array of ticker symbols, nothing else.
Example: ["AAPL", "MSFT", "TSLA"]"""

            # Use standard provider interface: complete(messages)
            from llm_providers import Message
            logger.debug(f'Calling provider.complete() for stock discovery')
            response = provider.complete(
                messages=[Message(role='user', content=prompt)],
                model=model
            )
            logger.debug(f'Provider returned: {response.content[:200]}...')

            # Parse JSON response (response is CompletionResponse object)
            import json
            symbols = json.loads(response.content)
            logger.debug(f'Parsed symbols: {symbols}')

            if isinstance(symbols, list):
                result = [s.upper() for s in symbols[:count]]
                logger.debug(f'Discovery returning: {result}')
                return result

            logger.warning(f'Response was not a list: {type(symbols)}')
            return []

        except Exception as e:
            logger.error(f'Error discovering stocks: {str(e)}')
            return []

    def generate_prediction(self, symbol: str, stock_data: Dict, provider_name: Optional[str] = None) -> Optional[Dict]:
        """
        Generate prediction for a stock using a specific provider or the default 'prediction' role.
        
        Args:
            symbol: Stock symbol
            stock_data: Technical data
            provider_name: Specific provider name (e.g., 'anthropic', 'xai', 'mistral', 'perplexity')
                           If None, uses the default 'prediction' role from config.
        """
        if provider_name:
            # Check if we have this provider initialized for any role, or get it from factory
            target_provider = None
            for r, p in self.providers.items():
                if self.config['PROVIDERS'].get(r) == provider_name:
                    target_provider = p
                    break
            
            if not target_provider:
                try:
                    target_provider = ProviderFactory.get_provider(provider_name)
                    # Set model from overrides if available
                    model = self.config.get('MODEL_OVERRIDES', {}).get(provider_name)
                    if model:
                        target_provider.model = model
                except Exception as e:
                    logger.error(f'Failed to get provider {provider_name}: {e}')
                    return None
        else:
            if 'prediction' not in self.providers:
                logger.error('Prediction provider not configured')
                return None
            target_provider = self.providers['prediction']
            provider_name = self.config['PROVIDERS']['prediction']

        try:
            model = self.config.get('MODEL_OVERRIDES', {}).get(provider_name)

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

            from llm_providers import Message
            response = target_provider.complete(
                messages=[Message(role='user', content=prompt)],
                model=model
            )

            # Parse JSON response (response is CompletionResponse object)
            import json
            import re
            content = response.content.strip()
            if content.startswith('```'):
                content = re.sub(r'^```json\s*|\s*```$', '', content, flags=re.MULTILINE)
            
            prediction = json.loads(content)

            return {
                'provider': provider_name,
                'model': model or getattr(target_provider, 'model', 'unknown'),
                'prediction': str(prediction.get('prediction', 'NEUTRAL')).upper(),
                'confidence': prediction.get('confidence', 0.5),
                'reasoning': prediction.get('reasoning', 'No reasoning provided')
            }

        except Exception as e:
            logger.error(f'Error generating prediction for {symbol} using {provider_name}: {str(e)}')
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
            provider_name = self.config['PROVIDERS']['synthesis']
            model = self.config.get('MODEL_OVERRIDES', {}).get(provider_name)

            prompt = f"""You are analyzing multiple stock predictions.
Synthesize these predictions into a single confidence score (0.0 to 1.0).

Predictions:
{predictions}

Consider:
- Agreement between predictions
- Confidence levels
- Quality of reasoning

Return ONLY a number between 0.0 and 1.0, nothing else."""

            from llm_providers import Message
            response = provider.complete(
                messages=[Message(role='user', content=prompt)],
                model=model
            )

            # Parse float response (response is CompletionResponse object)
            confidence = float(response.content.strip())
            return max(0.0, min(1.0, confidence))

        except Exception as e:
            logger.error(f'Error synthesizing confidence: {str(e)}')
            return None
