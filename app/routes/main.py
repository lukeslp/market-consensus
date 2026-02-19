"""
Main routes blueprint
Serves the dashboard UI
"""
from flask import Blueprint, send_from_directory, current_app
from datetime import datetime

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Serve the main dashboard"""
    return send_from_directory('../static', 'index.html')


@main_bp.route('/health')
def health():
    """Health check endpoint"""
    from app.database import get_db

    try:
        # Check database connectivity using ForesightDB methods
        db = get_db()
        # Try to get dashboard summary to verify DB is working
        db.get_dashboard_summary()

        # Check worker status
        worker = current_app.worker
        if hasattr(worker, 'get_cluster_status'):
            worker_info = worker.get_cluster_status()
            worker_status = 'running' if worker_info.get('running') and worker_info.get('alive') else 'stopped'
        else:
            worker_status = 'running' if worker.is_alive() else 'stopped'

        return {
            'status': 'healthy',
            'service': 'foresight',
            'database': 'connected',
            'worker': worker_status,
            'timestamp': datetime.now().isoformat()
        }, 200

    except Exception as e:
        current_app.logger.error(f'Health check failed: {str(e)}')
        return {
            'status': 'unhealthy',
            'service': 'foresight',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, 503
