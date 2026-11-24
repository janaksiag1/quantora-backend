"""Provider-backed Telegram digests. No invented prices, flows or sentiment."""
import asyncio
import hashlib
import html
import json
import logging
import math
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from sqlalchemy.exc import IntegrityError
from .config import settings
from .models import Session, TelegramDelivery
from .providers import market
from .feeds import news
from .market_sources import market_status
from .telegram_bot import send_telegram_message, send_telegram_photo

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
_last_broadcasts = {}


def get_channel_target():
    return settings.telegram_chat_id


def digest_key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def scheduled_kind(now):
    now = now.astimezone(IST)
    if now.weekday() >= 5:
        return None
    minute = now.hour * 60 + now.minute
    if 535 <= minute < 555:
        return 'pre_market'
    if 555 <= minute < 930:
        return 'intraday'
    if 940 <= minute < 975:
        return 'closing_bell'
    return None


def claim(keys):
    # Unique keys arbitrate concurrent workers and cron calls using the same DB.
    try:
        with Session.begin() as db:
            for key in keys:
                db.add(TelegramDelivery(key=key, status='pending'))
        return True
    except IntegrityError:
        return False


async def broadcast_digest(kind='intraday', now=None):
    now = (now or datetime.now(IST)).astimezone(IST)
    if not settings.telegram_bot_token.get_secret_value() or not get_channel_target():
        return {'ok': False, 'error': 'Telegram environment is not configured'}
    if now.weekday() >= 5:
        return {'ok': True, 'skipped': 'Market weekend'}
    # Fail closed when exchange status cannot confirm an intraday trading session.
    if kind in ('intraday', 'pre_market'):
        if kind == 'intraday' and scheduled_kind(now) != 'intraday':
            return {'ok': True, 'skipped': 'Outside regular NSE hours'}
        try:
            status = await market_status()
        except Exception:
            return {'ok': True, 'skipped': 'Exchange session status unavailable'}
        if kind == 'pre_market':
            trade_date = str(status.get('tradeDate') or '')
            confirmed = False
            for fmt in ('%d-%b-%Y', '%d-%B-%Y', '%Y-%m-%d'):
                try:
                    confirmed = datetime.strptime(trade_date, fmt).date() == now.date()
                    if confirmed: break
                except ValueError: pass
            if not confirmed:
                return {'ok': True, 'skipped': 'Trading date not confirmed by exchange'}
        if kind == 'intraday' and status.get('state') != 'open':
            return {'ok': True, 'skipped': 'Exchange closed or holiday'}

    symbols = [s.strip() for s in settings.telegram_symbols.split(',') if s.strip()][:12]
    raw = await asyncio.gather(*(market.quote(s, '1d') for s in symbols), return_exceptions=True)
    quotes = []
    for q in raw:
        if not isinstance(q, dict):
            continue
        try:
            if not isinstance(q.get('currency'), str) or not q['currency'] or not q.get('symbol'):
                continue
            stamp = datetime.fromisoformat(q['asOf'].replace('Z', '+00:00'))
            age = (now - stamp.astimezone(IST)).total_seconds()
            if not math.isfinite(q['price']) or q['price'] <= 0 or not math.isfinite(q.get('change', float('nan'))):
                continue
            if age < -60 or (kind == 'intraday' and age > 1200):
                continue
            if kind != 'pre_market' and stamp.astimezone(IST).date() != now.date():
                continue
            q = {**q, '_stamp': stamp.astimezone(IST).strftime('%d %b %H:%M IST')}
            quotes.append(q)
        except (KeyError, TypeError, ValueError):
            continue
    try:
        headlines = await news()
    except Exception:
        headlines = []
    fresh = []
    for row in headlines:
        age = now.timestamp() - row.get('published', 0)
        key = 'news:' + digest_key(row.get('url', ''))
        if not (0 <= age <= 86400):
            continue
        with Session() as db:
            if db.get(TelegramDelivery, key):
                continue
        fresh.append((row, key))
    fresh = fresh[:2]
    if not quotes:
        return {'ok': True, 'skipped': 'No sufficiently fresh, timestamped quotes'}

    interval = max(5, min(60, settings.telegram_update_minutes))
    minute = now.hour * 60 + now.minute
    slot = f"{now.date()}:{kind}:{minute // interval if kind == 'intraday' else 'daily'}"
    content = [str(now.date()), [(q['symbol'], q['price'], q.get('change')) for q in quotes], [r['url'] for r, _ in fresh]]
    keys = ['slot:' + slot, 'content:' + digest_key(content)] + [key for _, key in fresh]
    if not claim(keys):
        return {'ok': True, 'skipped': 'Already delivered or unchanged content'}
    titles = ['MARKET CHECK-IN', 'PRICE & NEWS RADAR', 'RESEARCH DESK UPDATE']
    title = 'PRE-MARKET BRIEF' if kind == 'pre_market' else 'CLOSING SNAPSHOT' if kind == 'closing_bell' else titles[(minute // interval) % len(titles)]
    lines = [f"<b>GAINBUD · {title}</b>", now.strftime('%d %b %Y · %H:%M IST'), '']
    for q in quotes:
        lines += [f"<b>{html.escape(q.get('name') or q['symbol'])}</b> · {q['price']:,.2f} {html.escape(q['currency'])} · {q['change']:+.2f}%", f"Source: {html.escape(q.get('source') or 'Market provider')} · {q['_stamp']}"]
    if fresh:
        lines += ['', '<b>Latest published headlines</b>']
        for row, _ in fresh:
            published = datetime.fromtimestamp(row['published'], IST).strftime('%d %b %H:%M IST')
            lines += [f"• <a href=\"{html.escape(row['url'], quote=True)}\">{html.escape(row['title'][:180])}</a>", f"{html.escape(row['source'])} · {published}"]
    lines += ['', 'Quotes may be delayed. Research only; no guaranteed returns.']
    body = '\n'.join(lines)
    # Telegram HTML must remain complete; never slice through a source link.
    if len(body) > 4000:
        lines = lines[:3] + lines[3:3 + min(len(quotes), 5) * 2] + ['', 'Quotes may be delayed. Research only.']
        body = '\n'.join(lines)
    buttons = [{'text': 'Explore stocks', 'url': 'https://gainbud.in/app?module=stocks'}, {'text': 'Research desk', 'url': 'https://gainbud.in/app'}]
    # Plot actual available closes only; no generated or interpolated financial values.
    chart_quote = quotes[(minute // interval) % len(quotes)]
    points = [p for p in chart_quote.get('points', []) if isinstance(p.get('close'), (int, float)) and math.isfinite(p['close'])][-50:]
    image = None
    if len(points) >= 2:
        chart = {'type': 'line', 'data': {'labels': [datetime.fromtimestamp(p['time']/1000, IST).strftime('%H:%M') for p in points], 'datasets': [{'label': chart_quote['symbol'] + ' · available closes', 'data': [p['close'] for p in points], 'borderColor': '#13795b', 'fill': False}]}, 'options': {'title': {'display': True, 'text': chart_quote['symbol'] + ' · provider data, may be delayed'}}}
        image = 'https://quickchart.io/chart?' + urlencode({'width': 800, 'height': 400, 'backgroundColor': 'white', 'c': json.dumps(chart)})
    # A short caption plus link keeps the image optional and all facts in the full digest.
    result = await send_telegram_photo(image, body, buttons=buttons) if image and len(body) <= 1024 else await send_telegram_message(body, buttons=buttons)
    # For detailed digests, send the chart separately only after text delivery succeeds.
    if result.get('ok') and image and len(body) > 1024:
        await send_telegram_photo(image, f"{html.escape(chart_quote['symbol'])} · available provider closes · {chart_quote['_stamp']} · may be delayed", buttons=buttons)
    with Session.begin() as db:
        for key in keys:
            row = db.get(TelegramDelivery, key)
            row.status = 'sent' if result.get('ok') else 'failed'
    # Retain failed/ambiguous claims: no automatic duplicate after a timeout.
    if result.get('ok'):
        _last_broadcasts[kind] = now.isoformat()
    return result


async def broadcast_pre_market(): return await broadcast_digest('pre_market')
async def broadcast_morning_momentum(): return await broadcast_digest()
async def broadcast_ipo_gmp(): return {'ok': True, 'skipped': 'IPO-specific broadcast awaits a verified structured feed; use price/news digest'}
async def broadcast_mid_day_news(): return await broadcast_digest()
async def broadcast_power_hour(): return await broadcast_digest()
async def broadcast_closing_bell(): return await broadcast_digest('closing_bell')
async def broadcast_fii_dii(): return {'ok': True, 'skipped': 'Verified institutional-flow provider is not configured'}
async def broadcast_weekend_feature(): return {'ok': True, 'skipped': 'Automated broadcasts limited to trading sessions'}


async def run_scheduled_broadcast(now=None):
    if not settings.telegram_broadcast_enabled:
        return {'ok': True, 'skipped': 'Automatic broadcasts disabled'}
    now = now or datetime.now(IST)
    kind = scheduled_kind(now)
    if not kind:
        return {'ok': True, 'skipped': 'No scheduled trading session update'}
    return await broadcast_digest(kind, now)


async def telegram_auto_broadcaster_worker():
    await asyncio.sleep(45)
    while True:
        try:
            await run_scheduled_broadcast()
        except Exception:
            logger.error('Telegram broadcast cycle failed; claims retained to avoid duplicates')
        await asyncio.sleep(60)
