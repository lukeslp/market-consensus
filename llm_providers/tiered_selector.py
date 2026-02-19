"""
Tiered Provider Selector

Utility for selecting optimal models based on task complexity and budget.
Integrates with ProviderFactory's COMPLEXITY_TIERS for cost-optimized
model selection in orchestration workflows.

Author: Luke Steuber

Usage:
    from llm_providers.tiered_selector import TieredProviderSelector

    # Get model for specific tier
    selector = TieredProviderSelector('gradient_v2')
    model = selector.get_model_for_tier('simple')  # llama3.2-1b-instruct

    # Auto-select based on task analysis
    model, metadata = selector.select_for_task(
        "What is Python?",
        budget='cheap'
    )

    # Get models for orchestrator tiers
    models = selector.get_orchestrator_models()
    # Returns: {'belter': 'simple_model', 'drummer': 'medium_model', 'camina': 'complex_model'}
"""

from typing import Dict, Optional, Tuple, Any, List

from .factory import COMPLEXITY_TIERS, PROVIDER_CAPABILITIES, ProviderFactory


class TieredProviderSelector:
    """
    Selects optimal models based on task complexity and budget constraints.

    Designed for use with orchestration workflows where different agent
    tiers can use different model complexities for cost optimization.

    Orchestrator Tier Mapping:
    - Belter (workers) → 'simple' tier (fast, cheap)
    - Drummer (mid-synthesis) → 'medium' tier (balanced)
    - Camina (executive) → 'complex' tier (highest quality)

    Example:
        >>> selector = TieredProviderSelector('gradient_v2')
        >>>
        >>> # For Dream Cascade orchestrator
        >>> models = selector.get_orchestrator_models()
        >>> config = DreamCascadeConfig(
        ...     worker_model=models['belter'],
        ...     synthesis_model=models['camina'],
        ...     primary_model=models['drummer']
        ... )
    """

    # Map orchestrator tiers to complexity tiers
    ORCHESTRATOR_TIER_MAP = {
        'belter': 'simple',
        'worker': 'simple',
        'drummer': 'medium',
        'synthesizer': 'medium',
        'camina': 'complex',
        'executive': 'complex'
    }

    # Budget tier adjustments
    BUDGET_ADJUSTMENTS = {
        'cheap': {'simple': 'simple', 'medium': 'simple', 'complex': 'medium'},
        'balanced': {'simple': 'simple', 'medium': 'medium', 'complex': 'complex'},
        'premium': {'simple': 'medium', 'medium': 'complex', 'complex': 'complex'}
    }

    def __init__(self, provider_name: str):
        """
        Initialize tiered selector for a provider.

        Args:
            provider_name: Name of the LLM provider (e.g., 'gradient_v2', 'xai', 'openai')

        Raises:
            ValueError: If provider has no complexity tiers defined
        """
        self.provider_name = provider_name

        if provider_name not in COMPLEXITY_TIERS:
            available = list(COMPLEXITY_TIERS.keys())
            raise ValueError(
                f"No complexity tiers defined for provider: {provider_name}. "
                f"Available providers with tiers: {', '.join(available)}"
            )

        self.tiers = COMPLEXITY_TIERS[provider_name]
        self.capabilities = PROVIDER_CAPABILITIES.get(provider_name, {})

    def get_model_for_tier(self, tier: str) -> str:
        """
        Get model name for a specific complexity tier.

        Args:
            tier: Complexity tier ('simple', 'medium', 'complex')

        Returns:
            Model name string

        Raises:
            ValueError: If tier is invalid
        """
        if tier not in self.tiers:
            raise ValueError(
                f"Invalid tier: {tier}. Valid tiers: {list(self.tiers.keys())}"
            )
        return self.tiers[tier]

    def get_orchestrator_models(
        self,
        budget: str = 'balanced'
    ) -> Dict[str, str]:
        """
        Get model assignments for orchestrator agent tiers.

        Maps orchestrator agent types (belter, drummer, camina) to
        appropriate models based on complexity and budget.

        Args:
            budget: Budget tier ('cheap', 'balanced', 'premium')

        Returns:
            Dict mapping orchestrator tier to model name:
            {
                'belter': 'simple_model',
                'drummer': 'medium_model',
                'camina': 'complex_model'
            }
        """
        adjustments = self.BUDGET_ADJUSTMENTS.get(budget, self.BUDGET_ADJUSTMENTS['balanced'])

        return {
            'belter': self.tiers[adjustments['simple']],
            'drummer': self.tiers[adjustments['medium']],
            'camina': self.tiers[adjustments['complex']],
            # Aliases
            'worker': self.tiers[adjustments['simple']],
            'synthesizer': self.tiers[adjustments['medium']],
            'executive': self.tiers[adjustments['complex']]
        }

    def select_for_task(
        self,
        task: str,
        budget: str = 'balanced'
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Auto-select model based on task analysis.

        Analyzes task complexity using heuristics and selects appropriate
        model, adjusted by budget preference.

        Args:
            task: Task description text
            budget: Budget tier ('cheap', 'balanced', 'premium')

        Returns:
            Tuple of (model_name, metadata_dict)

        Example:
            >>> model, meta = selector.select_for_task("What is Python?", budget='cheap')
            >>> print(model)  # 'llama3.2-1b-instruct'
            >>> print(meta)   # {'complexity': 'simple', 'budget': 'cheap', ...}
        """
        # Use ProviderFactory's complexity detection
        model, metadata = ProviderFactory.select_model_by_complexity(
            query=task,
            provider=self.provider_name,
            budget_tier=budget
        )

        return model, metadata

    def get_model_for_orchestrator_tier(
        self,
        orchestrator_tier: str,
        budget: str = 'balanced'
    ) -> str:
        """
        Get model for a specific orchestrator tier.

        Args:
            orchestrator_tier: Orchestrator tier name
                ('belter', 'worker', 'drummer', 'synthesizer', 'camina', 'executive')
            budget: Budget tier ('cheap', 'balanced', 'premium')

        Returns:
            Model name string
        """
        tier_lower = orchestrator_tier.lower()

        if tier_lower not in self.ORCHESTRATOR_TIER_MAP:
            raise ValueError(
                f"Unknown orchestrator tier: {orchestrator_tier}. "
                f"Valid tiers: {list(self.ORCHESTRATOR_TIER_MAP.keys())}"
            )

        complexity = self.ORCHESTRATOR_TIER_MAP[tier_lower]
        adjustments = self.BUDGET_ADJUSTMENTS.get(budget, self.BUDGET_ADJUSTMENTS['balanced'])
        adjusted_complexity = adjustments[complexity]

        return self.tiers[adjusted_complexity]

    def get_all_tiers(self) -> Dict[str, str]:
        """
        Get all available complexity tiers and their models.

        Returns:
            Dict mapping tier name to model name
        """
        return dict(self.tiers)

    def estimate_cost_factor(self, tier: str) -> float:
        """
        Estimate relative cost factor for a tier.

        Returns a multiplier representing relative cost:
        - simple: 1.0 (baseline)
        - medium: 3.0-5.0 (mid-range)
        - complex: 10.0-20.0 (premium)

        These are rough estimates - actual costs vary by provider.

        Args:
            tier: Complexity tier

        Returns:
            Cost factor multiplier
        """
        cost_factors = {
            'simple': 1.0,
            'medium': 4.0,
            'complex': 15.0
        }
        return cost_factors.get(tier, 4.0)

    def estimate_workflow_cost(
        self,
        belter_count: int = 8,
        drummer_count: int = 2,
        camina_count: int = 1,
        budget: str = 'balanced'
    ) -> Dict[str, Any]:
        """
        Estimate relative cost for an orchestrator workflow.

        Provides rough cost factors for planning purposes.
        Actual costs depend on token usage and provider pricing.

        Args:
            belter_count: Number of Belter (worker) agents
            drummer_count: Number of Drummer (synthesizer) agents
            camina_count: Number of Camina (executive) agents
            budget: Budget tier

        Returns:
            Dict with cost estimates and model assignments
        """
        models = self.get_orchestrator_models(budget)
        adjustments = self.BUDGET_ADJUSTMENTS.get(budget, self.BUDGET_ADJUSTMENTS['balanced'])

        belter_cost = belter_count * self.estimate_cost_factor(adjustments['simple'])
        drummer_cost = drummer_count * self.estimate_cost_factor(adjustments['medium'])
        camina_cost = camina_count * self.estimate_cost_factor(adjustments['complex'])

        total_factor = belter_cost + drummer_cost + camina_cost

        return {
            'models': {
                'belter': models['belter'],
                'drummer': models['drummer'],
                'camina': models['camina']
            },
            'cost_factors': {
                'belter_total': belter_cost,
                'drummer_total': drummer_cost,
                'camina_total': camina_cost,
                'total': total_factor
            },
            'counts': {
                'belter': belter_count,
                'drummer': drummer_count,
                'camina': camina_count
            },
            'budget': budget
        }


def get_tiered_selector(provider_name: str = 'gradient_v2') -> TieredProviderSelector:
    """
    Convenience function to get a tiered selector instance.

    Args:
        provider_name: Provider name (default: gradient_v2)

    Returns:
        TieredProviderSelector instance
    """
    return TieredProviderSelector(provider_name)


def get_optimal_models_for_workflow(
    provider_name: str = 'gradient_v2',
    budget: str = 'balanced'
) -> Dict[str, str]:
    """
    Get optimal model assignments for an orchestrator workflow.

    Convenience function for quick model selection.

    Args:
        provider_name: Provider name
        budget: Budget tier ('cheap', 'balanced', 'premium')

    Returns:
        Dict with model assignments for orchestrator tiers

    Example:
        >>> models = get_optimal_models_for_workflow('gradient_v2', 'cheap')
        >>> # Returns: {'belter': 'llama3.2-1b-instruct', 'drummer': 'llama3.2-1b-instruct', ...}
    """
    selector = TieredProviderSelector(provider_name)
    return selector.get_orchestrator_models(budget)


def list_providers_with_tiers() -> List[str]:
    """
    List all providers that have complexity tiers defined.

    Returns:
        List of provider names
    """
    return list(COMPLEXITY_TIERS.keys())
