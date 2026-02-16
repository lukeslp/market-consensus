"""
Error handlers for Foresight
Consistent JSON error responses
"""
from flask import jsonify, current_app
from werkzeug.exceptions import HTTPException
import traceback


def register_error_handlers(app):
    """Register all error handlers with the Flask app"""

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            'error': 'Bad Request',
            'message': str(error.description) if hasattr(error, 'description') else 'Invalid request'
        }), 400

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'error': 'Not Found',
            'message': 'The requested resource does not exist'
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({
            'error': 'Method Not Allowed',
            'message': f'The method is not allowed for the requested URL'
        }), 405

    @app.errorhandler(500)
    def internal_error(error):
        current_app.logger.error(f'Internal error: {str(error)}')
        current_app.logger.error(traceback.format_exc())

        # Rollback database if it exists
        from app.database import get_db
        try:
            db = get_db()
            db.rollback()
        except:
            pass

        return jsonify({
            'error': 'Internal Server Error',
            'message': 'An unexpected error occurred'
        }), 500

    @app.errorhandler(503)
    def service_unavailable(error):
        return jsonify({
            'error': 'Service Unavailable',
            'message': 'The service is temporarily unavailable'
        }), 503

    @app.errorhandler(Exception)
    def handle_exception(error):
        """Handle uncaught exceptions"""
        # Pass through HTTP errors
        if isinstance(error, HTTPException):
            return error

        # Log the error
        current_app.logger.error(f'Unhandled exception: {str(error)}')
        current_app.logger.error(traceback.format_exc())

        return jsonify({
            'error': 'Internal Server Error',
            'message': 'An unexpected error occurred'
        }), 500
