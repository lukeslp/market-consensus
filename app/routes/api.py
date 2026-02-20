"""
API routes blueprint
REST endpoints and SSE streaming for predictions
"""
from flask import Blueprint, jsonify, Response, current_app, request
from app.database import get_db
import json
import logging
import time
from datetime import datetime

api_bp = Blueprint('api', __name__)
logger = logging.getLogger(__name__)


@api_bp.route('/current')
def current():
    """Get current prediction cycle data"""
    db = get_db()

    # Get current active cycle
    cycle = db.get_current_cycle()

    if not cycle:
        return jsonify({
            'status': 'no_cycles',
            'message': 'No prediction cycles yet',
            'cycle': None,
            'predictions': []
        }), 200

    # Get predictions for this cycle, then reduce to one row per ticker.
    # Priority: *-consensus > council-weighted > highest-confidence individual.
    all_predictions = db.get_predictions_for_cycle(cycle['id'])
    by_ticker = {}
    for p in all_predictions:
        ticker = p.get('ticker')
        if not ticker:
            continue
        existing = by_ticker.get(ticker)
        provider = p.get('provider', '')
        if existing is None:
            by_ticker[ticker] = p
        elif provider.endswith('-consensus'):
            by_ticker[ticker] = p
        elif provider == 'council-weighted' and not existing.get('provider', '').endswith('-consensus'):
            by_ticker[ticker] = p
        elif (
            not existing.get('provider', '').endswith('-consensus')
            and existing.get('provider') != 'council-weighted'
            and (p.get('confidence') or 0) > (existing.get('confidence') or 0)
        ):
            by_ticker[ticker] = p
    predictions = list(by_ticker.values())

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
        'total_stocks': summary.get('total_stocks', 0),
        'by_provider': leaderboard
    })


@api_bp.route('/history')
def history():
    """Get historical cycles with pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # Normalize pagination inputs
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)  # Max 100 per page
    offset = (page - 1) * per_page

    db = get_db()

    total_cycles = db.get_cycle_count()
    cycles = db.get_recent_cycles(limit=per_page, offset=offset)
    pages = (total_cycles + per_page - 1) // per_page if total_cycles > 0 else 0

    return jsonify({
        'cycles': cycles,
        'page': page,
        'per_page': per_page,
        'total': total_cycles,
        'pages': pages
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
    worker = getattr(current_app, 'worker', None)
    service = getattr(worker, 'prediction_service', None)
    if service is None:
        from app.services.prediction_service import PredictionService
        service = PredictionService(current_app.config)
    runtime_status = service.get_provider_runtime_status()

    provider_order = current_app.config.get(
        'PROVIDER_ORDER',
        ['anthropic', 'openai', 'gemini', 'xai', 'perplexity', 'mistral', 'huggingface', 'cohere']
    )
    provider_weights = current_app.config.get('PROVIDER_WEIGHTS', {})

    providers_status = {}
    for provider_name in provider_order:
        runtime = runtime_status.get(provider_name, {})
        initialized = provider_name in service.providers
        providers_status[provider_name] = {
            'status': 'configured' if (initialized and runtime.get('healthy', True)) else 'error',
            'provider': provider_name,
            'weight': provider_weights.get(provider_name, 1.0),
            'type': type(service.providers[provider_name]).__name__ if initialized else 'Not initialized',
            'last_error': runtime.get('last_error'),
            'last_failed_at': runtime.get('last_failed_at')
        }

    configured_healthy = all(p.get('status') == 'configured' for p in providers_status.values())
    runtime_healthy = all(v.get('healthy', True) for v in runtime_status.values())
    all_healthy = configured_healthy and runtime_healthy

    return jsonify({
        'healthy': all_healthy,
        'providers': providers_status,
        # Runtime health for every provider touched by the service
        'runtime': runtime_status
    })


@api_bp.route('/stream')
def stream():
    """SSE endpoint for real-time prediction updates.

    Uses cursor-based streaming (Last-Event-ID / id: N) so multiple browser
    tabs can watch simultaneously without competing for events.
    """
    from db import ForesightDB

    db_path = current_app.config['DB_PATH']
    sse_retry = current_app.config.get('SSE_RETRY', 3000)

    # Capture Last-Event-ID before entering the generator (request context ends there)
    try:
        last_event_id = int(request.headers.get('Last-Event-ID', 0) or 0)
    except (ValueError, TypeError):
        last_event_id = 0

    def generate():
        db = ForesightDB(db_path)

        # New connections start from the current tail so they don't replay history.
        # Reconnecting tabs send Last-Event-ID and resume from where they left off.
        last_id = last_event_id if last_event_id > 0 else db.get_latest_event_id()

        yield f"retry: {sse_retry}\n\n"
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.now().isoformat()})}\n\n"

        # Send initial state snapshot so the frontend has data immediately
        try:
            cycle = db.get_current_cycle()
            if cycle:
                snapshot = {
                    'type': 'snapshot',
                    'cycle': dict(cycle) if cycle else None,
                    'timestamp': datetime.now().isoformat()
                }
                yield f"data: {json.dumps(snapshot)}\n\n"
        except Exception:
            pass  # Non-critical; frontend will fetch via REST

        last_heartbeat = time.time()
        heartbeat_interval = 15  # 15-second heartbeat to keep connection alive

        while True:
            current_time = time.time()
            try:
                events = db.get_events_after(after_id=last_id, limit=10)

                for event in events:
                    last_id = event['id']
                    event_data = {
                        'id': event['id'],
                        'type': event['event_type'],
                        'data': event.get('data') or {},
                        'timestamp': event['timestamp']
                    }
                    # SSE id field lets the browser send Last-Event-ID on reconnect
                    yield f"id: {event['id']}\ndata: {json.dumps(event_data)}\n\n"

                if current_time - last_heartbeat >= heartbeat_interval:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now().isoformat()})}\n\n"
                    last_heartbeat = current_time

                time.sleep(1)

            except GeneratorExit:
                logger.info('SSE client disconnected')
                break

            except Exception as e:
                logger.error(f'SSE stream error: {e}')
                yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'timestamp': datetime.now().isoformat()})}\n\n"
                break

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache, no-transform',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


@api_bp.route('/worker/status')
def worker_status():
    """Get background worker status"""
    db = get_db()
    worker = current_app.worker
    status = worker.get_cluster_status() if hasattr(worker, 'get_cluster_status') else worker.get_status()
    current_cycle = db.get_current_cycle()

    # If the scheduler heartbeat has no in-flight cycle, surface DB active cycle for visibility.
    if current_cycle and not status.get('current_cycle_id'):
        status['current_cycle_id'] = current_cycle['id']

    return jsonify({
        'worker': status,
        'current_cycle': current_cycle,
        'config': {
            'cycle_interval': current_app.config['CYCLE_INTERVAL'],
            'market_timezone': current_app.config['MARKET_TIMEZONE'],
            'use_nyse_calendar': current_app.config['USE_NYSE_CALENDAR'],
            'market_open': f"{current_app.config['MARKET_OPEN_HOUR']:02d}:{current_app.config['MARKET_OPEN_MINUTE']:02d}",
            'market_close': f"{current_app.config['MARKET_CLOSE_HOUR']:02d}:{current_app.config['MARKET_CLOSE_MINUTE']:02d}",
            'nyse_early_close': f"{current_app.config['NYSE_EARLY_CLOSE_HOUR']:02d}:{current_app.config['NYSE_EARLY_CLOSE_MINUTE']:02d}",
            'market_open_interval_seconds': current_app.config['MARKET_OPEN_INTERVAL_SECONDS'],
            'worker_heartbeat_path': current_app.config['WORKER_HEARTBEAT_PATH'],
            'worker_heartbeat_max_age_seconds': current_app.config['WORKER_HEARTBEAT_MAX_AGE_SECONDS'],
            'provider_health_cooldown_seconds': current_app.config['PROVIDER_HEALTH_COOLDOWN_SECONDS'],
            'overnight_check_times': current_app.config['OVERNIGHT_CHECK_TIMES'],
            'overnight_lookahead_hours': current_app.config['OVERNIGHT_LOOKAHEAD_HOURS'],
            'overnight_light_mode': current_app.config['OVERNIGHT_LIGHT_MODE'],
            'overnight_full_debate_every': current_app.config['OVERNIGHT_FULL_DEBATE_EVERY'],
            'overnight_light_provider_order': current_app.config['OVERNIGHT_LIGHT_PROVIDER_ORDER'],
            'provider_order': current_app.config.get('PROVIDER_ORDER', []),
            'provider_weights': current_app.config.get('PROVIDER_WEIGHTS', {}),
            'max_stocks': current_app.config['MAX_STOCKS'],
            'lookback_days': current_app.config['LOOKBACK_DAYS'],
            'include_crypto': current_app.config['INCLUDE_CRYPTO'],
            'max_crypto_symbols': current_app.config['MAX_CRYPTO_SYMBOLS'],
            'crypto_symbols': current_app.config['CRYPTO_SYMBOLS'],
        }
    })


@api_bp.route('/cycle/start', methods=['POST'])
def start_cycle():
    """Manually trigger a new prediction cycle"""
    import threading

    db = get_db()

    # Check if there's already an active cycle
    current_cycle = db.get_current_cycle()

    if current_cycle and not current_cycle.get('_is_historical'):
        return jsonify({
            'error': 'Cycle already running',
            'cycle_id': current_cycle['id']
        }), 409

    worker = current_app.worker

    # Create new cycle
    cycle_id = db.create_cycle()

    # Trigger an immediate cycle in the worker by calling _run_prediction_cycle directly
    # This runs in a background thread so we don't block the response
    app = current_app._get_current_object()
    def trigger_cycle():
        with app.app_context():
            try:
                # Manual runs should work even if this request hits a Gunicorn
                # process that does not host the scheduler thread.
                worker._run_prediction_cycle(cycle_id=cycle_id, run_reason='manual')
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
