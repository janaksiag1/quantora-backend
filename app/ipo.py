import asyncio
import time
from datetime import datetime, timezone, timedelta
import httpx

cache = {}

async def get_issues(kind='current'):
    if kind in cache and time.monotonic() - cache[kind][0] < (20 if kind in ('current','upcoming') else 300):
        return cache[kind][1]
    endpoint = 'all-upcoming-issues?category=forthcoming' if kind == 'upcoming' else 'public-past-issues' if kind == 'past' else 'ipo-current-issue'
    source = f'https://www.nseindia.com/api/{endpoint}'
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        r = await client.get(source, headers={'User-Agent': 'Mozilla/5.0 QuantoraResearch/1.0', 'Referer': 'https://www.nseindia.com/market-data/all-upcoming-issues-ipo', 'Accept': 'application/json'})
        r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list):
        raise ValueError('Unexpected NSE response')
    issues = []
    seen = set()
    for row in rows:
        symbol = str(row.get('symbol', ''))
        category = str(row.get('category', 'Total'))
        if symbol in seen or category.lower() not in ['total', '', 'null']:
            continue
        seen.add(symbol)
        from .ipo_subscription import subscription_value
        subscription = subscription_value(row)
        listing_date = row.get('listingDate')
        listing_date = listing_date if listing_date and listing_date.strip() != '-' else None
        has_listed = False
        if listing_date:
            try:
                has_listed = datetime.strptime(listing_date, '%d-%b-%Y').date() <= datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
            except ValueError:
                pass
        status = (row.get('status') or ('Listed' if has_listed else 'Closed')) if kind == 'past' else row.get('status', 'Upcoming')
        price_band = row.get('priceRange') or row.get('issuePrice')
        price_band = str(price_band) if price_band and str(price_band).strip() != '-' else None
        issues.append({'symbol': symbol, 'name': row.get('companyName') or row.get('company') or symbol, 'opens': row.get('issueStartDate') or row.get('ipoStartDate'), 'closes': row.get('issueEndDate') or row.get('ipoEndDate'), 'listingDate': listing_date, 'priceBand': price_band, 'offeredShares': row.get('noOfSharesOffered'), 'sharesBid': row.get('noOfsharesBid'), 'issueSize': row.get('issueSize'), 'subscription': subscription, 'status': status, 'exchange': row.get('exchange') or 'NSE feed', 'series': row.get('series') or row.get('securityType', ''), 'source': source})
    result = {'issues': issues, 'source': source, 'asOf': datetime.now(timezone.utc).isoformat(), 'disclaimer': 'Source retrieval time is shown. Exchange publication may lag. No unofficial GMP or listing-gain forecasts are supplied.'}
    cache[kind] = (time.monotonic(), result)
    return result
