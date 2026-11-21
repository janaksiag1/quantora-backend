import asyncio
import pytest
from app.evidence import inspect_evidence
from app.providers import market

def test_price_statistics_use_observations_and_do_not_predict(monkeypatch):
    async def source(*args):
        return {'symbol': 'TEST.NS', 'name': 'Test-only series', 'points': [{'close': 100+i} for i in range(60)], 'currency': 'INR'}
    monkeypatch.setattr(market, 'quote', source)
    result = asyncio.run(inspect_evidence('TEST.NS'))
    metrics = result['metrics']
    assert metrics['observations'] == 60
    assert metrics['periodReturn'] == pytest.approx(59)
    assert metrics['maxDrawdown'] == 0
    assert metrics['sma20'] == 149.5
    assert metrics['sma50'] == 134.5
    assert metrics['rsi14'] == 100
    assert 'No prediction' in result['method']
