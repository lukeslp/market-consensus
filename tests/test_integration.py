"""
Integration tests for prediction cycles
Tests complete workflows from discovery to evaluation
Run with: pytest tests/test_integration.py -v
"""
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import patch


@pytest.mark.integration
class TestPredictionCycleWorkflow:
    """Test complete prediction cycle workflow"""

    def test_full_cycle_creation(self, db):
        """Can create complete prediction cycle"""
        # Create cycle
        cycle_id = db.create_cycle()
        cycle = db.get_cycle(cycle_id)

        assert cycle is not None
        assert cycle['status'] == 'active'

        # Add stocks
        stock_ids = []
        for ticker, name in [('AAPL', 'Apple'), ('MSFT', 'Microsoft')]:
            stock_id = db.add_stock(ticker, name)
            stock_ids.append(stock_id)

        db.update_cycle(cycle_id, stocks_discovered=len(stock_ids))

        # Add predictions
        for stock_id in stock_ids:
            pred_id = db.add_prediction(
                cycle_id=cycle_id,
                stock_id=stock_id,
                provider='anthropic',
                predicted_direction='up',
                confidence=0.75,
                initial_price=100.0,
                target_time=datetime.now() + timedelta(hours=1)
            )
            assert pred_id is not None

        db.update_cycle(cycle_id, predictions_made=len(stock_ids))

        # Complete cycle
        success = db.complete_cycle(cycle_id)
        assert success is True

        cycle = db.get_cycle(cycle_id)
        assert cycle['status'] == 'completed'

    def test_cycle_with_price_tracking(self, db):
        """Track prices throughout cycle"""
        cycle_id = db.create_cycle()
        stock_id = db.add_stock('AAPL', 'Apple Inc.')

        # Add initial price
        price_id = db.add_price(
            stock_id=stock_id,
            cycle_id=cycle_id,
            price=100.0,
            volume=1000000
        )

        # Make prediction
        pred_id = db.add_prediction(
            cycle_id=cycle_id,
            stock_id=stock_id,
            provider='anthropic',
            predicted_direction='up',
            confidence=0.75,
            initial_price=100.0,
            target_time=datetime.now() + timedelta(minutes=5)
        )

        # Add target price
        db.add_price(
            stock_id=stock_id,
            cycle_id=cycle_id,
            price=105.0,
            volume=1100000
        )

        # Evaluate prediction
        db.evaluate_prediction(pred_id, 105.0, 'up')

        prediction = db.get_prediction(pred_id)
        assert prediction['accuracy'] == 1.0

    def test_multi_provider_cycle(self, db):
        """Cycle with predictions from multiple providers"""
        cycle_id = db.create_cycle()
        stock_id = db.add_stock('AAPL', 'Apple Inc.')

        providers = ['anthropic', 'xai', 'gemini']
        predictions = []

        for provider in providers:
            pred_id = db.add_prediction(
                cycle_id=cycle_id,
                stock_id=stock_id,
                provider=provider,
                predicted_direction='up',
                confidence=0.7 + (0.05 * len(predictions)),
                initial_price=100.0,
                target_time=datetime.now() + timedelta(minutes=5)
            )
            predictions.append(pred_id)

        # Evaluate all predictions
        for pred_id in predictions:
            db.evaluate_prediction(pred_id, 105.0, 'up')

        # Check leaderboard
        leaderboard = db.get_provider_leaderboard()
        assert len(leaderboard) >= 3


@pytest.mark.integration
class TestEventStreamingWorkflow:
    """Test SSE event streaming workflow"""

    def test_events_created_on_prediction(self, db):
        """Events created when predictions are made"""
        initial_events = db.get_unprocessed_events()
        initial_count = len(initial_events)

        cycle_id = db.create_cycle()
        stock_id = db.add_stock('AAPL', 'Apple Inc.')

        db.add_prediction(
            cycle_id=cycle_id,
            stock_id=stock_id,
            provider='anthropic',
            predicted_direction='up',
            confidence=0.75,
            initial_price=100.0,
            target_time=datetime.now() + timedelta(hours=1)
        )

        events = db.get_unprocessed_events()
        assert len(events) > initial_count

    def test_event_processing_workflow(self, db):
        """Can process and clean up events"""
        # Create some events
        cycle_id = db.create_cycle()
        stock_id = db.add_stock('TEST', 'Test Corp')

        db.add_prediction(
            cycle_id=cycle_id,
            stock_id=stock_id,
            provider='test',
            predicted_direction='up',
            confidence=0.5,
            initial_price=100.0,
            target_time=datetime.now()
        )

        # Get unprocessed
        events = db.get_unprocessed_events()
        event_ids = [e['id'] for e in events[:5]]

        # Mark as processed
        if event_ids:
            db.mark_events_processed(event_ids)

            # Cleanup
            deleted = db.cleanup_old_events(days=0)
            assert deleted >= 0


@pytest.mark.integration
class TestAccuracyTracking:
    """Test accuracy tracking over multiple cycles"""

    def test_accuracy_aggregation(self, db):
        """Accuracy stats aggregate correctly"""
        # Create multiple cycles with predictions
        for cycle_num in range(3):
            cycle_id = db.create_cycle()
            stock_id = db.add_stock(f'STOCK{cycle_num}', f'Stock {cycle_num}')

            # Add prediction
            pred_id = db.add_prediction(
                cycle_id=cycle_id,
                stock_id=stock_id,
                provider='anthropic',
                predicted_direction='up',
                confidence=0.75,
                initial_price=100.0,
                target_time=datetime.now()
            )

            # Evaluate (alternate correct/incorrect)
            actual_dir = 'up' if cycle_num % 2 == 0 else 'down'
            db.evaluate_prediction(pred_id, 105.0, actual_dir)

            db.complete_cycle(cycle_id)

        # Check overall accuracy
        stats = db.calculate_accuracy_stats(provider='anthropic')

        assert stats['total_predictions'] == 3
        assert 0.0 <= stats['accuracy_rate'] <= 1.0

    def test_provider_comparison(self, db):
        """Can compare multiple providers"""
        cycle_id = db.create_cycle()
        stock_id = db.add_stock('AAPL', 'Apple Inc.')

        # Provider A: 2/3 correct
        for i in range(3):
            pred_id = db.add_prediction(
                cycle_id=cycle_id,
                stock_id=stock_id,
                provider='provider_a',
                predicted_direction='up',
                confidence=0.7,
                initial_price=100.0,
                target_time=datetime.now()
            )
            actual_dir = 'up' if i < 2 else 'down'
            db.evaluate_prediction(pred_id, 105.0, actual_dir)

        # Provider B: 1/2 correct
        for i in range(2):
            pred_id = db.add_prediction(
                cycle_id=cycle_id,
                stock_id=stock_id,
                provider='provider_b',
                predicted_direction='up',
                confidence=0.8,
                initial_price=100.0,
                target_time=datetime.now()
            )
            actual_dir = 'up' if i == 0 else 'down'
            db.evaluate_prediction(pred_id, 105.0, actual_dir)

        leaderboard = db.get_provider_leaderboard()

        # Find providers
        provider_a = next(p for p in leaderboard if p['provider'] == 'provider_a')
        provider_b = next(p for p in leaderboard if p['provider'] == 'provider_b')

        # Provider A should have better accuracy
        assert provider_a['accuracy_rate'] > provider_b['accuracy_rate']


@pytest.mark.integration
@pytest.mark.slow
class TestAPIWorkflow:
    """Test complete API workflow"""

    def test_cycle_api_workflow(self, client, db):
        """Complete workflow through API endpoints"""
        # Start cycle
        response = client.post('/api/cycle/start')
        assert response.status_code == 201
        data = response.get_json()
        cycle_id = data['cycle_id']

        # Check current
        response = client.get('/api/current')
        assert response.status_code == 200
        data = response.get_json()
        assert data['cycle']['id'] == cycle_id

        # Add stock and prediction manually
        stock_id = db.add_stock('AAPL', 'Apple Inc.')
        pred_id = db.add_prediction(
            cycle_id=cycle_id,
            stock_id=stock_id,
            provider='anthropic',
            predicted_direction='up',
            confidence=0.75,
            initial_price=150.0,
            target_time=datetime.now()
        )
        
        # Evaluate prediction so it shows in stats
        db.evaluate_prediction(pred_id, 155.0, 'up')

        # Check stats
        response = client.get('/api/stats')
        assert response.status_code == 200
        data = response.get_json()
        assert data['total_predictions'] >= 1

        # Stop cycle
        response = client.post(f'/api/cycle/{cycle_id}/stop')
        assert response.status_code == 200

        # Verify history
        response = client.get('/api/history')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['cycles']) >= 1
