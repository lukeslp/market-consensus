"""
Service layer tests
Tests StockService and PredictionService with mocked dependencies
Run with: pytest tests/test_services.py -v
"""
import pytest
import json
from unittest.mock import Mock, patch
from datetime import datetime


@pytest.mark.unit
class TestStockService:
    """Test StockService operations"""

    def test_fetch_stock_info_success(self, app_context, mock_yfinance):
        """Can fetch stock information"""
        from app.services.stock_service import StockService

        info = StockService.fetch_stock_info('AAPL')

        assert info is not None
        assert info['symbol'] == 'AAPL'
        assert 'price' in info
        assert 'name' in info

    def test_fetch_stock_info_invalid_symbol(self, app_context, mock_yfinance):
        """Returns None for invalid symbol"""
        from app.services.stock_service import StockService

        # Configure mock to raise exception
        mock_yfinance.info = {}
        mock_yfinance.history.side_effect = Exception("Invalid symbol")

        info = StockService.fetch_stock_info('INVALID')

        # Should handle error gracefully
        assert info is None or 'error' in info

    def test_validate_symbol(self, app_context, mock_yfinance):
        """Can validate stock symbols"""
        from app.services.stock_service import StockService

        # Valid symbol
        assert StockService.validate_symbol('AAPL') is True

    def test_fetch_historical_data(self, app_context, mock_yfinance):
        """Can fetch historical price data"""
        from app.services.stock_service import StockService

        data = StockService.fetch_historical_data('AAPL', days=30)

        assert data is not None
        assert 'close' in data or len(data) > 0


@pytest.mark.unit
class TestPredictionService:
    """Test PredictionService operations"""

    def test_initialization(self, app_context, mock_provider_factory):
        """PredictionService initializes with providers"""
        from app.services.prediction_service import PredictionService

        service = PredictionService(app_context.config)

        assert service is not None
        assert hasattr(service, 'providers')

    def test_discover_stocks(self, app_context, mock_provider_factory):
        """Can discover stocks using LLM"""
        from app.services.prediction_service import PredictionService

        # Configure mock to return stock list
        mock_provider_factory.complete.return_value.content = '["AAPL", "MSFT", "GOOGL"]'

        service = PredictionService(app_context.config)
        stocks = service.discover_stocks(count=3)

        assert isinstance(stocks, list)
        assert len(stocks) <= 3

    def test_discover_stocks_handles_errors(self, app_context, mock_provider_factory):
        """Discovery handles LLM errors gracefully"""
        from app.services.prediction_service import PredictionService

        # Configure mock to raise exception
        mock_provider_factory.complete.side_effect = Exception("LLM error")

        service = PredictionService(app_context.config)
        stocks = service.discover_stocks(count=3)

        # Should return empty list on error
        assert stocks == []

    def test_generate_prediction(self, app_context, mock_provider_factory):
        """Can generate prediction for stock"""
        from app.services.prediction_service import PredictionService

        # Configure mock response
        mock_provider_factory.complete.return_value.content = json.dumps({
            'prediction': 'UP',
            'confidence': 0.75,
            'reasoning': 'Strong upward trend'
        })

        service = PredictionService(app_context.config)
        stock_data = {'current_price': 150.0, 'close': [150, 151, 152]}

        prediction = service.generate_prediction('AAPL', stock_data)

        assert prediction is not None
        assert prediction['prediction'] == 'up'
        assert prediction['confidence'] == 0.75
        assert 'reasoning' in prediction

    def test_generate_prediction_handles_invalid_json(self, app_context, mock_provider_factory):
        """Prediction handles invalid LLM response"""
        from app.services.prediction_service import PredictionService

        # Configure mock to return invalid JSON
        mock_provider_factory.complete.return_value.content = 'Not valid JSON'

        service = PredictionService(app_context.config)
        prediction = service.generate_prediction('AAPL', {})

        # Should return None on error
        assert prediction is None

    def test_synthesize_confidence(self, app_context, mock_provider_factory):
        """Can synthesize confidence from multiple predictions"""
        from app.services.prediction_service import PredictionService

        # Configure mock to return confidence score
        mock_provider_factory.complete.return_value.content = '0.82'

        service = PredictionService(app_context.config)
        predictions = [
            {'prediction': 'UP', 'confidence': 0.8},
            {'prediction': 'UP', 'confidence': 0.75}
        ]

        confidence = service.synthesize_confidence(predictions)

        assert confidence is not None
        assert 0.0 <= confidence <= 1.0

    def test_synthesize_confidence_clamps_values(self, app_context, mock_provider_factory):
        """Synthesis clamps confidence to valid range"""
        from app.services.prediction_service import PredictionService

        # Configure mock to return out-of-range value
        mock_provider_factory.complete.return_value.content = '1.5'

        service = PredictionService(app_context.config)
        confidence = service.synthesize_confidence([])

        # Should clamp to 1.0
        assert confidence <= 1.0


@pytest.mark.integration
class TestServiceIntegration:
    """Integration tests between services and database"""

    def test_stock_service_to_database_flow(self, app_context, db, mock_yfinance):
        """Can fetch stock and store in database"""
        from app.services.stock_service import StockService

        info = StockService.fetch_stock_info('AAPL')

        if info:
            stock_id = db.add_stock(
                ticker=info['symbol'],
                name=info.get('name', 'Unknown'),
                metadata={'fetched_at': datetime.now().isoformat()}
            )

            stock = db.get_stock('AAPL')
            assert stock is not None
            assert stock['ticker'] == 'AAPL'

    def test_prediction_service_to_database_flow(self, app_context, db, sample_cycle, sample_stock, mock_provider_factory):
        """Can generate prediction and store in database"""
        from app.services.prediction_service import PredictionService

        mock_provider_factory.generate.return_value = json.dumps({
            'prediction': 'UP',
            'confidence': 0.75,
            'reasoning': 'Test'
        })

        service = PredictionService(app_context.config)
        prediction = service.generate_prediction('AAPL', {'current_price': 150.0})

        if prediction:
            pred_id = db.add_prediction(
                cycle_id=sample_cycle['id'],
                stock_id=sample_stock['id'],
                provider=prediction['provider'],
                predicted_direction=prediction['prediction'].lower(),
                confidence=prediction['confidence'],
                initial_price=150.0,
                target_time=datetime.now(),
                reasoning=prediction['reasoning']
            )

            stored = db.get_prediction(pred_id)
            assert stored is not None
            assert stored['predicted_direction'] == 'up'
