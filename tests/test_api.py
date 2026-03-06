"""
API endpoint tests
Tests REST endpoints and SSE streaming
Run with: pytest tests/test_api.py -v
"""
import pytest
import json
from datetime import datetime, timedelta


@pytest.mark.api
class TestHealthEndpoint:
    """Test health check endpoint"""

    def test_health_endpoint_returns_ok(self, client):
        """Health endpoint returns 200 OK"""
        response = client.get('/health')
        assert response.status_code == 200

    def test_health_endpoint_json_format(self, client):
        """Health endpoint returns JSON with expected structure"""
        response = client.get('/health')
        data = json.loads(response.data)

        assert 'status' in data
        assert 'timestamp' in data
        assert data['status'] in ['healthy', 'unhealthy']


@pytest.mark.api
class TestCurrentCycleEndpoint:
    """Test current cycle endpoint"""

    def test_current_no_cycles(self, client, db):
        """Returns 200 with no_cycles status when no cycles exist"""
        response = client.get('/api/current')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'no_cycles'

    def test_current_with_active_cycle(self, client, db, sample_cycle):
        """Returns current cycle data"""
        response = client.get('/api/current')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'cycle' in data
        assert 'predictions' in data
        assert data['cycle']['id'] == sample_cycle['id']
        assert data['cycle']['status'] == 'active'

    def test_current_includes_prediction_counts(self, client, db, sample_cycle, sample_prediction):
        """Current cycle includes prediction statistics"""
        response = client.get('/api/current')
        data = json.loads(response.data)

        assert 'stocks_discovered' in data
        assert 'predictions_made' in data
        assert isinstance(data['predictions'], list)


@pytest.mark.api
class TestStatsEndpoint:
    """Test accuracy statistics endpoint"""

    def test_stats_with_no_predictions(self, client, db):
        """Stats endpoint returns empty data when no predictions"""
        response = client.get('/api/stats')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['total_predictions'] == 0
        assert data['total_cycles'] == 0
        assert 'by_provider' in data

    def test_stats_with_predictions(self, client, db, sample_prediction):
        """Stats endpoint returns provider leaderboard"""
        # Evaluate the prediction
        db.evaluate_prediction(sample_prediction['id'], 155.0, 'up')

        response = client.get('/api/stats')
        data = json.loads(response.data)

        assert data['total_predictions'] >= 1
        assert data['completed_cycles'] >= 0
        assert len(data['by_provider']) >= 1

        # Check provider data structure
        provider = data['by_provider'][0]
        assert 'provider' in provider
        assert 'total_predictions' in provider
        assert 'accuracy_rate' in provider


@pytest.mark.api
class TestHistoryEndpoint:
    """Test cycle history endpoint"""

    def test_history_pagination_default(self, client, db, sample_cycle):
        """History endpoint returns paginated results"""
        response = client.get('/api/history')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'cycles' in data
        assert 'page' in data
        assert 'per_page' in data
        assert 'total' in data
        assert data['page'] == 1
        assert data['per_page'] == 20

    def test_history_pagination_custom(self, client, db):
        """History endpoint accepts custom pagination params"""
        # Create multiple cycles
        for i in range(5):
            db.create_cycle()

        response = client.get('/api/history?page=1&per_page=2')
        data = json.loads(response.data)

        assert data['page'] == 1
        assert data['per_page'] == 2
        assert len(data['cycles']) <= 2

    def test_history_max_per_page(self, client, db):
        """History endpoint enforces max per_page limit"""
        response = client.get('/api/history?per_page=1000')
        data = json.loads(response.data)

        assert data['per_page'] == 100  # Max enforced

    def test_history_pagination_second_page(self, client, db):
        """History endpoint returns distinct pages with total metadata."""
        for _ in range(5):
            db.create_cycle()

        page_one = json.loads(client.get('/api/history?page=1&per_page=2').data)
        page_two = json.loads(client.get('/api/history?page=2&per_page=2').data)

        assert page_two['page'] == 2
        assert page_two['per_page'] == 2
        assert page_two['total'] == 5
        assert page_two['pages'] == 3
        assert set(c['id'] for c in page_one['cycles']).isdisjoint(
            set(c['id'] for c in page_two['cycles'])
        )


@pytest.mark.api
class TestStockDetailEndpoint:
    """Test stock detail endpoint"""

    def test_stock_not_found(self, client, db):
        """Returns 404 for unknown stock"""
        response = client.get('/api/stock/INVALID')
        assert response.status_code == 404

        data = json.loads(response.data)
        assert 'error' in data

    def test_stock_detail_success(self, client, db, sample_stock, sample_prediction):
        """Returns complete stock data"""
        response = client.get(f'/api/stock/{sample_stock["ticker"]}')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['symbol'] == sample_stock['ticker']
        assert 'stock' in data
        assert 'predictions' in data
        assert 'price_history' in data
        assert isinstance(data['predictions'], list)

    def test_stock_case_insensitive(self, client, db, sample_stock):
        """Stock lookup is case-insensitive"""
        response = client.get('/api/stock/aapl')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['symbol'] == 'AAPL'


@pytest.mark.api
class TestCycleControlEndpoints:
    """Test cycle start/stop endpoints"""

    def test_start_cycle_success(self, client, db):
        """Can start new cycle"""
        response = client.post('/api/cycle/start')
        assert response.status_code == 201

        data = json.loads(response.data)
        assert data['status'] == 'started'
        assert 'cycle_id' in data

        # Verify cycle was created
        cycle = db.get_cycle(data['cycle_id'])
        assert cycle is not None
        assert cycle['status'] == 'active'

    def test_start_cycle_already_running(self, client, db, sample_cycle):
        """Cannot start cycle when one is already running"""
        response = client.post('/api/cycle/start')
        assert response.status_code == 409

        data = json.loads(response.data)
        assert 'error' in data

    def test_stop_cycle_success(self, client, db, sample_cycle):
        """Can stop active cycle"""
        response = client.post(f'/api/cycle/{sample_cycle["id"]}/stop')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['status'] == 'completed'

        # Verify cycle was completed
        cycle = db.get_cycle(sample_cycle['id'])
        assert cycle['status'] == 'completed'

    def test_stop_nonexistent_cycle(self, client, db):
        """Returns 404 for nonexistent cycle"""
        response = client.post('/api/cycle/99999/stop')
        assert response.status_code == 404

    def test_stop_already_completed_cycle(self, client, db, sample_cycle):
        """Cannot stop already completed cycle"""
        db.complete_cycle(sample_cycle['id'])

        response = client.post(f'/api/cycle/{sample_cycle["id"]}/stop')
        assert response.status_code == 400

        data = json.loads(response.data)
        assert 'error' in data


@pytest.mark.api
class TestWorkerStatusEndpoint:
    """Test worker status endpoint"""

    def test_worker_status_includes_current_cycle(self, client, db, sample_cycle):
        """Worker status includes active DB cycle metadata."""
        response = client.get('/api/worker/status')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'worker' in data
        assert 'current_cycle' in data
        assert data['current_cycle']['id'] == sample_cycle['id']

    def test_worker_status_includes_cluster_fields(self, client):
        """Worker status exposes local/cluster fields for multi-process deployments."""
        response = client.get('/api/worker/status')
        assert response.status_code == 200

        data = json.loads(response.data)
        worker = data['worker']
        assert 'status_source' in worker
        assert 'local_running' in worker
        assert 'local_alive' in worker
        assert 'scheduler_lock_acquired' in worker


@pytest.mark.api
@pytest.mark.slow
class TestSSEStreamingEndpoint:
    """Test Server-Sent Events streaming"""

    def test_sse_initial_connection(self, client):
        """SSE endpoint sends initial connection event"""
        response = client.get('/api/stream')

        # SSE should return 200
        assert response.status_code == 200
        assert response.mimetype == 'text/event-stream'

        # Note: Full SSE testing requires async or threading
        # This is a basic connection test

    def test_sse_headers(self, client):
        """SSE endpoint sets correct headers"""
        response = client.get('/api/stream')

        assert response.content_type == 'text/event-stream; charset=utf-8'


@pytest.mark.api
class TestErrorHandling:
    """Test API error handling"""

    def test_404_for_unknown_endpoint(self, client):
        """Returns 404 for unknown endpoints"""
        response = client.get('/api/nonexistent')
        assert response.status_code == 404

    def test_405_for_wrong_method(self, client):
        """Returns 405 for wrong HTTP method"""
        response = client.get('/api/cycle/start')  # Should be POST
        assert response.status_code == 405

    def test_error_response_format(self, client):
        """Error responses return JSON"""
        response = client.get('/api/stock/INVALID')
        assert response.status_code == 404

        data = json.loads(response.data)
        assert 'error' in data
