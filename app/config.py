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

    # Legacy cycle interval (kept for backwards compatibility with existing tooling)
    CYCLE_INTERVAL = int(os.environ.get('CYCLE_INTERVAL', 1800))

    # Market-aware scheduling
    MARKET_TIMEZONE = os.environ.get('MARKET_TIMEZONE', 'America/New_York')
    MARKET_OPEN_HOUR = int(os.environ.get('MARKET_OPEN_HOUR', 9))
    MARKET_OPEN_MINUTE = int(os.environ.get('MARKET_OPEN_MINUTE', 30))
    MARKET_CLOSE_HOUR = int(os.environ.get('MARKET_CLOSE_HOUR', 16))
    MARKET_CLOSE_MINUTE = int(os.environ.get('MARKET_CLOSE_MINUTE', 0))
    MARKET_OPEN_INTERVAL_SECONDS = int(
        os.environ.get('MARKET_OPEN_INTERVAL_SECONDS', os.environ.get('CYCLE_INTERVAL', 1800))
    )  # default every 30 minutes during market hours
    OVERNIGHT_CHECK_TIMES = os.environ.get('OVERNIGHT_CHECK_TIMES', '20:00,06:00')
    OVERNIGHT_LOOKAHEAD_HOURS = int(os.environ.get('OVERNIGHT_LOOKAHEAD_HOURS', 18))
    SCHEDULE_POLL_SECONDS = int(os.environ.get('SCHEDULE_POLL_SECONDS', 20))

    # LLM Providers
    PROVIDERS = {
        'discovery': os.environ.get('DISCOVERY_PROVIDER', 'mistral'),      # Mistral for stock discovery
        'prediction': os.environ.get('PREDICTION_PROVIDER', 'anthropic'), # Claude for technical analysis
        'synthesis': os.environ.get('SYNTHESIS_PROVIDER', 'gemini')    # Gemini for debate/consensus
    }

    # Model overrides (optional). By default we use provider defaults because model IDs change often.
    # Set env vars like MODEL_OVERRIDE_ANTHROPIC, MODEL_OVERRIDE_XAI, etc. to pin specific models.
    MODEL_OVERRIDES = {
        provider: model for provider, model in {
            'xai': os.environ.get('MODEL_OVERRIDE_XAI'),
            # Anthropic Sonnet 3.5 is deprecated; default to Sonnet 4 unless explicitly overridden.
            'anthropic': os.environ.get('MODEL_OVERRIDE_ANTHROPIC', 'claude-sonnet-4-20250514'),
            'gemini': os.environ.get('MODEL_OVERRIDE_GEMINI'),
            'cohere': os.environ.get('MODEL_OVERRIDE_COHERE'),
            'mistral': os.environ.get('MODEL_OVERRIDE_MISTRAL'),
            'perplexity': os.environ.get('MODEL_OVERRIDE_PERPLEXITY'),
            'openai': os.environ.get('MODEL_OVERRIDE_OPENAI'),
            'manus': os.environ.get('MODEL_OVERRIDE_MANUS'),
        }.items() if model
    }

    # Swarm-style democracy settings
    SWARM_SUBAGENTS_PER_PROVIDER = int(os.environ.get('SWARM_SUBAGENTS_PER_PROVIDER', 2))

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
