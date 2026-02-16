"""
API routes blueprint
REST endpoints and SSE streaming for predictions
"""
from flask import Blueprint, jsonify, Response, current_app, request
from app.database import get_db
import json
import time
from datetime import datetime, timedelta

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


@api_bp.route('/stream')
def stream():
    """SSE endpoint for real-time prediction updates"""

    def generate():
        """Generate SSE events"""
        # Set SSE headers
        yield f"retry: {current_app.config['SSE_RETRY']}\n\n"

        # Send initial connection event
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.now().isoformat()})}\n\n"

        # This is a placeholder - actual implementation would:
        # 1. Listen to a queue/channel for prediction events
        # 2. Stream updates as they happen
        # 3. Handle client disconnection gracefully

        # For now, send a heartbeat every 30 seconds
        last_heartbeat = time.time()
        while True:
            current_time = time.time()

            if current_time - last_heartbeat >= 30:
                yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now().isoformat()})}\n\n"
                last_heartbeat = current_time

            time.sleep(1)

            # TODO: Check for new predictions and yield them
            # Example event structure:
            # {
            #     'type': 'prediction',
            #     'cycle_id': 1,
            #     'stock': {'symbol': 'AAPL', 'name': 'Apple Inc.'},
            #     'prediction': {
            #         'provider': 'anthropic',
            #         'prediction': 'bullish',
            #         'confidence': 0.75,
            #         'reasoning': '...'
            #     }
            # }

    return Response(generate(), mimetype='text/event-stream')


@api_bp.route('/cycle/start', methods=['POST'])
def start_cycle():
    """Manually trigger a new prediction cycle"""
    db = get_db()

    # Check if there's already a running cycle
    running = db.execute('''
        SELECT id FROM cycles
        WHERE status = 'running'
        LIMIT 1
    ''').fetchone()

    if running:
        return jsonify({
            'error': 'Cycle already running',
            'cycle_id': running['id']
        }), 409

    # Create new cycle
    cursor = db.execute('''
        INSERT INTO cycles (start_time, status)
        VALUES (?, 'running')
    ''', (datetime.now(),))

    db.commit()

    cycle_id = cursor.lastrowid

    # TODO: Trigger background prediction worker
    current_app.logger.info(f'Started prediction cycle {cycle_id}')

    return jsonify({
        'status': 'started',
        'cycle_id': cycle_id,
        'message': 'Prediction cycle started'
    }), 201


@api_bp.route('/cycle/<int:cycle_id>/stop', methods=['POST'])
def stop_cycle(cycle_id):
    """Manually stop a prediction cycle"""
    db = get_db()

    cycle = db.execute('''
        SELECT * FROM cycles WHERE id = ? AND status = 'running'
    ''', (cycle_id,)).fetchone()

    if not cycle:
        return jsonify({
            'error': 'Cycle not found or already stopped'
        }), 404

    db.execute('''
        UPDATE cycles
        SET status = 'stopped', end_time = ?
        WHERE id = ?
    ''', (datetime.now(), cycle_id))

    db.commit()

    current_app.logger.info(f'Stopped prediction cycle {cycle_id}')

    return jsonify({
        'status': 'stopped',
        'cycle_id': cycle_id
    })
