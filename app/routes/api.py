"""
API routes blueprint
REST endpoints and SSE streaming for predictions
"""
from flask import Blueprint, jsonify, Response, current_app, request
from app.database import get_db
import json
import time
from datetime import datetime

api_bp = Blueprint('api', __name__)


@api_bp.route('/current')
def current():
    """Get current prediction cycle data"""
    db = get_db()

    # Get current active cycle
    cycle = db.get_current_cycle()

    if not cycle:
        return jsonify({
            'status': 'no_cycles',
            'message': 'No prediction cycles yet'
        }), 404

    # Get predictions for this cycle
    predictions = db.get_predictions_for_cycle(cycle['id'])

    return jsonify({
        'cycle': cycle,
        'predictions': predictions,
        'stocks_discovered': cycle.get('stocks_discovered', 0),
        'predictions_made': cycle.get('predictions_made', 0)
    })


@api_bp.route('/stats')
def stats():
    """Get accuracy statistics"""
    db = get_db()

    # Get provider leaderboard
    leaderboard = db.get_provider_leaderboard()

    # Get recent cycles
    recent_cycles = db.get_recent_cycles(limit=10)
    completed_cycles = [c for c in recent_cycles if c['status'] == 'completed']

    # Get overall stats from dashboard summary
    summary = db.get_dashboard_summary()

    return jsonify({
        'total_predictions': sum(p['total_predictions'] for p in leaderboard) if leaderboard else 0,
        'total_cycles': len(recent_cycles),
        'completed_cycles': len(completed_cycles),
        'overall_accuracy': summary.get('overall_accuracy', 0.0),
        'by_provider': leaderboard
    })


@api_bp.route('/history')
def history():
    """Get historical cycles with pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)  # Max 100 per page

    db = get_db()

    # Get all recent cycles (get_recent_cycles doesn't support pagination yet)
    # TODO: Add pagination support to ForesightDB.get_recent_cycles()
    all_cycles = db.get_recent_cycles(limit=1000)

    # Manual pagination
    start = (page - 1) * per_page
    end = start + per_page
    cycles = all_cycles[start:end]

    return jsonify({
        'cycles': cycles,
        'page': page,
        'per_page': per_page,
        'total': len(all_cycles),
        'pages': (len(all_cycles) + per_page - 1) // per_page
    })


@api_bp.route('/stock/<symbol>')
def stock_detail(symbol):
    """Get detailed data for a specific stock"""
    db = get_db()

    # Get stock by ticker
    stock = db.get_stock(symbol.upper())

    if not stock:
        return jsonify({
            'error': 'Stock not found',
            'symbol': symbol
        }), 404

    # Get predictions for this stock
    predictions = db.get_predictions_for_stock(stock['id'], limit=100)

    # Get price history
    price_history = db.get_price_history(stock['id'], limit=100)

    return jsonify({
        'symbol': symbol.upper(),
        'stock': stock,
        'predictions': predictions,
        'price_history': price_history,
        'times_predicted': stock.get('times_predicted', 0),
        'avg_accuracy': stock.get('avg_accuracy')
    })


@api_bp.route('/health/providers')
def health_providers():
    """Check health of LLM providers"""
    from app.services.prediction_service import PredictionService

    service = PredictionService(current_app.config)

    providers_status = {}
    for role, provider_name in current_app.config['PROVIDERS'].items():
        if role in service.providers:
            provider = service.providers[role]
            providers_status[role] = {
                'status': 'configured',
                'provider': provider_name,
                'type': type(provider).__name__
            }
        else:
            providers_status[role] = {
                'status': 'error',
                'provider': provider_name,
                'error': 'Failed to initialize'
            }

    all_healthy = all(p.get('status') == 'configured' for p in providers_status.values())

    return jsonify({
        'healthy': all_healthy,
        'providers': providers_status
    })


@api_bp.route('/stream')
def stream():
    """SSE endpoint for real-time prediction updates"""
    # Import ForesightDB to create instance directly (avoid Flask g context in generator)
    from db import ForesightDB
    
    # Capture config values before generator to avoid context issues
    db_path = current_app.config['DB_PATH']
    sse_retry = current_app.config.get('SSE_RETRY', 3000)

    def generate():
        """Generate SSE events from database event queue"""
        # Create direct database instance (not using Flask g)
        db = ForesightDB(db_path)

        # Set SSE retry interval
        yield f"retry: {sse_retry}\n\n"

        # Send initial connection event
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.now().isoformat()})}\n\n"

        # Stream events from database
        last_heartbeat = time.time()
        heartbeat_interval = 30  # seconds

        while True:
            current_time = time.time()

            try:
                # Get unprocessed events from database
                events = db.get_unprocessed_events(limit=10)

                if events:
                    # Collect event IDs to mark as processed
                    event_ids = []

                    for event in events:
                        event_ids.append(event['id'])

                        # Format and yield the event
                        event_data = {
                            'id': event['id'],
                            'type': event['event_type'],
                            'data': json.loads(event['data']) if event['data'] else {},
                            'timestamp': event['timestamp']
                        }

                        yield f"data: {json.dumps(event_data)}\n\n"

                    # Mark all events as processed
                    db.mark_events_processed(event_ids)

                # Send heartbeat if needed
                if current_time - last_heartbeat >= heartbeat_interval:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now().isoformat()})}\n\n"
                    last_heartbeat = current_time

                # Sleep briefly before checking for more events
                time.sleep(1)

            except GeneratorExit:
                # Client disconnected
                current_app.logger.info('SSE client disconnected')
                break

            except Exception as e:
                current_app.logger.error(f'SSE stream error: {e}')
                # Send error event
                error_data = {
                    'type': 'error',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                break

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # Disable nginx buffering
            'Connection': 'keep-alive'
        }
    )


@api_bp.route('/worker/status')
def worker_status():
    """Get background worker status"""
    worker = current_app.worker

    return jsonify({
        'worker': worker.get_status(),
        'config': {
            'cycle_interval': current_app.config['CYCLE_INTERVAL'],
            'max_stocks': current_app.config['MAX_STOCKS'],
            'lookback_days': current_app.config['LOOKBACK_DAYS']
        }
    })


@api_bp.route('/cycle/start', methods=['POST'])
def start_cycle():
    """Manually trigger a new prediction cycle"""
    import threading

    db = get_db()

    # Check if there's already an active cycle
    current_cycle = db.get_current_cycle()

    if current_cycle:
        return jsonify({
            'error': 'Cycle already running',
            'cycle_id': current_cycle['id']
        }), 409

    # Check if worker is running
    worker = current_app.worker
    if not worker.is_alive() and not current_app.config.get('TESTING'):
        return jsonify({
            'error': 'Background worker is not running',
            'message': 'Restart the application to start the worker'
        }), 503

    # Create new cycle
    cycle_id = db.create_cycle()

    # Trigger an immediate cycle in the worker by calling _run_prediction_cycle directly
    # This runs in a background thread so we don't block the response
    app = current_app._get_current_object()
    def trigger_cycle():
        with app.app_context():
            try:
                worker._run_prediction_cycle(cycle_id=cycle_id)
                app.logger.info(f'Manual cycle {cycle_id} triggered via /api/cycle/start')
            except Exception as e:
                app.logger.error(f'Manual cycle error: {e}', exc_info=True)

    cycle_thread = threading.Thread(target=trigger_cycle, daemon=True)
    cycle_thread.start()

    return jsonify({
        'status': 'started',
        'cycle_id': cycle_id,
        'message': 'Prediction cycle started'
    }), 201


@api_bp.route('/cycle/<int:cycle_id>/stop', methods=['POST'])
def stop_cycle(cycle_id):
    """Manually stop a prediction cycle"""
    db = get_db()

    # Get cycle to verify it exists and is active
    cycle = db.get_cycle(cycle_id)

    if not cycle:
        return jsonify({
            'error': 'Cycle not found'
        }), 404

    if cycle['status'] != 'active':
        return jsonify({
            'error': 'Cycle is not active',
            'current_status': cycle['status']
        }), 400

    # Complete the cycle
    success = db.complete_cycle(cycle_id)

    if not success:
        return jsonify({
            'error': 'Failed to stop cycle'
        }), 500

    current_app.logger.info(f'Stopped prediction cycle {cycle_id}')

    return jsonify({
        'status': 'completed',
        'cycle_id': cycle_id
    })
