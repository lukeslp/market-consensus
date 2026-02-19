"""
Provider factory with lazy loading and singleton pattern.
Eliminates duplicate provider initialization code across services.

Usage:
    from shared.llm_providers.factory import ProviderFactory

    # Get a provider instance (lazily loaded, cached)
    provider = ProviderFactory.get_provider('xai')

    # Use the provider
    response = provider.analyze_image(img_bytes, "Describe this image")
"""

from typing import Dict, Optional, Any, List, Tuple


# Provider capability matrix
PROVIDER_CAPABILITIES = {
    'openai': {
        'chat': True,
        'streaming': True,
        'image_generation': True,  # DALL-E
        'vision': True,             # GPT-4V
        'tts': False,
        'embedding': True
    },
    'anthropic': {
        'chat': True,
        'streaming': True,
        'image_generation': False,
        'vision': True,             # Claude 3.5
        'tts': False,
        'embedding': False
    },
    'xai': {
        'chat': True,
        'streaming': True,
        'image_generation': True,  # Aurora
        'vision': True,             # Grok
        'tts': False,
        'embedding': False
    },
    'mistral': {
        'chat': True,
        'streaming': True,
        'image_generation': False,
        'vision': True,  # Pixtral Large and Pixtral 12B
        'tts': False,
        'embedding': True
    },
    'cohere': {
        'chat': True,
        'streaming': True,
        'image_generation': False,
        'vision': False,
        'tts': False,
        'embedding': True
    },
    'gemini': {
        'chat': True,
        'streaming': True,
        'image_generation': False,
        'vision': True,  # Gemini 2.0 Flash and Pro support vision
        'tts': False,
        'embedding': True
    },
    'perplexity': {
        'chat': True,
        'streaming': True,
        'image_generation': False,
        'vision': True,   # Sonar Pro and Sonar support vision
        'tts': False,
        'embedding': False
    },
    'groq': {
        'chat': True,
        'streaming': True,
        'image_generation': False,
        'vision': False,
        'tts': False,
        'embedding': False
    },
    'huggingface': {
        'chat': True,
        'streaming': True,
        'image_generation': True,  # Stable Diffusion and others
        'vision': True,             # Various vision models
        'tts': False,
        'embedding': True
    },
    'manus': {
        'chat': True,
        'streaming': True,
        'image_generation': False,
        'vision': True,
        'tts': False,
        'embedding': False
    },
    'elevenlabs': {
        'chat': False,
        'streaming': False,
        'image_generation': False,
        'vision': False,
        'tts': True,                # Primary purpose
        'embedding': False
    },
    'claude_code': {
        'chat': True,
        'streaming': True,
        'image_generation': False,
        'vision': True,             # Inherits from AnthropicProvider
        'tts': False,
        'embedding': False
    },
    'ollama': {
        'chat': True,
        'streaming': True,
        'image_generation': False,
        'vision': True,             # Via vision models (llava, bakllava, etc.)
        'tts': False,
        'embedding': True           # Ollama supports embedding models
    },
    'gradient': {
        'chat': True,
        'streaming': True,
        'image_generation': False,
        'vision': False,            # Serverless inference, no vision yet
        'tts': False,
        'embedding': False          # No embedding endpoint currently
    },
    'gradient_v2': {
        'chat': True,
        'streaming': True,
        'image_generation': True,   # Via do-gradient-ai SDK (tier-dependent)
        'vision': False,            # Not supported by Gradient
        'tts': False,
        'embedding': False,
        'knowledge_bases': True,    # RAG with citations
        'agents': True              # Managed AI assistants
    }
}


# Model complexity tiers for cost optimization (Updated January 2026)
COMPLEXITY_TIERS = {
    'openai': {
        'simple': 'gpt-4o-mini',          # Fast, cheap, good for simple tasks
        'medium': 'gpt-4o',               # Balanced quality/cost
        'complex': 'gpt-4o'               # Best general purpose
    },
    'anthropic': {
        'simple': 'claude-3-haiku-20240307',      # Fast, cheap
        'medium': 'claude-3-5-sonnet-20241022',   # Balanced
        'complex': 'claude-3-5-sonnet-20241022'   # Best general purpose
    },
    'xai': {
        'simple': 'grok-3-mini',          # Fast, efficient
        'medium': 'grok-3',               # Full capability
        'complex': 'grok-3'               # Best reasoning
    },
    'groq': {
        'simple': 'llama-3.3-70b-versatile',
        'medium': 'llama-3.3-70b-versatile',
        'complex': 'llama-3.3-70b-versatile'
    },
    'mistral': {
        'simple': 'mistral-small-latest',     # Fast, efficient
        'medium': 'mistral-medium-latest',    # Balanced
        'complex': 'mistral-large-latest'     # Full capability
    },
    'gemini': {
        'simple': 'gemini-2.0-flash',         # Fast, efficient
        'medium': 'gemini-2.0-flash',         # Good balance
        'complex': 'gemini-2.5-pro'           # Full capability
    },
    'cohere': {
        'simple': 'command-r7b-12-2024',      # Small, fast
        'medium': 'command-r-plus-08-2024',   # Balanced
        'complex': 'command-r-plus-08-2024'   # Full capability
    },
    'perplexity': {
        'simple': 'sonar',                    # Fast search-augmented
        'medium': 'sonar-pro',                # Better accuracy
        'complex': 'sonar-reasoning'          # Best for complex analysis
    },
    'huggingface': {
        'simple': 'microsoft/Phi-3-mini-4k-instruct',
        'medium': 'mistralai/Mixtral-8x7B-Instruct-v0.1',
        'complex': 'meta-llama/Llama-3.2-3B-Instruct'
    },
    'manus': {
        'simple': 'manus-1.5',
        'medium': 'manus-1.5',
        'complex': 'manus-1.5'
    },
    'ollama': {
        'simple': 'llama3.2',
        'medium': 'llama3.1',
        'complex': 'llama3.1:70b'
    },
    'gradient': {
        'simple': 'llama3.2-1b-instruct',
        'medium': 'llama3.3-70b-instruct',
        'complex': 'llama3.3-70b-instruct'
    },
    'gradient_v2': {
        'simple': 'llama3.2-1b-instruct',
        'medium': 'llama3.3-70b-instruct',
        'complex': 'llama3.3-70b-instruct'
    }
}


class ProviderFactory:
    """Singleton factory for lazy-loading LLM providers."""

    _instances: Dict[str, any] = {}

    @classmethod
    def get_provider(cls, provider_name: str):
        """
        Get or create a provider instance with lazy loading.

        Args:
            provider_name: Name of the provider ('xai', 'anthropic', 'openai', etc.)

        Returns:
            Provider instance (cached after first creation)

        Raises:
            ValueError: If provider_name is not recognized
        """
        if provider_name not in cls._instances:
            # Lazy import providers to avoid unnecessary dependencies
            provider_classes = cls._get_provider_classes()

            if provider_name not in provider_classes:
                available = list(provider_classes.keys())
                raise ValueError(
                    f"Unknown provider: {provider_name}. "
                    f"Available providers: {', '.join(available)}"
                )

            # Instantiate and cache the provider
            cls._instances[provider_name] = provider_classes[provider_name]()

        return cls._instances[provider_name]

    @classmethod
    def _get_provider_classes(cls) -> Dict[str, type]:
        """
        Get mapping of provider names to classes.
        Imports are done here to keep them lazy.
        """
        from .xai_provider import XAIProvider
        from .anthropic_provider import AnthropicProvider
        from .openai_provider import OpenAIProvider

        # Core providers that are always available
        providers = {
            'xai': XAIProvider,
            'anthropic': AnthropicProvider,
            'openai': OpenAIProvider,
        }

        # Optional providers (gracefully handle if not installed)
        try:
            from .mistral_provider import MistralProvider
            providers['mistral'] = MistralProvider
        except ImportError:
            pass

        try:
            from .cohere_provider import CohereProvider
            providers['cohere'] = CohereProvider
        except ImportError:
            pass

        try:
            from .gemini_provider import GeminiProvider
            providers['gemini'] = GeminiProvider
        except ImportError:
            pass

        try:
            from .perplexity_provider import PerplexityProvider
            providers['perplexity'] = PerplexityProvider
        except ImportError:
            pass

        try:
            from .huggingface_provider import HuggingFaceProvider
            providers['huggingface'] = HuggingFaceProvider
        except ImportError:
            pass

        try:
            from .groq_provider import GroqProvider
            providers['groq'] = GroqProvider
        except ImportError:
            pass

        try:
            from .manus_provider import ManusProvider
            providers['manus'] = ManusProvider
        except ImportError:
            pass

        try:
            from .elevenlabs_provider import ElevenLabsProvider
            providers['elevenlabs'] = ElevenLabsProvider
        except ImportError:
            pass

        try:
            from .claude_code_provider import ClaudeCodeProvider
            providers['claude_code'] = ClaudeCodeProvider
        except ImportError:
            pass

        try:
            from .ollama_provider import OllamaProvider
            providers['ollama'] = OllamaProvider
        except ImportError:
            pass

        try:
            from .gradient_provider import GradientProvider
            providers['gradient'] = GradientProvider
        except ImportError:
            pass

        try:
            from .gradient_provider_v2 import GradientProviderV2
            providers['gradient_v2'] = GradientProviderV2
        except ImportError:
            pass

        return providers

    @classmethod
    def create_provider(cls, provider_name: str, api_key: str, model: Optional[str] = None):
        """
        Create a provider instance with explicit API key.

        Args:
            provider_name: Name of the provider
            api_key: API key for the provider
            model: Optional model name

        Returns:
            Provider instance (not cached)

        Raises:
            ValueError: If provider_name is not recognized
        """
        provider_classes = cls._get_provider_classes()

        if provider_name not in provider_classes:
            available = list(provider_classes.keys())
            raise ValueError(
                f"Unknown provider: {provider_name}. "
                f"Available providers: {', '.join(available)}"
            )

        return provider_classes[provider_name](api_key=api_key, model=model)

    @classmethod
    def get_provider_capabilities(cls, provider_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get capability matrix for providers.

        Args:
            provider_name: Specific provider, or None for all

        Returns:
            Dict with capability flags (chat, streaming, image_generation, vision, tts, embedding)

        Example:
            # Check if OpenAI supports vision
            caps = ProviderFactory.get_provider_capabilities('openai')
            if caps['vision']:
                provider = ProviderFactory.get_provider('openai')
                result = provider.analyze_image(image, prompt)

            # Get all capabilities
            all_caps = ProviderFactory.get_provider_capabilities()
            vision_providers = [p for p, c in all_caps.items() if c['vision']]
        """
        if provider_name:
            return PROVIDER_CAPABILITIES.get(provider_name, {}).copy()
        return {k: v.copy() for k, v in PROVIDER_CAPABILITIES.items()}

    @classmethod
    def find_providers_with_capability(cls, capability: str) -> List[str]:
        """
        Find all providers that support a specific capability.

        Args:
            capability: One of: chat, streaming, image_generation, vision, tts, embedding

        Returns:
            List of provider names supporting the capability

        Example:
            vision_providers = ProviderFactory.find_providers_with_capability('vision')
            # Returns: ['openai', 'anthropic', 'xai', 'huggingface', 'manus', 'claude_code']

            tts_providers = ProviderFactory.find_providers_with_capability('tts')
            # Returns: ['elevenlabs']
        """
        return [
            provider_name
            for provider_name, caps in PROVIDER_CAPABILITIES.items()
            if caps.get(capability, False)
        ]

    @classmethod
    def select_model_by_complexity(
        cls,
        query: str,
        provider: str,
        budget_tier: str = 'balanced'
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Select optimal model based on query complexity.

        Args:
            query: The user query or task
            provider: Provider name
            budget_tier: 'cheap', 'balanced', or 'premium'

        Returns:
            Tuple of (model_name, metadata_dict)

        Example:
            model, meta = ProviderFactory.select_model_by_complexity(
                "What is Python?",
                "openai"
            )
            # Returns: ('gpt-4o-mini', {'complexity': 'simple', 'cost_tier': 'low'})
        """
        # Detect complexity
        complexity = cls._detect_query_complexity(query)

        # Adjust for budget tier
        if budget_tier == 'cheap' and complexity == 'medium':
            complexity = 'simple'
        elif budget_tier == 'premium' and complexity == 'simple':
            complexity = 'medium'

        # Get model from tiers
        if provider not in COMPLEXITY_TIERS:
            raise ValueError(f"No complexity tiers defined for provider: {provider}")

        model = COMPLEXITY_TIERS[provider][complexity]

        metadata = {
            'complexity': complexity,
            'cost_tier': 'low' if complexity == 'simple' else 'medium' if complexity == 'medium' else 'high',
            'budget_tier': budget_tier
        }

        return model, metadata

    @classmethod
    def _detect_query_complexity(cls, query: str) -> str:
        """
        Detect query complexity based on heuristics.

        Args:
            query: The user query

        Returns:
            'simple', 'medium', or 'complex'
        """
        query_lower = query.lower()

        # Simple indicators
        simple_keywords = [
            'what is', 'define', 'basic', 'simple', 'quick',
            'tell me', 'list', 'name', 'who is', 'when'
        ]

        # Complex indicators
        complex_keywords = [
            'optimize', 'architect', 'design', 'comprehensive',
            'research', 'analyze thoroughly', 'detailed analysis',
            'compare and contrast', 'evaluate', 'implement',
            'create system', 'build', 'develop'
        ]

        # Medium indicators
        medium_keywords = [
            'explain', 'compare', 'analyze', 'how does',
            'why', 'describe', 'summarize', 'review'
        ]

        # Check for code snippets
        has_code = '```' in query or 'def ' in query or 'class ' in query

        # Word count
        word_count = len(query.split())

        # Simple query detection
        if any(keyword in query_lower for keyword in simple_keywords) and word_count < 15:
            return 'simple'

        # Complex query detection
        if any(keyword in query_lower for keyword in complex_keywords) or word_count > 50 or has_code:
            return 'complex'

        # Medium query detection
        if any(keyword in query_lower for keyword in medium_keywords) or word_count > 20:
            return 'medium'

        # Default to simple for short queries
        if word_count < 10:
            return 'simple'

        return 'medium'

    @classmethod
    def clear_cache(cls, provider_name: Optional[str] = None):
        """
        Clear cached provider instances.

        Args:
            provider_name: Specific provider to clear, or None to clear all
        """
        if provider_name:
            cls._instances.pop(provider_name, None)
        else:
            cls._instances.clear()

    @classmethod
    def list_providers(cls) -> list:
        """List all available provider names."""
        return list(cls._get_provider_classes().keys())
