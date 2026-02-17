"""
Foresight Configuration
Environment-based configuration classes
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


class Config:
    """Base configuration"""
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')

    # Server
    PORT = int(os.environ.get('PORT', 5062))
    HOST = os.environ.get('HOST', '0.0.0.0')

    # Database (SQLite with WAL mode for concurrent reads)
    DB_PATH = os.environ.get('DB_PATH', str(BASE_DIR / 'foresight.db'))

    # Prediction cycle
    CYCLE_INTERVAL = int(os.environ.get('CYCLE_INTERVAL', 30))  # 30 seconds (dev), set to 600 for production

    # LLM Providers
    PROVIDERS = {
        'discovery': os.environ.get('DISCOVERY_PROVIDER', 'xai'),      # Grok for stock discovery
        'prediction': os.environ.get('PREDICTION_PROVIDER', 'anthropic'), # Claude for technical analysis
        'synthesis': os.environ.get('SYNTHESIS_PROVIDER', 'gemini')    # Gemini for debate/consensus
    }

    # Model overrides (optional, leave empty for provider defaults)
    MODEL_OVERRIDES = {
        'xai': 'grok-2-1212',
        'anthropic': 'claude-3-opus-20240229',
        'gemini': 'gemini-2.0-flash',
        'cohere': 'command-r-plus',
        'mistral': 'mistral-large-latest',
        'perplexity': 'sonar',
        'manus': 'manus-1.5'
    }

    # API Keys (loaded from environment)
    XAI_API_KEY = os.environ.get('XAI_API_KEY')
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

    # SSE streaming
    SSE_RETRY = int(os.environ.get('SSE_RETRY', 3000))  # milliseconds

    # Stock data
    MAX_STOCKS = int(os.environ.get('MAX_STOCKS', 10))  # Max stocks to track per cycle
    LOOKBACK_DAYS = int(os.environ.get('LOOKBACK_DAYS', 30))  # Historical data to fetch


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
