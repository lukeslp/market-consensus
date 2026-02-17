"""
Foresight - Stock Prediction Dashboard
Application factory pattern
"""
import sys
from pathlib import Path

# Add shared library to path
if '/home/coolhand/shared' not in sys.path:
    sys.path.append('/home/coolhand/shared')

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
import logging
from logging.handlers import RotatingFileHandler
import atexit

from app.config import Config
from app.database import init_db, close_db
from app.errors import register_error_handlers

# Global worker instance
_worker = None


def create_app(config_class=Config):
    """Application factory"""
    global _worker

    app = Flask(__name__, static_folder='../static')
    app.config.from_object(config_class)

    # Trust proxy headers from Caddy
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Setup logging
    setup_logging(app)

    # Initialize database
    init_db(app)

    # Register error handlers
    register_error_handlers(app)

    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Database teardown
    app.teardown_appcontext(close_db)

    # Initialize and start background worker
    from app.worker import PredictionWorker
    _worker = PredictionWorker(app.config)
    
    if not app.config.get('TESTING'):
        _worker.start()
        app.logger.info('Background prediction worker started')
    else:
        app.logger.info('Background prediction worker disabled for testing')

    # Store worker reference in app for access from routes
    app.worker = _worker

    # Register shutdown handler
    atexit.register(lambda: shutdown_worker(_worker, app.logger))

    app.logger.info(f'Foresight initialized on port {app.config["PORT"]}')

    return app


def shutdown_worker(worker, logger):
    """Shutdown worker gracefully"""
    if worker and worker.is_alive():
        logger.info('Shutting down prediction worker...')
        worker.stop()


def setup_logging(app):
    """Configure application logging"""
    if not app.debug:
        # File handler for production
        log_file = Path(__file__).parent.parent / 'foresight.log'
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10240000, backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info('Foresight startup')


def get_worker():
    """Get global worker instance"""
    return _worker
