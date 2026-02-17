"""
Prediction service
Handles LLM-based stock predictions
"""
import sys
import json
import re
import sqlite3
from typing import Dict, Optional, List
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
        self.db_path = config.get('DB_PATH')
        self.providers = {}
        self.provider_runtime = {}

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
                self._mark_provider_success(provider_name)

            except Exception as e:
                logger.error(f'Failed to initialize {provider_name} for {role}: {str(e)}')
                self._mark_provider_failure(provider_name, e)

    def _complete_with_optional_model(self, provider, messages, model=None):
        """
        Call provider.complete without passing model when unset.
        Some provider SDKs reject model=None.
        """
        kwargs = {'messages': messages}
        if model:
            kwargs['model'] = model
        return provider.complete(**kwargs)

    def _mark_provider_success(self, provider_name: str):
        state = self.provider_runtime.setdefault(provider_name, {})
        state['healthy'] = True
        state['last_error'] = None
        state['last_failed_at'] = None
        self._persist_provider_runtime(provider_name, True, None)

    def _mark_provider_failure(self, provider_name: str, error: Exception):
        from datetime import datetime
        state = self.provider_runtime.setdefault(provider_name, {})
        state['healthy'] = False
        state['last_error'] = str(error)
        state['last_failed_at'] = datetime.now().isoformat()
        self._persist_provider_runtime(provider_name, False, str(error))

    def _persist_provider_runtime(self, provider_name: str, healthy: bool, error: Optional[str]):
        """Persist provider runtime status to SQLite so all processes share it."""
        if not self.db_path:
            return
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS provider_runtime (
                    provider TEXT PRIMARY KEY,
                    healthy INTEGER NOT NULL DEFAULT 1,
                    last_error TEXT,
                    last_failed_at TEXT,
                    last_success_at TEXT
                )
            """)
            if healthy:
                conn.execute("""
                    INSERT INTO provider_runtime(provider, healthy, last_error, last_failed_at, last_success_at)
                    VALUES (?, 1, NULL, NULL, datetime('now'))
                    ON CONFLICT(provider) DO UPDATE SET
                        healthy=1,
                        last_error=NULL,
                        last_failed_at=NULL,
                        last_success_at=datetime('now')
                """, (provider_name,))
            else:
                conn.execute("""
                    INSERT INTO provider_runtime(provider, healthy, last_error, last_failed_at, last_success_at)
                    VALUES (?, 0, ?, datetime('now'), NULL)
                    ON CONFLICT(provider) DO UPDATE SET
                        healthy=0,
                        last_error=excluded.last_error,
                        last_failed_at=datetime('now')
                """, (provider_name, error or 'Unknown provider error'))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f'Failed to persist provider runtime status for {provider_name}: {e}')

    def get_provider_runtime_status(self) -> Dict:
        """
        Return provider runtime health based on init + most recent calls.
        """
        providers = set(self.provider_runtime.keys())
        providers.update(self.config.get('PROVIDERS', {}).values())
        status = {}
        for name in providers:
            base = self.provider_runtime.get(name, {})
            status[name] = {
                'healthy': base.get('healthy', True),
                'last_error': base.get('last_error'),
                'last_failed_at': base.get('last_failed_at')
            }

        # Merge persisted status from SQLite so runtime errors are visible across processes
        if self.db_path:
            try:
                conn = sqlite3.connect(self.db_path, timeout=5)
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT provider, healthy, last_error, last_failed_at FROM provider_runtime").fetchall()
                conn.close()
                for row in rows:
                    status[row['provider']] = {
                        'healthy': bool(row['healthy']),
                        'last_error': row['last_error'],
                        'last_failed_at': row['last_failed_at']
                    }
            except Exception as e:
                logger.debug(f'Failed reading provider_runtime table: {e}')
        return status

    @staticmethod
    def base_provider_weights() -> Dict[str, float]:
        """
        Baseline trust weights before performance adjustment.
        """
        return {
            'xai': 1.0,         # cheap search/context
            'gemini': 1.0,      # cheap synthesis/search
            'anthropic': 1.2,   # strong reasoning
            'openai': 1.2,      # strong reasoning
            'perplexity': 1.1,  # web-grounded
            'mistral': 0.8,     # side input
            'cohere': 0.6,      # low default weight
        }

    def build_provider_weights(self, performance_map: Dict[str, float]) -> Dict[str, float]:
        """
        Build dynamic provider weights using historical accuracy where available.
        """
        weights = {}
        for provider, base in self.base_provider_weights().items():
            acc = performance_map.get(provider)
            if acc is None:
                # Neutral prior when provider has no evaluated history
                factor = 1.0
            else:
                # Map accuracy [0..1] to factor [0.5..1.5]
                factor = max(0.5, min(1.5, 0.5 + float(acc)))
            weights[provider] = round(base * factor, 4)
        return weights

    def debate_and_vote(self, symbol: str, stock_data: Dict, analyst_predictions: list) -> Optional[Dict]:
        """
        Have a lead agent synthesize multiple predictions into a final consensus
        """
        # Try multiple potential synthesis providers in order of preference
        synthesis_providers = ['gemini', 'xai', 'mistral']
        
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

        for p_name in synthesis_providers:
            try:
                # Get the provider instance (either from our initialized ones or factory)
                provider = None
                for role, p in self.providers.items():
                    if self.config['PROVIDERS'].get(role) == p_name:
                        provider = p
                        break
                
                if not provider:
                    provider = ProviderFactory.get_provider(p_name)
                
                model = self.config.get('MODEL_OVERRIDES', {}).get(p_name)
                
                from llm_providers import Message
                response = self._complete_with_optional_model(
                    provider,
                    messages=[Message(role='user', content=prompt)],
                    model=model
                )

                import json
                import re
                
                # Clean response
                content = response.content.strip()
                if content.startswith('```'):
                    content = re.sub(r'^```json\s*|\s*```$', '', content, flags=re.MULTILINE)
                
                result = json.loads(content)
                self._mark_provider_success(p_name)

                return {
                    'provider': p_name,
                    'model': getattr(provider, 'model', 'unknown'),
                    'prediction': str(result.get('consensus_direction', 'NEUTRAL')).lower(),
                    'confidence': result.get('consensus_confidence', 0.5),
                    'reasoning': result.get('synthesis_reasoning', 'No synthesis reasoning provided')
                }

            except Exception as e:
                logger.warning(f'Synthesis failed with {p_name}: {e}')
                self._mark_provider_failure(p_name, e)
                continue
        
        logger.error(f'All synthesis providers failed for {symbol}')
        return None

    def discover_stocks(self, count: int = 10) -> list:
        """
        Use LLM to discover interesting stocks

        Args:
            count: Number of stocks to discover

        Returns:
            List of stock symbols
        """
        prompt = f"""You are a stock market analyst. Identify {count} publicly traded stocks
that are currently interesting for short-term trading (next 1-7 days).

Focus on stocks with:
- Recent news or events
- High volatility
- Strong market interest
- Clear trading signals

Return ONLY a JSON array of ticker symbols, nothing else.
Example: ["AAPL", "MSFT", "TSLA"]"""

        # Discovery fallback chain: configured provider first, then alternates.
        primary = self.config['PROVIDERS'].get('discovery')
        chain = [primary, 'xai', 'anthropic', 'gemini', 'mistral']
        chain = list(dict.fromkeys([p for p in chain if p]))

        from llm_providers import Message
        last_error = None

        for provider_name in chain:
            try:
                provider = None
                for role, p in self.providers.items():
                    if self.config['PROVIDERS'].get(role) == provider_name:
                        provider = p
                        break
                if not provider:
                    provider = ProviderFactory.get_provider(provider_name)

                model = self.config.get('MODEL_OVERRIDES', {}).get(provider_name)
                logger.debug(f'Using {provider_name} ({model or "default"}) for stock discovery')
                response = self._complete_with_optional_model(
                    provider,
                    messages=[Message(role='user', content=prompt)],
                    model=model
                )

                symbols = self._parse_discovery_symbols(response.content, count)
                if symbols:
                    self._mark_provider_success(provider_name)
                    logger.info(f'Stock discovery succeeded with {provider_name}: {symbols}')
                    return symbols

                # Empty parse is a soft failure for this provider
                err = ValueError(f'{provider_name} returned no parseable symbols')
                self._mark_provider_failure(provider_name, err)
                last_error = err

            except Exception as e:
                self._mark_provider_failure(provider_name, e)
                last_error = e
                logger.warning(f'Discovery failed with {provider_name}: {e}')

        if last_error:
            logger.error(f'Error discovering stocks: {last_error}')
        return []

    def discover_stocks_debate(self, count: int, provider_weights: Dict[str, float]) -> List[str]:
        """
        Multi-provider discovery debate:
        1) xAI + Gemini (cheap, fast)
        2) Anthropic + OpenAI + Perplexity (join)
        3) Mistral + Cohere (side input)
        Returns weighted-vote top symbols.
        """
        stage_order = ['xai', 'gemini', 'anthropic', 'openai', 'perplexity', 'mistral', 'cohere']
        votes: Dict[str, float] = {}
        provenance: Dict[str, List[str]] = {}

        for provider_name in stage_order:
            try:
                symbols = self._discover_symbols_from_provider(provider_name, count)
                if not symbols:
                    continue
                weight = provider_weights.get(provider_name, self.base_provider_weights().get(provider_name, 1.0))
                for symbol in symbols:
                    votes[symbol] = votes.get(symbol, 0.0) + weight
                    provenance.setdefault(symbol, []).append(provider_name)
                logger.info(f'Discovery vote from {provider_name}: {symbols} (weight={weight:.2f})')
            except Exception as e:
                self._mark_provider_failure(provider_name, e)
                logger.warning(f'Discovery debate provider failed ({provider_name}): {e}')

        ranked = sorted(votes.items(), key=lambda x: x[1], reverse=True)
        symbols = [symbol for symbol, _ in ranked[:count]]
        if symbols:
            logger.info(f'Discovery debate selected: {symbols} | provenance: {provenance}')
        return symbols

    def _discover_symbols_from_provider(self, provider_name: str, count: int) -> List[str]:
        """Run discovery prompt with a specific provider."""
        provider = None
        for role, p in self.providers.items():
            if self.config['PROVIDERS'].get(role) == provider_name:
                provider = p
                break
        if not provider:
            provider = ProviderFactory.get_provider(provider_name)

        model = self.config.get('MODEL_OVERRIDES', {}).get(provider_name)
        prompt = f"""You are a stock market analyst. Identify {count} publicly traded stocks
that are currently interesting for short-term trading (next 1-7 days).

Focus on stocks with:
- Recent news or events
- High volatility
- Strong market interest
- Clear trading signals

Return ONLY a JSON array of ticker symbols, nothing else.
Example: ["AAPL", "MSFT", "TSLA"]"""

        from llm_providers import Message
        response = self._complete_with_optional_model(
            provider,
            messages=[Message(role='user', content=prompt)],
            model=model
        )
        symbols = self._parse_discovery_symbols(response.content, count)
        if symbols:
            self._mark_provider_success(provider_name)
        else:
            self._mark_provider_failure(provider_name, ValueError('No parseable symbols'))
        return symbols

    def _parse_discovery_symbols(self, content: str, count: int) -> list:
        """Parse provider output into a deduplicated ticker list."""
        if not content:
            return []

        text = content.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text)

        def normalize(items):
            out = []
            seen = set()
            for item in items:
                if not isinstance(item, str):
                    continue
                symbol = item.strip().upper()
                if not re.fullmatch(r'[A-Z]{1,6}', symbol):
                    continue
                if symbol in seen:
                    continue
                seen.add(symbol)
                out.append(symbol)
                if len(out) >= count:
                    break
            return out

        # 1) Strict JSON parse
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                result = normalize(parsed)
                if result:
                    return result
            if isinstance(parsed, dict):
                for key in ('symbols', 'tickers', 'stocks'):
                    if isinstance(parsed.get(key), list):
                        result = normalize(parsed[key])
                        if result:
                            return result
        except Exception:
            pass

        # 2) Extract first JSON array substring from a verbose response
        array_match = re.search(r'\[[\s\S]*?\]', text)
        if array_match:
            try:
                parsed = json.loads(array_match.group(0))
                if isinstance(parsed, list):
                    result = normalize(parsed)
                    if result:
                        return result
            except Exception:
                pass

        # 3) Fallback: find ticker-like tokens in plain text
        token_matches = re.findall(r'\b[A-Z]{1,6}\b', text.upper())
        result = normalize(token_matches)
        return result

    def generate_prediction(self, symbol: str, stock_data: Dict, provider_name: Optional[str] = None) -> Optional[Dict]:
        """
        Generate prediction for a stock using a specific provider or the default 'prediction' role.
        """
        # For explicit multi-analyst roles, do not silently substitute a different provider.
        # This preserves role diversity (e.g., Anthropic, xAI, Mistral, Perplexity).
        if provider_name:
            fallback_chain = [provider_name]
        else:
            fallback_chain = [self.config['PROVIDERS'].get('prediction', 'anthropic'), 'xai', 'mistral', 'gemini']
            # Remove duplicates while preserving order
            fallback_chain = list(dict.fromkeys([p for p in fallback_chain if p]))

        for p_name in fallback_chain:
            try:
                # Check if we have this provider initialized for any role
                target_provider = None
                for r, p in self.providers.items():
                    if self.config['PROVIDERS'].get(r) == p_name:
                        target_provider = p
                        break
                
                if not target_provider:
                    target_provider = ProviderFactory.get_provider(p_name)
                
                model = self.config.get('MODEL_OVERRIDES', {}).get(p_name)
                if model:
                    target_provider.model = model

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
                response = self._complete_with_optional_model(
                    target_provider,
                    messages=[Message(role='user', content=prompt)],
                    model=model
                )

                import json
                import re
                content = response.content.strip()
                if content.startswith('```'):
                    content = re.sub(r'^```json\s*|\s*```$', '', content, flags=re.MULTILINE)
                
                prediction = json.loads(content)
                self._mark_provider_success(p_name)

                return {
                    'provider': p_name,
                    'model': model or getattr(target_provider, 'model', 'unknown'),
                    'prediction': str(prediction.get('prediction', 'NEUTRAL')).lower(),
                    'confidence': prediction.get('confidence', 0.5),
                    'reasoning': prediction.get('reasoning', 'No reasoning provided')
                }

            except Exception as e:
                logger.warning(f'Prediction failed with {p_name} for {symbol}: {e}')
                self._mark_provider_failure(p_name, e)
                continue
        
        logger.error(f'All prediction providers failed for {symbol}')
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
            response = self._complete_with_optional_model(
                provider,
                messages=[Message(role='user', content=prompt)],
                model=model
            )

            # Parse float response (response is CompletionResponse object)
            confidence = float(response.content.strip())
            return max(0.0, min(1.0, confidence))

        except Exception as e:
            logger.error(f'Error synthesizing confidence: {str(e)}')
            return None
