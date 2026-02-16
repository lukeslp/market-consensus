"""
Database module tests for Foresight
Run with: python test_db.py
"""
import os
import tempfile
from datetime import datetime, timedelta
from db import ForesightDB


def test_database():
    """Test all database operations"""
    # Use temp database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name

    try:
        db = ForesightDB(db_path)
        print("✓ Database initialized with schema")

        # Test cycle operations
        print("\n--- Testing Cycles ---")
        cycle_id = db.create_cycle()
        print(f"✓ Created cycle: {cycle_id}")

        cycle = db.get_current_cycle()
        assert cycle['status'] == 'active'
        print(f"✓ Got current cycle: {cycle['id']}")

        db.update_cycle(cycle_id, stocks_discovered=5, predictions_made=10)
        updated = db.get_cycle(cycle_id)
        assert updated['stocks_discovered'] == 5
        assert updated['predictions_made'] == 10
        print("✓ Updated cycle stats")

        # Test stock operations
        print("\n--- Testing Stocks ---")
        stock_id = db.add_stock('AAPL', 'Apple Inc.', {'sector': 'Technology'})
        print(f"✓ Added stock AAPL: {stock_id}")

        stock = db.get_stock('AAPL')
        assert stock['ticker'] == 'AAPL'
        assert stock['name'] == 'Apple Inc.'
        assert stock['metadata']['sector'] == 'Technology'
        print("✓ Retrieved stock with metadata")

        # Test duplicate stock (should update)
        stock_id2 = db.add_stock('AAPL', 'Apple Inc. Updated')
        assert stock_id == stock_id2
        print("✓ Duplicate stock handling works")

        # Add more stocks
        db.add_stock('MSFT', 'Microsoft')
        db.add_stock('GOOGL', 'Alphabet')
        all_stocks = db.get_all_stocks()
        assert len(all_stocks) >= 3
        print(f"✓ Retrieved all stocks: {len(all_stocks)}")

        # Test price operations
        print("\n--- Testing Prices ---")
        price_id = db.add_price(
            stock_id=stock_id,
            cycle_id=cycle_id,
            price=150.25,
            volume=1000000,
            change_percent=2.5
        )
        print(f"✓ Added price snapshot: {price_id}")

        latest_price = db.get_latest_price(stock_id)
        assert latest_price['price'] == 150.25
        assert latest_price['volume'] == 1000000
        print("✓ Retrieved latest price")

        # Add historical prices
        for i in range(5):
            db.add_price(
                stock_id=stock_id,
                cycle_id=cycle_id,
                price=150.0 + i,
                timestamp=datetime.now() - timedelta(hours=i)
            )

        history = db.get_price_history(stock_id, limit=10)
        assert len(history) >= 5
        print(f"✓ Retrieved price history: {len(history)} entries")

        # Test price at time
        target_time = datetime.now() - timedelta(hours=2)
        price_at_time = db.get_price_at_time(stock_id, target_time)
        assert price_at_time is not None
        print("✓ Retrieved price at specific time")

        # Test prediction operations
        print("\n--- Testing Predictions ---")
        prediction_id = db.add_prediction(
            cycle_id=cycle_id,
            stock_id=stock_id,
            provider='anthropic',
            predicted_direction='up',
            confidence=0.75,
            initial_price=150.0,
            target_time=datetime.now() + timedelta(minutes=10),
            predicted_price=155.0,
            reasoning='Strong technical indicators suggest upward movement'
        )
        print(f"✓ Added prediction: {prediction_id}")

        prediction = db.get_prediction(prediction_id)
        assert prediction['predicted_direction'] == 'up'
        assert prediction['confidence'] == 0.75
        print("✓ Retrieved prediction")

        # Test prediction evaluation
        db.evaluate_prediction(
            prediction_id=prediction_id,
            actual_price=156.0,
            actual_direction='up'
        )
        evaluated = db.get_prediction(prediction_id)
        assert evaluated['accuracy'] == 1.0
        assert evaluated['actual_price'] == 156.0
        print("✓ Evaluated prediction (correct)")

        # Add incorrect prediction
        pred2_id = db.add_prediction(
            cycle_id=cycle_id,
            stock_id=stock_id,
            provider='xai',
            predicted_direction='down',
            confidence=0.65,
            initial_price=150.0,
            target_time=datetime.now() + timedelta(minutes=10)
        )
        db.evaluate_prediction(pred2_id, 152.0, 'up')
        pred2 = db.get_prediction(pred2_id)
        assert pred2['accuracy'] == 0.0
        print("✓ Evaluated prediction (incorrect)")

        # Get predictions for cycle
        cycle_predictions = db.get_predictions_for_cycle(cycle_id)
        assert len(cycle_predictions) >= 2
        print(f"✓ Retrieved cycle predictions: {len(cycle_predictions)}")

        # Get predictions for stock
        stock_predictions = db.get_predictions_for_stock(stock_id)
        assert len(stock_predictions) >= 2
        print(f"✓ Retrieved stock predictions: {len(stock_predictions)}")

        # Test unevaluated predictions
        pred3_id = db.add_prediction(
            cycle_id=cycle_id,
            stock_id=stock_id,
            provider='gemini',
            predicted_direction='neutral',
            confidence=0.5,
            initial_price=150.0,
            target_time=datetime.now() - timedelta(minutes=5)  # Past target
        )
        unevaluated = db.get_unevaluated_predictions()
        assert len(unevaluated) >= 1
        print(f"✓ Retrieved unevaluated predictions: {len(unevaluated)}")

        # Test accuracy stats
        print("\n--- Testing Accuracy Stats ---")
        stats = db.calculate_accuracy_stats(provider='anthropic', timeframe='24h')
        assert stats['total_predictions'] >= 1
        print(f"✓ Calculated accuracy stats: {stats['accuracy_rate']:.2%}")

        # Store accuracy stats
        stats_id = db.add_accuracy_stats(
            provider='anthropic',
            timeframe='24h',
            total_predictions=stats['total_predictions'],
            correct_predictions=stats['correct_predictions'],
            avg_confidence=stats['avg_confidence'],
            metadata={'test': True}
        )
        print(f"✓ Stored accuracy stats: {stats_id}")

        # Get provider leaderboard
        leaderboard = db.get_provider_leaderboard()
        assert len(leaderboard) >= 2
        print(f"✓ Generated provider leaderboard: {len(leaderboard)} providers")
        for entry in leaderboard:
            print(f"  {entry['provider']}: {entry['accuracy_rate']:.2%} ({entry['total_predictions']} predictions)")

        # Test event operations
        print("\n--- Testing Events ---")
        events = db.get_unprocessed_events()
        assert len(events) > 0
        print(f"✓ Retrieved unprocessed events: {len(events)}")

        event_ids = [e['id'] for e in events[:3]]
        db.mark_events_processed(event_ids)
        print(f"✓ Marked {len(event_ids)} events as processed")

        # Test dashboard summary
        print("\n--- Testing Dashboard Summary ---")
        summary = db.get_dashboard_summary()
        assert summary['current_cycle'] is not None
        assert summary['total_stocks'] >= 3
        print(f"✓ Dashboard summary:")
        print(f"  Total stocks: {summary['total_stocks']}")
        print(f"  Overall accuracy: {summary['overall_accuracy']:.2%}")
        print(f"  Recent predictions: {len(summary['recent_predictions'])}")

        # Test stock stats update
        print("\n--- Testing Stock Stats Update ---")
        db.update_stock_stats(
            stock_id=stock_id,
            times_predicted=100,
            avg_accuracy=0.75,
            last_price=160.0
        )
        updated_stock = db.get_stock_by_id(stock_id)
        assert updated_stock['times_predicted'] == 100
        assert updated_stock['avg_accuracy'] == 0.75
        print("✓ Updated stock statistics")

        # Test cycle completion
        print("\n--- Testing Cycle Completion ---")
        db.complete_cycle(cycle_id)
        completed = db.get_cycle(cycle_id)
        assert completed['status'] == 'completed'
        assert completed['end_time'] is not None
        print("✓ Completed cycle")

        # Test recent cycles
        recent = db.get_recent_cycles(limit=5)
        assert len(recent) >= 1
        print(f"✓ Retrieved recent cycles: {len(recent)}")

        # Test event cleanup
        print("\n--- Testing Event Cleanup ---")
        deleted = db.cleanup_old_events(days=0)  # Delete all processed events
        print(f"✓ Cleaned up old events: {deleted} deleted")

        print("\n✅ All database tests passed!")

    finally:
        # Cleanup temp database
        if os.path.exists(db_path):
            os.unlink(db_path)
            print(f"\n🧹 Cleaned up test database: {db_path}")


if __name__ == '__main__':
    test_database()
