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
    DEFAULT_ANTHROPIC_MODEL = 'claude-sonnet-4-6'
    DEPRECATED_ANTHROPIC_MODELS = {
        'claude-3-5-sonnet-20241022',
        'claude-3-5-sonnet-latest',
        'claude-3-5-sonnet-20240620',
        'claude-sonnet-4-20250514',
    }

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
        """Initialize all council providers from PROVIDER_ORDER config."""
        provider_order = self.config.get(
            'PROVIDER_ORDER',
            ['anthropic', 'openai', 'gemini', 'xai', 'perplexity', 'mistral', 'huggingface', 'cohere']
        )
        for provider_name in provider_order:
            try:
                provider = ProviderFactory.get_provider(provider_name)
                model = self._resolve_model(provider_name, provider)
                if model:
                    provider.model = model
                    logger.info(f'Initialized {provider_name} using model {model}')
                else:
                    logger.info(f'Initialized {provider_name}')
                self.providers[provider_name] = provider
                self._mark_provider_success(provider_name)
            except Exception as e:
                logger.error(f'Failed to initialize {provider_name}: {str(e)}')
                self._mark_provider_failure(provider_name, e)

    def _resolve_model(self, provider_name: str, provider_obj=None) -> Optional[str]:
        """
        Resolve effective model for provider with defensive upgrade rules.
        """
        configured = self.config.get('MODEL_OVERRIDES', {}).get(provider_name)
        current = getattr(provider_obj, 'model', None) if provider_obj else None
        model = configured or current

        # Force-upgrade deprecated Anthropic defaults even if inherited upstream.
        if provider_name == 'anthropic':
            if not model or model in self.DEPRECATED_ANTHROPIC_MODELS:
                return self.DEFAULT_ANTHROPIC_MODEL
        return model

    def _get_provider(self, provider_name: str):
        """
        Get a provider instance by name.
        Checks cached providers dict first, falls back to ProviderFactory.
        """
        if provider_name in self.providers:
            return self.providers[provider_name]
        return ProviderFactory.get_provider(provider_name)

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
        Baseline trust weights. Premium tier (Claude/ChatGPT/Gemini) at 1.5×,
        xai mid at 1.1×, rest lower. Override per-provider via config.
        """
        return {
            'anthropic':   1.5,   # premium — strongest reasoning
            'openai':      1.5,   # premium — strong reasoning
            'gemini':      1.5,   # premium — strong synthesis/search
            'xai':         1.1,   # mid-tier — fast context/search
            'perplexity':  0.9,   # web-grounded, good for news
            'mistral':     0.8,   # standard
            'huggingface': 0.85,  # open-weight Llama, diversity input
            'cohere':      0.6,   # trial limits, low default
        }

    def get_configured_base_weights(self) -> Dict[str, float]:
        """Base weights with any per-provider overrides from PROVIDER_WEIGHTS config."""
        base = dict(self.base_provider_weights())
        overrides = self.config.get('PROVIDER_WEIGHTS', {})
        for p, w in overrides.items():
            base[p] = float(w)
        return base

    def build_provider_weights(self, performance_map: Dict[str, float]) -> Dict[str, float]:
        """
        Build dynamic provider weights using historical accuracy where available.
        """
        weights = {}
        for provider, base in self.get_configured_base_weights().items():
            acc = performance_map.get(provider)
            if acc is None:
                factor = 1.0
            else:
                # Map accuracy [0..1] to factor [0.5..1.5]
                factor = max(0.5, min(1.5, 0.5 + float(acc)))
            weights[provider] = round(base * factor, 4)
        return weights

    def _provider_stage(self, provider_name: str) -> str:
        if provider_name in ('anthropic', 'openai', 'gemini'):
            return 'premium'
        if provider_name == 'xai':
            return 'mid'
        return 'standard'  # perplexity, mistral, cohere, huggingface

    def synthesize_council_swarm(
        self,
        symbol: str,
        stock_data: Dict,
        analyst_predictions: list,
        provider_weights: Dict[str, float],
        stage_order: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """
        Final-stage synthesis as a provider democracy (no single lead model).
        """
        if not analyst_predictions:
            return None

        if not stage_order:
            stage_order = ['xai', 'gemini', 'anthropic', 'openai', 'perplexity', 'mistral', 'cohere']
        debate_context = ""
        for i, pred in enumerate(analyst_predictions):
            debate_context += f"Analyst {i+1} ({pred['provider']} / {pred.get('stage', 'n/a')}):\n"
            debate_context += f"Direction: {pred['prediction']}\n"
            debate_context += f"Confidence: {pred['confidence']}\n"
            debate_context += f"Reasoning: {pred['reasoning']}\n\n"

        reports = []
        from llm_providers import Message
        for provider_name in stage_order:
            try:
                provider = self._get_provider(provider_name)

                model = self._resolve_model(provider_name, provider)
                if model:
                    provider.model = model

                prompt = f"""You are one voting member of a hedge fund research council.
Debate and vote on the best short-term direction for {symbol} over the next prediction window.

Symbol: {symbol}
Current Price: ${stock_data.get('current_price', 'N/A')}

Analyst Reports:
{debate_context}

Return JSON only:
{{
  "prediction": "UP|DOWN|NEUTRAL",
  "confidence": 0.0,
  "reasoning": "Concise explanation of your vote based on the debate."
}}"""
                response = self._complete_with_optional_model(
                    provider,
                    messages=[Message(role='user', content=prompt)],
                    model=model
                )
                parsed = self._parse_prediction_json(response.content)
                if not parsed:
                    continue
                parsed.update({
                    'provider': provider_name,
                    'stage': self._provider_stage(provider_name),
                    'model': model or getattr(provider, 'model', 'unknown'),
                    'raw_response': response.content,
                    'prompt': prompt,
                    'usage': getattr(response, 'usage', None) or {},
                    'response_model': getattr(response, 'model', model) or model,
                })
                reports.append(parsed)
                self._mark_provider_success(provider_name)
            except Exception as e:
                logger.warning(f'Final synthesis failed with {provider_name}: {e}')
                self._mark_provider_failure(provider_name, e)

        if not reports:
            return None

        vote_totals = {'up': 0.0, 'down': 0.0, 'neutral': 0.0}
        lines = []
        for report in reports:
            direction = report['prediction'] if report['prediction'] in vote_totals else 'neutral'
            confidence = float(report.get('confidence') or 0.5)
            weight = float(provider_weights.get(report['provider'], 1.0))
            score = max(0.05, confidence) * weight
            vote_totals[direction] += score
            lines.append(
                f"{report['provider']} [{report['stage']}]: dir={direction} conf={confidence:.2f} weight={weight:.2f} score={score:.2f}; reason={report.get('reasoning','')}"
            )

        winning_direction = max(vote_totals.items(), key=lambda x: x[1])[0]
        total_score = sum(vote_totals.values()) or 1.0
        confidence = vote_totals[winning_direction] / total_score
        reasoning = (
            f"Democratic synthesis vote totals: up={vote_totals['up']:.2f}, down={vote_totals['down']:.2f}, neutral={vote_totals['neutral']:.2f}. "
            f"Winner={winning_direction}. Individual synthesis votes: " + " | ".join(lines)
        )

        return {
            'provider': 'council-swarm',
            'model': 'multi-provider',
            'prediction': winning_direction,
            'confidence': confidence,
            'reasoning': reasoning,
            'reports': reports,
            'vote_totals': vote_totals,
        }

    def discover_stocks(self, count: int = 10) -> list:
        """
        Use LLM to discover interesting stocks

        Args:
            count: Number of stocks to discover

        Returns:
            List of stock symbols
        """
        prompt = f"""You are a stock market analyst. Identify {count} publicly traded stocks
that are currently interesting for short-term trading (next 30 minutes to 2.5 hours).

Focus on stocks with:
- Recent news or events
- High volatility or momentum
- Strong market interest
- Clear short-term trading signals

Return ONLY a JSON array of ticker symbols, nothing else.
Example: ["AAPL", "MSFT", "TSLA"]"""

        # Discovery fallback chain: configured provider first, then alternates.
        primary = self.config.get('PROVIDERS', {}).get('discovery', 'xai')
        chain = [primary, 'xai', 'anthropic', 'gemini', 'mistral']
        chain = list(dict.fromkeys([p for p in chain if p]))

        from llm_providers import Message
        last_error = None

        for provider_name in chain:
            try:
                provider = self._get_provider(provider_name)

                model = self._resolve_model(provider_name, provider)
                if model:
                    provider.model = model
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

    def discover_stocks_debate(
        self,
        count: int,
        provider_weights: Dict[str, float],
        stage_order: Optional[List[str]] = None
    ) -> List[str]:
        """
        Multi-provider discovery debate:
        1) xAI + Gemini (cheap, fast)
        2) Anthropic + OpenAI + Perplexity (join)
        3) Mistral + Cohere (side input)
        Returns weighted-vote top symbols.
        """
        if not stage_order:
            stage_order = ['xai', 'gemini', 'anthropic', 'openai', 'perplexity', 'mistral', 'cohere']
        votes: Dict[str, float] = {}
        provenance: Dict[str, List[str]] = {}

        for provider_name in stage_order:
            try:
                symbols = self._discover_symbols_from_provider_swarm(provider_name, count)
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

    def _discover_symbols_from_provider_swarm(self, provider_name: str, count: int) -> List[str]:
        """
        Provider-internal discovery swarm: multiple cheap roles vote on tickers.
        """
        provider = self._get_provider(provider_name)

        model = self._resolve_model(provider_name, provider)
        if model:
            provider.model = model

        n = max(1, int(self.config.get('SWARM_SUBAGENTS_PER_PROVIDER', 2)))
        personas = ['momentum scanner', 'news catalyst scout', 'volatility hunter', 'contrarian screener'][:n]
        symbol_votes: Dict[str, float] = {}

        from llm_providers import Message
        for persona in personas:
            prompt = f"""You are a {persona} for short-term equity ideas.
List {count} US ticker symbols for likely movement in the next 30 minutes to 2.5 hours.
Prioritize names with fresh catalysts from the latest market/news context.

Return ONLY a JSON array of ticker symbols.
Example: ["AAPL", "MSFT", "TSLA"]"""
            try:
                response = self._complete_with_optional_model(
                    provider,
                    messages=[Message(role='user', content=prompt)],
                    model=model
                )
                symbols = self._parse_discovery_symbols(response.content, count)
                for rank, symbol in enumerate(symbols):
                    symbol_votes[symbol] = symbol_votes.get(symbol, 0.0) + max(0.1, 1.0 - (rank * 0.1))
            except Exception as e:
                logger.warning(f'Discovery subagent {persona} failed for {provider_name}: {e}')

        if not symbol_votes:
            self._mark_provider_failure(provider_name, ValueError('No discovery swarm symbols'))
            return []

        ranked = sorted(symbol_votes.items(), key=lambda x: x[1], reverse=True)
        symbols = [symbol for symbol, _ in ranked[:count]]
        self._mark_provider_success(provider_name)
        return symbols

    def _discover_symbols_from_provider(self, provider_name: str, count: int) -> List[str]:
        """Run discovery prompt with a specific provider."""
        provider = self._get_provider(provider_name)

        model = self._resolve_model(provider_name, provider)
        if model:
            provider.model = model
        prompt = f"""You are a stock market analyst. Identify {count} publicly traded stocks
that are currently interesting for short-term trading (next 30 minutes to 2.5 hours).

Focus on stocks with:
- Recent news or events
- High volatility or momentum
- Strong market interest
- Clear short-term trading signals

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

        # Do not token-scan plain prose. It over-extracts words like "I" and "CANNOT"
        # from refusal/error text and pollutes discovery with non-symbols.
        return []

    def generate_prediction(self, symbol: str, stock_data: Dict, provider_name: Optional[str] = None) -> Optional[Dict]:
        """
        Generate prediction for a stock using a specific provider or the default 'prediction' role.
        """
        # For explicit multi-analyst roles, do not silently substitute a different provider.
        # This preserves role diversity (e.g., Anthropic, xAI, Mistral, Perplexity).
        if provider_name:
            fallback_chain = [provider_name]
        else:
            fallback_chain = [self.config.get('PROVIDERS', {}).get('prediction', 'anthropic'), 'xai', 'mistral', 'gemini']
            # Remove duplicates while preserving order
            fallback_chain = list(dict.fromkeys([p for p in fallback_chain if p]))

        for p_name in fallback_chain:
            try:
                target_provider = self._get_provider(p_name)
                
                model = self._resolve_model(p_name, target_provider)
                if model:
                    target_provider.model = model

                prompt = f"""Analyze this stock and make a short-term prediction (next 30 minutes to 2.5 hours):

Symbol: {symbol}
Current Price: ${stock_data.get('current_price', 'N/A')}
Recent Price Data: {stock_data.get('close', [])[-10:]}

Use both price action and recent news/catalyst context (if your provider has web/news access).
Based on that, predict:
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
                raw_content = content  # Preserve raw response before parsing
                if content.startswith('```'):
                    content = re.sub(r'^```json\s*|\s*```$', '', content, flags=re.MULTILINE)
                
                prediction = json.loads(content)
                self._mark_provider_success(p_name)

                return {
                    'provider': p_name,
                    'model': model or getattr(target_provider, 'model', 'unknown'),
                    'prediction': str(prediction.get('prediction', 'NEUTRAL')).lower(),
                    'confidence': prediction.get('confidence', 0.5),
                    'reasoning': prediction.get('reasoning', 'No reasoning provided'),
                    'raw_response': raw_content,
                    'prompt': prompt,
                    'usage': getattr(response, 'usage', None) or {},
                    'response_model': getattr(response, 'model', model) or model,
                }

            except Exception as e:
                logger.warning(f'Prediction failed with {p_name} for {symbol}: {e}')
                self._mark_provider_failure(p_name, e)
                continue
        
        logger.error(f'All prediction providers failed for {symbol}')
        return None

    def generate_prediction_swarm(
        self,
        symbol: str,
        stock_data: Dict,
        provider_name: str,
        subagents: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """
        Run provider-internal sub-agent debate and aggregate provider output.
        """
        if not provider_name:
            return None

        if not subagents:
            n = max(1, int(self.config.get('SWARM_SUBAGENTS_PER_PROVIDER', 2)))
            default_subagents = ['momentum', 'risk', 'news', 'contrarian']
            subagents = default_subagents[:n]

        provider = self._get_provider(provider_name)

        model = self._resolve_model(provider_name, provider)
        if model:
            provider.model = model
        reports = []

        from llm_providers import Message
        for agent in subagents:
            prompt = f"""You are a specialized equity analyst agent with the role: {agent}.
Analyze this stock and make a short-term prediction (next 30 minutes to 2.5 hours):

Symbol: {symbol}
Current Price: ${stock_data.get('current_price', 'N/A')}
Recent Price Data: {stock_data.get('close', [])[-10:]}
Recent context requirement: incorporate latest relevant headlines/catalysts when possible.

Return JSON only:
{{
  "prediction": "UP|DOWN|NEUTRAL",
  "confidence": 0.0,
  "reasoning": "2-3 concise sentences from the {agent} perspective"
}}"""
            try:
                response = self._complete_with_optional_model(
                    provider,
                    messages=[Message(role='user', content=prompt)],
                    model=model
                )
                parsed = self._parse_prediction_json(response.content)
                if not parsed:
                    continue
                parsed['subagent'] = agent
                parsed['raw_response'] = response.content
                parsed['prompt'] = prompt
                parsed['usage'] = getattr(response, 'usage', None) or {}
                parsed['response_model'] = getattr(response, 'model', model) or model
                reports.append(parsed)
            except Exception as e:
                logger.warning(f'Subagent {agent} failed with {provider_name} for {symbol}: {e}')

        if not reports:
            self._mark_provider_failure(provider_name, ValueError('No sub-agent reports generated'))
            return None

        vote = {'up': 0.0, 'down': 0.0, 'neutral': 0.0}
        for r in reports:
            pred = r.get('prediction', 'neutral')
            conf = float(r.get('confidence') or 0.5)
            vote[pred] = vote.get(pred, 0.0) + max(0.05, conf)

        winner = max(vote.items(), key=lambda x: x[1])[0]
        confidence = vote[winner] / (sum(vote.values()) or 1.0)
        reasoning = " || ".join([f"{r['subagent']}: {r.get('reasoning', '')}" for r in reports])
        self._mark_provider_success(provider_name)

        return {
            'provider': provider_name,
            'model': model or getattr(provider, 'model', 'unknown'),
            'prediction': winner,
            'confidence': confidence,
            'reasoning': reasoning,
            'subagents': reports
        }

    def _parse_prediction_json(self, content: str) -> Optional[Dict]:
        """Parse prediction JSON from provider response."""
        if not content:
            return None
        text = content.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text)
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                return None
            prediction = str(data.get('prediction', 'NEUTRAL')).strip().lower()
            if prediction not in ('up', 'down', 'neutral'):
                prediction = 'neutral'
            confidence = float(data.get('confidence', 0.5))
            confidence = max(0.0, min(1.0, confidence))
            return {
                'prediction': prediction,
                'confidence': confidence,
                'reasoning': str(data.get('reasoning', 'No reasoning provided')).strip()
            }
        except Exception:
            return None

    def synthesize_confidence(self, predictions: list) -> Optional[float]:
        """
        Use LLM to synthesize confidence from multiple predictions

        Args:
            predictions: List of prediction dicts

        Returns:
            Synthesized confidence score (0.0 to 1.0) or None
        """
        # Use configured synthesis provider, falling back to anthropic
        synthesis_name = self.config.get('PROVIDERS', {}).get('synthesis', 'anthropic')
        if synthesis_name not in self.providers and 'anthropic' not in self.providers:
            logger.error('Synthesis provider not configured')
            return None

        try:
            provider_name = synthesis_name
            provider = self._get_provider(provider_name)
            model = self._resolve_model(provider_name, provider)
            if model:
                provider.model = model

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
