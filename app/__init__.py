"""
Foresight - Stock Prediction Dashboard
Application factory pattern
"""
import sys
import os
from pathlib import Path
import fcntl
import time
import threading

# Add project root to path so bundled llm_providers is importable
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

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
_worker_lock_fd = None


def _try_acquire_worker_lock(lock_path: str = '/tmp/foresight.worker.lock') -> bool:
    """
    Acquire a non-blocking cross-process lock so only one Gunicorn worker
    starts the background prediction thread.
    """
    global _worker_lock_fd
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _worker_lock_fd = fd
        return True
    except BlockingIOError:
        os.close(fd)
        return False


def _retry_start_worker(worker, logger, retry_seconds: int = 5):
    """
    Retry lock acquisition in the background so a fresh process can
    take over scheduling after the previous worker exits.
    """
    def _attempt():
        while True:
            if worker.is_alive():
                return
            if _try_acquire_worker_lock():
                worker.scheduler_lock_acquired = True
                worker.start()
                logger.info('Background prediction worker started after lock retry')
                return
            time.sleep(max(1, retry_seconds))

    retry_thread = threading.Thread(target=_attempt, daemon=True, name='WorkerLockRetry')
    retry_thread.start()


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
        lock_acquired = _try_acquire_worker_lock()
        _worker.scheduler_lock_acquired = lock_acquired
        if lock_acquired:
            _worker.start()
            app.logger.info('Background prediction worker started')
        else:
            app.logger.info('Background worker lock held by another process; skipping worker start')
            _retry_start_worker(_worker, app.logger)
    else:
        _worker.scheduler_lock_acquired = False
        app.logger.info('Background prediction worker disabled for testing')

    # Store worker reference in app for access from routes
    app.worker = _worker

    # Register shutdown handler
    atexit.register(lambda: shutdown_worker(_worker, app.logger))

    app.logger.info(f'Foresight initialized on port {app.config["PORT"]}')

    return app


def shutdown_worker(worker, logger):
    """Shutdown worker gracefully"""
    global _worker_lock_fd
    if worker and worker.is_alive():
        logger.info('Shutting down prediction worker...')
        worker.stop()
    if _worker_lock_fd is not None:
        try:
            fcntl.flock(_worker_lock_fd, fcntl.LOCK_UN)
            os.close(_worker_lock_fd)
        except Exception:
            pass
        _worker_lock_fd = None


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
