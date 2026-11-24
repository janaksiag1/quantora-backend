import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import telegram_broadcaster as b
from app.models import TelegramDelivery


@pytest.fixture
def desk(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    TelegramDelivery.__table__.create(engine)
    monkeypatch.setattr(b, 'Session', sessionmaker(engine))
    monkeypatch.setattr(b.settings, 'telegram_bot_token', SecretStr('test-only'))
    monkeypatch.setattr(b.settings, 'telegram_broadcast_enabled', True)
    monkeypatch.setattr(b.settings, 'telegram_symbols', '^NSEI')
    monkeypatch.setattr(b, 'market_status', AsyncMock(return_value={'state': 'open'}))
    now = datetime(2026, 11, 24, 10, 0, tzinfo=b.IST)
    quote = {'symbol': '^NSEI', 'name': 'NIFTY <50>', 'currency': 'INR', 'price': 123.45,
             'change': -0.25, 'asOf': now.isoformat(), 'source': 'Test provider',
             'points': [{'time': now.timestamp()*1000, 'close': 123.45},
                        {'time': (now.timestamp()+60)*1000, 'close': 123.46}]}
    monkeypatch.setattr(b.market, 'quote', AsyncMock(return_value=quote))
    monkeypatch.setattr(b, 'news', AsyncMock(return_value=[{'title': 'New <filing>',
        'url': 'https://example.com/news', 'source': 'Test publisher', 'published': now.timestamp()}]))
    send = AsyncMock(return_value={'ok': True})
    monkeypatch.setattr(b, 'send_telegram_message', send)
    monkeypatch.setattr(b, 'send_telegram_photo', send)
    yield now, quote, send
    engine.dispose()


def test_schedule_hours_and_weekends():
    for hour, minute in [(9, 14), (15, 30), (20, 0)]:
        assert b.scheduled_kind(datetime(2026, 11, 24, hour, minute, tzinfo=b.IST)) != 'intraday'
    assert b.scheduled_kind(datetime(2026, 11, 24, 9, 15, tzinfo=b.IST)) == 'intraday'
    assert b.scheduled_kind(datetime(2026, 11, 28, 10, 0, tzinfo=b.IST)) is None


def test_actual_quotes_chart_and_escaped_news(desk):
    now, _, send = desk
    assert asyncio.run(b.broadcast_digest(now=now))['ok']
    payload = str(send.call_args_list)
    assert '123.45' in payload and 'Test provider' in payload
    assert 'NIFTY &lt;50&gt;' in payload and 'New &lt;filing&gt;' in payload
    assert 'quickchart.io' in payload and 'may be delayed' in payload


def test_duplicate_and_unchanged_messages_skipped(desk):
    now, _, send = desk
    asyncio.run(b.broadcast_digest(now=now))
    calls = send.call_count
    assert 'skipped' in asyncio.run(b.broadcast_digest(now=now))
    # First later slot can contain the changed news set; subsequent unchanged content cannot.
    asyncio.run(b.broadcast_digest(now=now + timedelta(minutes=15)))
    assert 'skipped' in asyncio.run(b.broadcast_digest(now=now + timedelta(minutes=16)))
    assert send.call_count <= calls + 2


def test_holiday_and_unknown_session_send_nothing(desk, monkeypatch):
    now, _, send = desk
    b.market_status.return_value = {'state': 'closed'}
    assert 'skipped' in asyncio.run(b.broadcast_digest(now=now))
    b.market_status.side_effect = RuntimeError('unavailable')
    assert 'skipped' in asyncio.run(b.broadcast_digest(now=now))
    send.assert_not_called()


def test_stale_or_invalid_quotes_send_nothing(desk):
    now, quote, send = desk
    quote['asOf'] = (now - timedelta(hours=1)).isoformat()
    assert 'skipped' in asyncio.run(b.broadcast_digest(now=now))
    quote['asOf'] = now.isoformat()
    quote['price'] = float('nan')
    assert 'skipped' in asyncio.run(b.broadcast_digest(now=now))
    send.assert_not_called()


def test_delivery_failure_not_reported_success_or_retried(desk):
    now, _, send = desk
    send.return_value = {'ok': False, 'error': 'Telegram unavailable'}
    assert asyncio.run(b.broadcast_digest(now=now))['ok'] is False
    calls = send.call_count
    assert 'skipped' in asyncio.run(b.broadcast_digest(now=now))
    assert send.call_count == calls
