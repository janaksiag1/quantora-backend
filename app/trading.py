"""Secure bounded research API, reusing Gainbud providers. No brokerage execution."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .providers import market
from .trading_engine import candles, setups, opening_range, time_machine, size_position

router = APIRouter(prefix='/v1/trading')
log = logging.getLogger('gainbud.trading')

class Analysis(BaseModel):
    symbol: str = Field(pattern=r'^[A-Z0-9&.-]{1,25}\.NS$')
    momentum: float = Field(default=3, ge=0, le=50)
    oversold: float = Field(default=30, ge=5, le=50)
    range: Literal['1d','5d','1mo','3mo','6mo','1y','5y'] = '6mo'

class Simulation(Analysis):
    entry: float = Field(gt=0, le=1e7)
    stop: float = Field(gt=0, le=1e7)
    target: float = Field(gt=0, le=1e7)
    seed: int = Field(default=19, ge=0, le=2147483647)
    paths: int = Field(default=1000, ge=100, le=5000)
    horizon: int = Field(default=10, ge=1, le=30)
    costsBps: float = Field(default=10, ge=0, le=200)
    cutoff: int | None = Field(default=None, ge=1)

class Risk(BaseModel):
    capital: float = Field(gt=0, le=1e10)
    riskPct: float = Field(default=1, gt=0, le=10)
    entry: float = Field(gt=0, le=1e7)
    stop: float = Field(gt=0, le=1e7)
    target: float = Field(gt=0, le=1e7)
    allocationPct: float = Field(default=25, gt=0, le=100)
    costsBps: float = Field(default=10, ge=0, le=200)

@router.post('/risk')
async def risk(b: Risk):
    try: return size_position(b.capital,b.riskPct,b.entry,b.stop,b.target,b.allocationPct,b.costsBps)
    except ValueError as e: raise HTTPException(422, str(e))

@router.post('/analyze')
async def analyze(b: Analysis):
    try:
        daily, intraday, display = await asyncio.gather(market.quote(b.symbol,'1y'), market.quote(b.symbol,'1d'), market.quote(b.symbol,b.range), return_exceptions=True)
        if isinstance(daily, Exception): raise ValueError('Daily candles unavailable')
        clean = candles(daily['points'])
        result = setups(clean,b.momentum,b.oversold)
        orb = opening_range(candles(intraday['points'],interval=300)) if not isinstance(intraday,Exception) else {'state':'unavailable','reason':'Intraday provider unavailable'}
        from .market_sources import market_status
        try: session = await market_status()
        except Exception: session = {'state':'unknown','message':'Exchange session could not be verified'}
        quote = display if not isinstance(display,Exception) else daily
        if quote.get('currency')!='INR':raise ValueError('NSE quote currency mismatch')
        age = max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(quote['asOf'].replace('Z','+00:00'))).total_seconds())
        return {'symbol':b.symbol,'quote':quote,'technical':result,'openingRange':orb,'session':session,'freshness':{'ageSeconds':round(age),'stale':age>1200,'realtime':False},'retrievedAt':datetime.now(timezone.utc).isoformat(),'engine':'gb-technical-1'}
    except Exception:
        log.warning('trading_analysis_unavailable',extra={'symbol':b.symbol})
        raise HTTPException(503,'Market candles unavailable. No technical signal was invented.')

@router.post('/simulate')
async def simulate(b: Simulation):
    try:
        quote = await market.quote(b.symbol,'5y')
        if quote.get('currency')!='INR':raise ValueError('NSE historical currency mismatch')
        clean = candles(quote['points'], datetime.fromtimestamp(b.cutoff/1000, timezone.utc) if b.cutoff else None)
        result = time_machine(clean,b.entry,b.stop,b.target,b.seed,b.paths,b.horizon,b.costsBps,b.cutoff)
        # Persist the actual input candles with the report, never forecast OHLC.
        history = [r for r in clean if r['time'] <= result['cutoff']][-1300:]
        return {**result,'symbol':b.symbol,'source':quote['source'],'asOf':quote['asOf'],
                'history':history,'name':quote.get('name',b.symbol)}
    except ValueError as e: raise HTTPException(422,str(e))
    except Exception: raise HTTPException(503,'Historical candles unavailable; simulation was not generated.')

@router.get('/news')
async def market_news():
    from .feeds import news
    try:
        rows = await news()
        def classify(title):
            t=title.lower()
            for label,words in [('Results',['results','earnings','profit']),('Corporate action',['dividend','split','buyback']),('Regulation',['sebi','rbi','regulation']),('IPO',['ipo','listing']),('Macro',['inflation','gdp','rates'])]:
                if any(w in t for w in words): return label
            return 'Market news'
        return {'items':[{**r,'classification':classify(r['title'])} for r in rows],'classificationMethod':'Headline keyword classification; not sentiment or investment advice.'}
    except Exception: raise HTTPException(503,'Publisher headlines are unavailable.')
