"""
Foresight Configuration
Environment-based configuration classes
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# ── Top 50 Crypto Tickers (yfinance format) ──────────────────────────────────
TOP_50_CRYPTO = [
    'BTC-USD',   # Bitcoin
    'ETH-USD',   # Ethereum
    'XRP-USD',   # XRP
    'SOL-USD',   # Solana
    'BNB-USD',   # Binance Coin
    'ADA-USD',   # Cardano
    'DOGE-USD',  # Dogecoin
    'TRX-USD',   # TRON
    'AVAX-USD',  # Avalanche
    'LINK-USD',  # Chainlink
    'DOT-USD',   # Polkadot
    'SHIB-USD',  # Shiba Inu
    'TON11419-USD',  # Toncoin
    'XLM-USD',   # Stellar
    'SUI20947-USD',  # Sui
    'HBAR-USD',  # Hedera
    'BCH-USD',   # Bitcoin Cash
    'LTC-USD',   # Litecoin
    'ATOM-USD',  # Cosmos
    'UNI7083-USD',  # Uniswap
    'NEAR-USD',  # NEAR Protocol
    'APT21794-USD',  # Aptos
    'MATIC-USD', # Polygon
    'FIL-USD',   # Filecoin
    'ARB11841-USD',  # Arbitrum
    'OP-USD',    # Optimism
    'ALGO-USD',  # Algorand
    'FTM-USD',   # Fantom
    'AAVE-USD',  # Aave
    'MKR-USD',   # Maker
    'GRT6719-USD',  # The Graph
    'RENDER-USD',  # Render
    'INJ-USD',   # Injective
    'IMX10603-USD',  # Immutable
    'STX4847-USD',  # Stacks
    'THETA-USD', # Theta Network
    'SAND-USD',  # The Sandbox
    'MANA-USD',  # Decentraland
    'AXS-USD',   # Axie Infinity
    'FLOW-USD',  # Flow
    'EOS-USD',   # EOS
    'XTZ-USD',   # Tezos
    'CRV-USD',   # Curve DAO
    'COMP-USD',  # Compound
    'KAVA-USD',  # Kava
    'ZEC-USD',   # Zcash
    'DASH-USD',  # Dash
    'ENJ-USD',   # Enjin Coin
    'CHZ-USD',   # Chiliz
    'ONE-USD',   # Harmony
]

# ── Top 50 Equity Tickers ────────────────────────────────────────────────────
TOP_50_EQUITIES = [
    'AAPL',   # Apple
    'MSFT',   # Microsoft
    'NVDA',   # NVIDIA
    'AMZN',   # Amazon
    'GOOGL',  # Alphabet (A)
    'META',   # Meta Platforms
    'TSLA',   # Tesla
    'BRK-B',  # Berkshire Hathaway (B)
    'AVGO',   # Broadcom
    'JPM',    # JPMorgan Chase
    'LLY',    # Eli Lilly
    'V',      # Visa
    'UNH',    # UnitedHealth
    'MA',     # Mastercard
    'XOM',    # Exxon Mobil
    'COST',   # Costco
    'HD',     # Home Depot
    'PG',     # Procter & Gamble
    'JNJ',    # Johnson & Johnson
    'ABBV',   # AbbVie
    'WMT',    # Walmart
    'NFLX',   # Netflix
    'CRM',    # Salesforce
    'BAC',    # Bank of America
    'ORCL',   # Oracle
    'CVX',    # Chevron
    'MRK',    # Merck
    'KO',     # Coca-Cola
    'AMD',    # AMD
    'PEP',    # PepsiCo
    'TMO',    # Thermo Fisher
    'LIN',    # Linde
    'CSCO',   # Cisco
    'ACN',    # Accenture
    'ADBE',   # Adobe
    'MCD',    # McDonald's
    'ABT',    # Abbott Labs
    'WFC',    # Wells Fargo
    'DHR',    # Danaher
    'TXN',    # Texas Instruments
    'PM',     # Philip Morris
    'NEE',    # NextEra Energy
    'INTC',   # Intel
    'DIS',    # Disney
    'CMCSA',  # Comcast
    'VZ',     # Verizon
    'QCOM',   # Qualcomm
    'AMGN',   # Amgen
    'INTU',   # Intuit
    'AMAT',   # Applied Materials
]


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
    USE_NYSE_CALENDAR = os.environ.get('USE_NYSE_CALENDAR', 'true').lower() not in ('0', 'false', 'no')
    MARKET_OPEN_HOUR = int(os.environ.get('MARKET_OPEN_HOUR', 9))
    MARKET_OPEN_MINUTE = int(os.environ.get('MARKET_OPEN_MINUTE', 30))
    MARKET_CLOSE_HOUR = int(os.environ.get('MARKET_CLOSE_HOUR', 16))
    MARKET_CLOSE_MINUTE = int(os.environ.get('MARKET_CLOSE_MINUTE', 0))
    NYSE_EARLY_CLOSE_HOUR = int(os.environ.get('NYSE_EARLY_CLOSE_HOUR', 13))
    NYSE_EARLY_CLOSE_MINUTE = int(os.environ.get('NYSE_EARLY_CLOSE_MINUTE', 0))
    MARKET_OPEN_INTERVAL_SECONDS = int(
        os.environ.get('MARKET_OPEN_INTERVAL_SECONDS', os.environ.get('CYCLE_INTERVAL', 1800))
    )  # default every 30 minutes during market hours
    OVERNIGHT_CHECK_TIMES = os.environ.get('OVERNIGHT_CHECK_TIMES', '20:00,06:00')
    OVERNIGHT_LOOKAHEAD_HOURS = int(os.environ.get('OVERNIGHT_LOOKAHEAD_HOURS', 18))
    SCHEDULE_POLL_SECONDS = int(os.environ.get('SCHEDULE_POLL_SECONDS', 20))
    WORKER_HEARTBEAT_PATH = os.environ.get('WORKER_HEARTBEAT_PATH', '/tmp/foresight.worker.heartbeat')
    WORKER_HEARTBEAT_MAX_AGE_SECONDS = int(os.environ.get('WORKER_HEARTBEAT_MAX_AGE_SECONDS', 120))
    PROVIDER_HEALTH_COOLDOWN_SECONDS = int(os.environ.get('PROVIDER_HEALTH_COOLDOWN_SECONDS', 3600))
    OVERNIGHT_LIGHT_MODE = os.environ.get('OVERNIGHT_LIGHT_MODE', 'true').lower() not in ('0', 'false', 'no')
    OVERNIGHT_FULL_DEBATE_EVERY = int(os.environ.get('OVERNIGHT_FULL_DEBATE_EVERY', 3))
    OVERNIGHT_LIGHT_PROVIDER_ORDER = os.environ.get(
        'OVERNIGHT_LIGHT_PROVIDER_ORDER',
        'anthropic,openai,gemini'  # Premium tier for light overnight runs
    )

    # LLM Provider Council — democracy, no fixed roles.
    # All providers participate in every phase (discovery, analysis, synthesis).
    # Order determines who speaks first in the debate round.
    PROVIDER_ORDER = [p.strip() for p in os.environ.get(
        'PROVIDER_ORDER',
        'anthropic,openai,gemini,xai,perplexity,mistral,huggingface,cohere'
    ).split(',') if p.strip()]

    # Per-provider baseline vote weights. Override with PROVIDER_WEIGHT_<NAME>=<float>.
    # Premium tier (claude/chatgpt/gemini) carry 1.5×; xai mid at 1.1×; rest lower.
    PROVIDER_WEIGHTS = {
        p: float(os.environ.get(f'PROVIDER_WEIGHT_{p.upper()}', default))
        for p, default in {
            'anthropic':   '1.5',
            'openai':      '1.5',
            'gemini':      '1.5',
            'xai':         '1.1',
            'perplexity':  '0.9',
            'mistral':     '0.8',
            'huggingface': '0.85',
            'cohere':      '0.6',
        }.items()
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
            'huggingface': os.environ.get('MODEL_OVERRIDE_HUGGINGFACE', 'meta-llama/Llama-3.3-70B-Instruct'),
        }.items() if model
    }

    # Legacy role-based provider mapping (backwards-compatible with prediction_service.py)
    # In the new democracy model, all providers participate in all phases.
    # This mapping provides defaults for code that still references config['PROVIDERS'].
    PROVIDERS = {
        'discovery': os.environ.get('PROVIDER_DISCOVERY', 'xai'),
        'prediction': os.environ.get('PROVIDER_PREDICTION', 'anthropic'),
        'synthesis': os.environ.get('PROVIDER_SYNTHESIS', 'anthropic'),
    }

    # Swarm-style democracy settings
    SWARM_SUBAGENTS_PER_PROVIDER = int(os.environ.get('SWARM_SUBAGENTS_PER_PROVIDER', 2))

    # API Keys (loaded from environment)
    XAI_API_KEY = os.environ.get('XAI_API_KEY')
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

    # SSE streaming
    SSE_RETRY = int(os.environ.get('SSE_RETRY', 3000))  # milliseconds

    # ── Watchlists ────────────────────────────────────────────────────────────
    # Hardcoded top-50 lists. Discovery debate is skipped; these are used directly.
    # Override with comma-separated env vars to customise.
    EQUITY_WATCHLIST = [s.strip() for s in os.environ.get(
        'EQUITY_WATCHLIST', ','.join(TOP_50_EQUITIES)
    ).split(',') if s.strip()]

    CRYPTO_WATCHLIST = [s.strip() for s in os.environ.get(
        'CRYPTO_WATCHLIST', ','.join(TOP_50_CRYPTO)
    ).split(',') if s.strip()]

    # Stock data
    MAX_STOCKS = int(os.environ.get('MAX_STOCKS', 50))  # Max equities per cycle
    LOOKBACK_DAYS = int(os.environ.get('LOOKBACK_DAYS', 30))  # Historical data to fetch
    INCLUDE_CRYPTO = os.environ.get('INCLUDE_CRYPTO', 'true').lower() not in ('0', 'false', 'no')
    MAX_CRYPTO_SYMBOLS = int(os.environ.get('MAX_CRYPTO_SYMBOLS', 50))
    CRYPTO_SYMBOLS = os.environ.get('CRYPTO_SYMBOLS', ','.join(TOP_50_CRYPTO))

    # Market direction prediction — aggregate UP/DOWN call for each market
    ENABLE_MARKET_PREDICTION = os.environ.get('ENABLE_MARKET_PREDICTION', 'true').lower() not in ('0', 'false', 'no')


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
