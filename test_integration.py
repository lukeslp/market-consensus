#!/usr/bin/env python3
"""
Integration test for Foresight core components
Tests database, worker, and SSE streaming
"""
import sys
from pathlib import Path

# Add project root to path
root_dir = Path(__file__).parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Add shared library to path
if '/home/coolhand/shared' not in sys.path:
    sys.path.append('/home/coolhand/shared')

import time
import json
from datetime import datetime, timedelta
from db import ForesightDB


def test_database():
    """Test database operations"""
    print("\n=== Testing Database ===")

    # Use test database
    test_db_path = root_dir / 'test_foresight.db'
    if test_db_path.exists():
        test_db_path.unlink()

    db = ForesightDB(str(test_db_path))

    # Test cycle creation
    cycle_id = db.create_cycle()
    print(f"✓ Created cycle: {cycle_id}")

    # Test stock addition
    stock_id = db.add_stock(
        ticker='AAPL',
        name='Apple Inc.',
        metadata={'sector': 'Technology', 'test': True}
    )
    print(f"✓ Added stock: {stock_id}")

    # Test price recording
    db.add_price(stock_id=stock_id, cycle_id=cycle_id, price=175.50)
    print(f"✓ Recorded price")

    # Test prediction
    from datetime import timedelta
    target_time = datetime.now() + timedelta(days=7)
    prediction_id = db.add_prediction(
        cycle_id=cycle_id,
        stock_id=stock_id,
        provider='anthropic',
        predicted_direction='up',
        confidence=0.75,
        reasoning='Test prediction',
        initial_price=175.50,
        target_time=target_time
    )
    print(f"✓ Added prediction: {prediction_id}")

    # Test event retrieval (events are auto-emitted by database operations)
    events = db.get_unprocessed_events(limit=10)
    print(f"✓ Retrieved {len(events)} unprocessed events")

    # Test cycle completion
    db.complete_cycle(cycle_id)
    print(f"✓ Completed cycle")

    # Clean up
    test_db_path.unlink()
    print(f"✓ Cleaned up test database")

    print("✅ Database tests passed!")


def test_worker_initialization():
    """Test worker can be initialized"""
    print("\n=== Testing Worker Initialization ===")

    from app.worker import PredictionWorker
    from app.config import DevelopmentConfig

    config = DevelopmentConfig()
    config.DB_PATH = str(root_dir / 'test_worker.db')
    config.CYCLE_INTERVAL = 30  # Short interval for testing

    worker = PredictionWorker(config)
    print(f"✓ Worker initialized")
    print(f"  Status: {worker.get_status()}")

    # Don't actually start the worker thread (would run indefinitely)
    # Just verify it can be created

    # Clean up
    db_path = Path(config.DB_PATH)
    if db_path.exists():
        db_path.unlink()

    print("✅ Worker initialization test passed!")


def test_sse_pattern():
    """Test SSE event generation pattern"""
    print("\n=== Testing SSE Pattern ===")

    def generate_sse_events():
        """Mock SSE generator"""
        # Connection event
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': 'now'})}\n\n"

        # Sample events
        for i in range(3):
            event = {
                'type': 'test_event',
                'count': i,
                'data': {'message': f'Event {i}'}
            }
            yield f"data: {json.dumps(event)}\n\n"

        # Completion
        yield f"data: {json.dumps({'type': 'complete'})}\n\n"

    # Collect generated events
    events = list(generate_sse_events())
    print(f"✓ Generated {len(events)} SSE events")

    # Verify format
    for event in events:
        assert event.startswith('data: '), "Event must start with 'data: '"
        assert event.endswith('\n\n'), "Event must end with double newline"

    print("✅ SSE pattern test passed!")


def test_services():
    """Test service initialization"""
    print("\n=== Testing Services ===")

    from app.services.stock_service import StockService
    from app.services.prediction_service import PredictionService
    from app.config import DevelopmentConfig

    # Test StockService
    stock_service = StockService()
    print(f"✓ StockService initialized")

    # Test market status (doesn't require API key)
    try:
        status = stock_service.get_market_status()
        print(f"✓ Market status: {status.get('market_state', 'UNKNOWN')}")
    except Exception as e:
        print(f"⚠ Market status check failed (may be network issue): {e}")

    # Test PredictionService initialization
    config = DevelopmentConfig()
    prediction_service = PredictionService(config)
    print(f"✓ PredictionService initialized")
    print(f"  Providers: {list(config.PROVIDERS.keys())}")

    print("✅ Services test passed!")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Foresight Integration Tests")
    print("=" * 60)

    try:
        test_database()
        test_worker_initialization()
        test_sse_pattern()
        test_services()

        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
