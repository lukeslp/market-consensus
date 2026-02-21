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


@api_bp.route('/watchlist')
def watchlist():
    """Return the full watchlist (all 100 tracked symbols) with latest prediction data merged in.
    Stocks without predictions yet show as pending."""
    from app.config import TOP_50_EQUITIES, TOP_50_CRYPTO

    equity_list = current_app.config.get('EQUITY_WATCHLIST', TOP_50_EQUITIES)
    crypto_list = current_app.config.get('CRYPTO_WATCHLIST', TOP_50_CRYPTO)

    db = get_db()
    cycle = db.get_current_cycle()

    # Build prediction lookup from current cycle
    pred_by_ticker = {}
    if cycle:
        all_predictions = db.get_predictions_for_cycle(cycle['id'])
        for p in all_predictions:
            ticker = p.get('ticker')
            if not ticker:
                continue
            existing = pred_by_ticker.get(ticker)
            provider = p.get('provider', '')
            if existing is None:
                pred_by_ticker[ticker] = p
            elif provider.endswith('-consensus'):
                pred_by_ticker[ticker] = p
            elif provider == 'council-weighted' and not existing.get('provider', '').endswith('-consensus'):
                pred_by_ticker[ticker] = p
            elif (
                not existing.get('provider', '').endswith('-consensus')
                and existing.get('provider') != 'council-weighted'
                and (p.get('confidence') or 0) > (existing.get('confidence') or 0)
            ):
                pred_by_ticker[ticker] = p

    # Build stock info lookup from DB
    all_stocks = db.get_all_stocks()
    stock_info = {s['ticker'].upper(): s for s in all_stocks}

    # Merge watchlist with predictions
    items = []
    seen = set()
    for symbol in equity_list + crypto_list:
        key = symbol.upper()
        if key in seen:
            continue
        seen.add(key)
        pred = pred_by_ticker.get(key)
        info = stock_info.get(key, {})
        is_crypto = key.endswith('-USD') or key.startswith('MARKET-CRYPTO')
        item = {
            'ticker': key,
            'name': info.get('name', ''),
            'asset_type': 'crypto' if is_crypto else 'equity',
            'last_price': info.get('last_price'),
            'predicted_direction': pred.get('predicted_direction') if pred else None,
            'confidence': pred.get('confidence') if pred else None,
            'initial_price': pred.get('initial_price') if pred else info.get('last_price'),
            'provider': pred.get('provider', '') if pred else '',
            'prediction_time': pred.get('prediction_time') if pred else None,
            'target_time': pred.get('target_time') if pred else None,
            'times_predicted': info.get('times_predicted', 0),
            'avg_accuracy': info.get('avg_accuracy'),
            'has_prediction': pred is not None,
        }
        items.append(item)

    return jsonify({
        'cycle': cycle,
        'watchlist': items,
        'total_equities': len(equity_list),
        'total_crypto': len(crypto_list),
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

    # Get agent votes (latest cycle first, then all)
    cycle = db.get_current_cycle()
    agent_votes = []
    debate_rounds = []
    if cycle:
        agent_votes = db.get_agent_votes_for_stock(stock['id'], cycle_id=cycle['id'])
        debate_rounds = db.get_debate_rounds_for_stock(stock['id'], cycle_id=cycle['id'])
    if not agent_votes:
        agent_votes = db.get_agent_votes_for_stock(stock['id'], limit=50)
    if not debate_rounds:
        debate_rounds = db.get_debate_rounds_for_stock(stock['id'], limit=10)

    return jsonify({
        'symbol': symbol.upper(),
        'stock': stock,
        'predictions': predictions,
        'price_history': price_history,
        'agent_votes': agent_votes,
        'debate_rounds': debate_rounds,
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
    from db import ConsensusDB

    db_path = current_app.config['DB_PATH']
    sse_retry = current_app.config.get('SSE_RETRY', 3000)

    # Capture Last-Event-ID before entering the generator (request context ends there)
    try:
        last_event_id = int(request.headers.get('Last-Event-ID', 0) or 0)
    except (ValueError, TypeError):
        last_event_id = 0

    def generate():
        db = ConsensusDB(db_path)

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


# ========== Corpus Export Endpoints ==========

@api_bp.route('/corpus/predictions')
def corpus_predictions():
    """Export all predictions with full detail for corpus analysis.
    Supports pagination via ?page=1&per_page=500 and optional filters:
      ?cycle_id=N  ?provider=name  ?ticker=AAPL  ?phase=analysis
    """
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 500, type=int), 5000)
    offset = (page - 1) * per_page

    cycle_id = request.args.get('cycle_id', type=int)
    provider = request.args.get('provider')
    ticker = request.args.get('ticker')

    with db.get_connection() as conn:
        query = """
            SELECT p.*, s.ticker, s.name as stock_name, c.start_time as cycle_start
            FROM predictions p
            JOIN stocks s ON p.stock_id = s.id
            JOIN cycles c ON p.cycle_id = c.id
            WHERE 1=1
        """
        count_query = """
            SELECT COUNT(*) as total
            FROM predictions p
            JOIN stocks s ON p.stock_id = s.id
            WHERE 1=1
        """
        params = []
        count_params = []

        if cycle_id:
            query += " AND p.cycle_id = ?"
            count_query += " AND p.cycle_id = ?"
            params.append(cycle_id)
            count_params.append(cycle_id)
        if provider:
            query += " AND p.provider = ?"
            count_query += " AND p.provider = ?"
            params.append(provider)
            count_params.append(provider)
        if ticker:
            query += " AND s.ticker = ?"
            count_query += " AND s.ticker = ?"
            params.append(ticker.upper())
            count_params.append(ticker.upper())

        total = conn.execute(count_query, count_params).fetchone()['total']
        query += " ORDER BY p.id ASC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        rows = conn.execute(query, params).fetchall()

    results = []
    for row in rows:
        d = dict(row)
        # Parse JSON fields
        if d.get('usage_tokens'):
            try:
                d['usage_tokens'] = json.loads(d['usage_tokens'])
            except (json.JSONDecodeError, TypeError):
                pass
        results.append(d)

    return jsonify({
        'predictions': results,
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': (total + per_page - 1) // per_page if total > 0 else 0,
    })


@api_bp.route('/corpus/agent_votes')
def corpus_agent_votes():
    """Export all agent votes with full detail for corpus analysis.
    Supports pagination via ?page=1&per_page=500 and optional filters:
      ?cycle_id=N  ?provider=name  ?ticker=AAPL  ?phase=analysis|synthesis|council|market
    """
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 500, type=int), 5000)
    offset = (page - 1) * per_page

    cycle_id = request.args.get('cycle_id', type=int)
    provider = request.args.get('provider')
    ticker = request.args.get('ticker')
    phase = request.args.get('phase')

    with db.get_connection() as conn:
        query = """
            SELECT av.*, s.ticker, s.name as stock_name
            FROM agent_votes av
            JOIN stocks s ON av.stock_id = s.id
            WHERE 1=1
        """
        count_query = """
            SELECT COUNT(*) as total
            FROM agent_votes av
            JOIN stocks s ON av.stock_id = s.id
            WHERE 1=1
        """
        params = []
        count_params = []

        if cycle_id:
            query += " AND av.cycle_id = ?"
            count_query += " AND av.cycle_id = ?"
            params.append(cycle_id)
            count_params.append(cycle_id)
        if provider:
            query += " AND av.provider = ?"
            count_query += " AND av.provider = ?"
            params.append(provider)
            count_params.append(provider)
        if ticker:
            query += " AND s.ticker = ?"
            count_query += " AND s.ticker = ?"
            params.append(ticker.upper())
            count_params.append(ticker.upper())
        if phase:
            query += " AND av.phase = ?"
            count_query += " AND av.phase = ?"
            params.append(phase)
            count_params.append(phase)

        total = conn.execute(count_query, count_params).fetchone()['total']
        query += " ORDER BY av.id ASC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        rows = conn.execute(query, params).fetchall()

    results = []
    for row in rows:
        d = dict(row)
        if d.get('usage_tokens'):
            try:
                d['usage_tokens'] = json.loads(d['usage_tokens'])
            except (json.JSONDecodeError, TypeError):
                pass
        results.append(d)

    return jsonify({
        'agent_votes': results,
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': (total + per_page - 1) // per_page if total > 0 else 0,
    })


@api_bp.route('/corpus/debate_rounds')
def corpus_debate_rounds():
    """Export all debate rounds with full detail for corpus analysis.
    Supports pagination via ?page=1&per_page=500 and optional filters:
      ?cycle_id=N  ?ticker=AAPL  ?round_type=council|synthesis|market
    """
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 500, type=int), 5000)
    offset = (page - 1) * per_page

    cycle_id = request.args.get('cycle_id', type=int)
    ticker = request.args.get('ticker')
    round_type = request.args.get('round_type')

    with db.get_connection() as conn:
        query = """
            SELECT dr.*, s.ticker, s.name as stock_name
            FROM debate_rounds dr
            JOIN stocks s ON dr.stock_id = s.id
            WHERE 1=1
        """
        count_query = """
            SELECT COUNT(*) as total
            FROM debate_rounds dr
            JOIN stocks s ON dr.stock_id = s.id
            WHERE 1=1
        """
        params = []
        count_params = []

        if cycle_id:
            query += " AND dr.cycle_id = ?"
            count_query += " AND dr.cycle_id = ?"
            params.append(cycle_id)
            count_params.append(cycle_id)
        if ticker:
            query += " AND s.ticker = ?"
            count_query += " AND s.ticker = ?"
            params.append(ticker.upper())
            count_params.append(ticker.upper())
        if round_type:
            query += " AND dr.round_type = ?"
            count_query += " AND dr.round_type = ?"
            params.append(round_type)
            count_params.append(round_type)

        total = conn.execute(count_query, count_params).fetchone()['total']
        query += " ORDER BY dr.id ASC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        rows = conn.execute(query, params).fetchall()

    results = []
    for row in rows:
        d = dict(row)
        if d.get('vote_totals'):
            try:
                d['vote_totals'] = json.loads(d['vote_totals'])
            except (json.JSONDecodeError, TypeError):
                pass
        if d.get('provider_weights'):
            try:
                d['provider_weights'] = json.loads(d['provider_weights'])
            except (json.JSONDecodeError, TypeError):
                pass
        results.append(d)

    return jsonify({
        'debate_rounds': results,
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': (total + per_page - 1) // per_page if total > 0 else 0,
    })


@api_bp.route('/corpus/summary')
def corpus_summary():
    """Get a summary of all data available for corpus analysis."""
    db = get_db()

    with db.get_connection() as conn:
        pred_count = conn.execute("SELECT COUNT(*) as n FROM predictions").fetchone()['n']
        vote_count = conn.execute("SELECT COUNT(*) as n FROM agent_votes").fetchone()['n']
        debate_count = conn.execute("SELECT COUNT(*) as n FROM debate_rounds").fetchone()['n']
        cycle_count = conn.execute("SELECT COUNT(*) as n FROM cycles").fetchone()['n']
        stock_count = conn.execute("SELECT COUNT(*) as n FROM stocks").fetchone()['n']
        price_count = conn.execute("SELECT COUNT(*) as n FROM prices").fetchone()['n']

        # Date range
        date_range = conn.execute("""
            SELECT MIN(prediction_time) as earliest, MAX(prediction_time) as latest
            FROM predictions
        """).fetchone()

        # Provider breakdown
        providers = conn.execute("""
            SELECT provider, COUNT(*) as count
            FROM predictions
            GROUP BY provider
            ORDER BY count DESC
        """).fetchall()

        # Agent vote phase breakdown
        phases = conn.execute("""
            SELECT phase, COUNT(*) as count
            FROM agent_votes
            GROUP BY phase
            ORDER BY count DESC
        """).fetchall()

        # Debate round type breakdown
        round_types = conn.execute("""
            SELECT round_type, COUNT(*) as count
            FROM debate_rounds
            GROUP BY round_type
            ORDER BY count DESC
        """).fetchall()

        # Columns with data (non-null counts for key fields)
        data_coverage = conn.execute("""
            SELECT
                COUNT(*) as total_predictions,
                SUM(CASE WHEN raw_response IS NOT NULL AND raw_response != '' THEN 1 ELSE 0 END) as has_raw_response,
                SUM(CASE WHEN model IS NOT NULL AND model != '' THEN 1 ELSE 0 END) as has_model,
                SUM(CASE WHEN prompt IS NOT NULL AND prompt != '' THEN 1 ELSE 0 END) as has_prompt,
                SUM(CASE WHEN usage_tokens IS NOT NULL THEN 1 ELSE 0 END) as has_usage_tokens,
                SUM(CASE WHEN reasoning IS NOT NULL AND reasoning != '' THEN 1 ELSE 0 END) as has_reasoning,
                SUM(CASE WHEN accuracy IS NOT NULL THEN 1 ELSE 0 END) as has_accuracy
            FROM predictions
        """).fetchone()

        vote_coverage = conn.execute("""
            SELECT
                COUNT(*) as total_votes,
                SUM(CASE WHEN raw_response IS NOT NULL AND raw_response != '' THEN 1 ELSE 0 END) as has_raw_response,
                SUM(CASE WHEN prompt IS NOT NULL AND prompt != '' THEN 1 ELSE 0 END) as has_prompt,
                SUM(CASE WHEN usage_tokens IS NOT NULL THEN 1 ELSE 0 END) as has_usage_tokens,
                SUM(CASE WHEN reasoning IS NOT NULL AND reasoning != '' THEN 1 ELSE 0 END) as has_reasoning
            FROM agent_votes
        """).fetchone()

    return jsonify({
        'totals': {
            'predictions': pred_count,
            'agent_votes': vote_count,
            'debate_rounds': debate_count,
            'cycles': cycle_count,
            'stocks': stock_count,
            'price_snapshots': price_count,
        },
        'date_range': {
            'earliest': date_range['earliest'] if date_range else None,
            'latest': date_range['latest'] if date_range else None,
        },
        'providers': [{'provider': r['provider'], 'count': r['count']} for r in providers],
        'agent_vote_phases': [{'phase': r['phase'], 'count': r['count']} for r in phases],
        'debate_round_types': [{'round_type': r['round_type'], 'count': r['count']} for r in round_types],
        'data_coverage': {
            'predictions': dict(data_coverage) if data_coverage else {},
            'agent_votes': dict(vote_coverage) if vote_coverage else {},
        },
    })
