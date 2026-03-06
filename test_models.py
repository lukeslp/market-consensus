import sys
import os
import logging

# Add project root to path so bundled llm_providers is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_providers import ProviderFactory

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

providers = ['xai', 'anthropic', 'gemini', 'cohere', 'mistral', 'perplexity']

print("="*60)
print("FETCHING LIVE MODELS FROM PROVIDERS")
print("="*60)

for p_name in providers:
    print(f"\n>>> Provider: {p_name.upper()}")
    try:
        provider = ProviderFactory.get_provider(p_name)
        models = provider.list_models()
        
        # Some providers might return list of strings, others list of dicts
        model_ids = []
        if models:
            if isinstance(models[0], dict):
                model_ids = [m.get('id', str(m)) for m in models]
            else:
                model_ids = models
            
        print(f"Count: {len(model_ids)}")
        print(f"Models: {model_ids[:15]}") # Show first 15
        
        # Try to guess "latest" or "best" based on common patterns
        if p_name == 'xai':
            latest = [m for m in model_ids if 'grok-3' in m or 'grok-4' in m]
            print(f"Suggested latest: {latest}")
        elif p_name == 'anthropic':
            latest = [m for m in model_ids if 'claude-3-7' in m or 'claude-3-5' in m]
            print(f"Suggested latest: {latest}")
            
    except Exception as e:
        print(f"ERROR for {p_name}: {str(e)}")

print("\n" + "="*60)
