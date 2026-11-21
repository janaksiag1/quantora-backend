import asyncio

import time

from datetime import datetime, timezone

from typing import Protocol

import httpx

from .config import settings



NAMES = {'^NSEI': 'NIFTY 50', '^BSESN': 'SENSEX', '^NSEBANK': 'NIFTY BANK', 'BTC-USD': 'Bitcoin', 'ETH-USD': 'Ethereum', 'SOL-USD': 'Solana'}



class MarketProvider(Protocol):

    async def quote(self, symbol: str, period: str = '1mo') -> dict: ...



class YahooProvider:

    """Public, unofficial market adapter. No uptime or realtime guarantee."""

    def __init__(self):

        self.cache: dict[str, tuple[float, dict]] = {}

        self.semaphore = asyncio.Semaphore(5)



    async def quote(self, symbol: str, period: str = '1mo') -> dict:

        key = f'{symbol}:{period}'

        if key in self.cache and time.monotonic() - self.cache[key][0] < (5 if period == '1d' else 60):

            return self.cache[key][1]

        interval = '5m' if period == '1d' else '30m' if period == '5d' else '1d'

        async with self.semaphore:

            async with httpx.AsyncClient(timeout=15) as client:

                response = await client.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{httpx.URL(symbol).raw_path.decode()}', params={'range': period, 'interval': interval}, headers={'User-Agent': 'Quantora/1.0'})

                response.raise_for_status()

        data = response.json()['chart']['result'][0]

        meta, values = data['meta'], data['indicators']['quote'][0]

        points = []

        for i, stamp in enumerate(data.get('timestamp', [])):

            close = values['close'][i]

            if close is not None:

                points.append({'time': stamp * 1000, **{key: values.get(key, [None] * len(data['timestamp']))[i] for key in ['close', 'open', 'high', 'low', 'volume']}})

        from .quote_baseline import session_baseline
        baseline = session_baseline(meta, points, period)

        result = {'symbol': symbol, 'name': NAMES.get(symbol, meta.get('longName') or meta.get('shortName') or symbol), 'price': meta['regularMarketPrice'], 'change': (meta['regularMarketPrice'] / baseline - 1) * 100 if baseline else 0, 'currency': meta['currency'], 'asOf': datetime.fromtimestamp(meta['regularMarketTime'], timezone.utc).isoformat(), 'points': points, 'source': 'Yahoo Finance · may be delayed'}

        self.cache[key] = (time.monotonic(), result)

        if len(self.cache) > 300:

            self.cache.pop(next(iter(self.cache)))

        return result



class AIProvider(Protocol):

    async def generate(self, prompt: str) -> str: ...



class GeminiProvider:
    """Server-only credentials and explicit, observable model selection."""
    def __init__(self):
        self.semaphore = asyncio.Semaphore(4)

    async def generate(self, prompt: str, requested_model: str | None = None) -> str:
        keys = [k.get_secret_value() for k in [settings.gemini_api_key_tertiary, settings.gemini_api_key, settings.gemini_api_key_secondary] if k.get_secret_value()]
        if not keys:
            raise ValueError('Configure a server-side Gemini key to activate AI research.')
        models = [requested_model] if requested_model else list(dict.fromkeys([settings.gemini_model] + [m.strip() for m in settings.gemini_fallback_models.split(',') if m.strip()]))
        # Explicit model probes use the dedicated project, never an unknown paid key.
        if requested_model:
            keys = keys[:1]
        from .agent_policy import TEMPERATURE, system_prompt
        system = system_prompt()
        async with self.semaphore:
            async with httpx.AsyncClient(timeout=35) as client:
                for key in keys:
                    for model in models:
                        payload = {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'maxOutputTokens': 2400, 'temperature': TEMPERATURE}}
                        if model.startswith('gemma-'):
                            payload['contents'][0]['parts'][0]['text'] = system+'\n'+prompt
                        else:
                            payload['systemInstruction'] = {'parts': [{'text': system}]}
                        try:
                            r = await client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent', headers={'x-goog-api-key': key}, json=payload)
                            if not r.is_success:
                                continue
                            data = r.json()
                            output = ''.join(p.get('text', '') for p in data.get('candidates', [{}])[0].get('content', {}).get('parts', []) if not p.get('thought'))
                            if not output.strip():
                                continue
                            from .ai_router import model_used
                            model_used.set('google/'+data.get('modelVersion', model))
                            return output.strip()
                        except httpx.HTTPError:
                            continue
        raise ValueError('Requested model unavailable or free quota exhausted. No response was fabricated.')


market = YahooProvider()

from .ai_router import AIRouter

ai = AIRouter(GeminiProvider())



async def search_assets(query: str) -> list[dict]:

    async with httpx.AsyncClient(timeout=12) as client:

        r = await client.get('https://query1.finance.yahoo.com/v1/finance/search', params={'q': query, 'quotesCount': 12, 'newsCount': 0}, headers={'User-Agent': 'Mozilla/5.0'})

        if not r.is_success:
            from .market_sources import stock_directory
            return await stock_directory(query)

    return [{'symbol': x['symbol'], 'name': x.get('longname') or x.get('shortname') or x['symbol'], 'exchange': x.get('exchDisp', ''), 'type': x.get('quoteType', '')} for x in r.json().get('quotes', []) if x.get('symbol')]

