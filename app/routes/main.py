"""
Main routes blueprint
Serves the dashboard UI
"""
from flask import Blueprint, send_from_directory, current_app

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

        return {
            'status': 'healthy',
            'service': 'foresight',
            'database': 'connected'
        }, 200

    except Exception as e:
        current_app.logger.error(f'Health check failed: {str(e)}')
        return {
            'status': 'unhealthy',
            'service': 'foresight',
            'error': str(e)
        }, 503
