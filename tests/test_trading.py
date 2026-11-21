"""Deterministic synthetic fixtures are tests only, never production market data."""
import random
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
import pytest
from app.trading_engine import candles,rsi,setups,opening_range,size_position,time_machine,outcome,IST
from app.trading import router
from fastapi import FastAPI

def daily(n=100):
    rng=random.Random(7);price=100;out=[]
    for i in range(n):
        open_=price;price*=1+rng.uniform(-.025,.03)
        out.append({'time':int((datetime(2024,1,1,tzinfo=IST)+timedelta(days=i)).timestamp()*1000),'open':open_,'high':max(open_,price)*1.01,'low':min(open_,price)*.99,'close':price,'volume':1000})
    return out

def test_rsi_flat_and_increasing():
    assert rsi([100]*30)==50
    assert rsi(list(range(1,40)))==100
    assert rsi([2]*4) is None

def test_sizing_costs_and_allocation():
    result=size_position(100000,1,100,95,110,25,10)
    assert result['quantity']==192
    assert result['estimatedLoss']<=1000
    assert result['capitalRequired']<=25000
    assert size_position(1,1,100,95,110)['quantity']==0
    with pytest.raises(ValueError):size_position(1,1,100,105,110)
    with pytest.raises(ValueError):size_position(float('nan'),1,100,95,110)

def test_candles_drop_invalid_future_partial_and_deduplicate():
    rows=daily(2);bad={**rows[0],'high':1};future={**rows[0],'time':4102444800000}
    result=candles([rows[0],rows[0],bad,rows[1],future],datetime(2024,1,2,8,tzinfo=IST))
    assert len(result)==1
    assert result[0]['time']==rows[0]['time']
    assert candles([{**rows[0],'volume':None}],datetime(2024,1,3,tzinfo=IST))[0]['volume'] is None

def test_orb_requires_complete_grid_and_excludes_partial():
    start=datetime(2026,11,12,9,15,tzinfo=IST)
    rows=[{'time':int((start+timedelta(minutes=5*i)).timestamp()*1000),'open':100,'high':101+i,'low':99,'close':100+i,'volume':1} for i in range(5)]
    assert opening_range(rows[:3])['state']=='unavailable'
    assert opening_range(rows)['state']=='confirmed'
    assert opening_range([rows[0],*rows[2:]])['state']=='unavailable'
    complete=candles(rows,start+timedelta(minutes=22),interval=300)
    assert len(complete)==4

def test_setup_minimum_and_momentum():
    assert setups(daily(10))['state']=='unavailable'
    rows=daily(50)
    for i in range(6):rows[-6+i]['close']=100+i*4
    assert 'momentum' in setups(rows)['signals']

def test_stop_first_and_gap_loss():
    assert outcome([{'open':100,'low':90,'high':120,'close':105}],100,95,110,10)==(95,'stop')
    assert outcome([{'open':80,'low':79,'high':100,'close':90}],100,95,110,10)==(80,'gap_stop')
    assert outcome([{'open':115,'low':90,'high':120,'close':100}],100,95,110,10)==(110,'target')

def test_simulation_reproducible_no_lookahead():
    rows=daily(150);cutoff=rows[99]['time']
    first=time_machine(rows,100,95,110,19,200,10,10,cutoff)
    assert first==time_machine(rows[:100],100,95,110,19,200,10,10,cutoff)
    assert first==time_machine(rows,100,95,110,19,200,10,10,cutoff)
    assert first['dataHash']!=time_machine(rows,100,95,110,19,200,10,10)['dataHash']
    assert first['samplePaths']!=time_machine(rows,100,95,110,20,200,10,10,cutoff)['samplePaths']
    assert first['p05']<=first['median']<=first['p95']
    assert all(t['signalAt']<t['entryAt']<=cutoff for t in first['historicalTrades'])

def test_replay_never_enters_signal_bar():
    rows=daily(150)
    result=time_machine(rows,100,95,110,paths=100)
    for trade in result['historicalTrades']:
        index=next(i for i,r in enumerate(rows) if r['time']==trade['signalAt'])
        assert rows[index+1]['time']==trade['entryAt']
        assert rows[index]['close']>max(r['close'] for r in rows[index-20:index])

def test_api_validation_and_risk():
    app=FastAPI();app.include_router(router);client=TestClient(app)
    assert client.post('/v1/trading/analyze',json={'symbol':'http://localhost'}).status_code==422
    assert client.post('/v1/trading/simulate',json={'symbol':'TCS.NS','entry':100,'stop':95,'target':110,'paths':999999}).status_code==422
    assert client.post('/v1/trading/risk',json={'capital':100000,'entry':100,'stop':95,'target':110}).json()['quantity']==192

def test_api_provider_failure_no_fake_analysis(monkeypatch):
    from app.providers import market
    async def fail(*args,**kwargs):raise ValueError('offline')
    monkeypatch.setattr(market,'quote',fail)
    app=FastAPI();app.include_router(router)
    r=TestClient(app).post('/v1/trading/analyze',json={'symbol':'TCS.NS'})
    assert r.status_code==503 and 'quote' not in r.json()

def test_simulation_chart_candles_preserve_source_and_cutoff(monkeypatch):
    from app.providers import market
    rows = daily(160)
    async def source(*args, **kwargs):
        return {'currency':'INR','points':rows,'source':'fixture','asOf':'2024-06-01T10:00:00Z','name':'Fixture company'}
    monkeypatch.setattr(market,'quote',source)
    app=FastAPI();app.include_router(router)
    cutoff=rows[99]['time'] + int(15.5*3600000)
    response=TestClient(app).post('/v1/trading/simulate',json={'symbol':'TCS.NS','entry':100,'stop':95,'target':110,'paths':100,'cutoff':cutoff})
    assert response.status_code==200
    data=response.json()
    assert data['history']==rows[:100]
    assert data['history'][-1]['time']==rows[99]['time']
    assert data['sampleBars']==100
    assert data['name']=='Fixture company'
    assert len(data['samplePaths'])==12

def test_intraday_cutoff_cannot_see_same_day_close():
    rows=daily(160)
    start=rows[99]['time']
    before=time_machine(rows,100,95,110,paths=100,as_of=start+9*3600000)
    at_close=time_machine(rows,100,95,110,paths=100,as_of=start+int(15.5*3600000))
    assert before['sampleBars']==99
    assert at_close['sampleBars']==100
    assert before['dataHash']!=at_close['dataHash']

def test_wrong_currency_never_reaches_paper_research(monkeypatch):
    from app.providers import market
    async def wrong(*args,**kwargs):return {'currency':'USD','points':daily(100)}
    monkeypatch.setattr(market,'quote',wrong)
    import app.market_sources as sources
    async def status():return {'state':'closed'}
    monkeypatch.setattr(sources,'market_status',status)
    app=FastAPI();app.include_router(router)
    assert TestClient(app).post('/v1/trading/analyze',json={'symbol':'TCS.NS'}).status_code==503

def test_regulator_pipeline_parser():
    from app.ipo_filings import parse_filings
    html='<table id="sample_1"><tbody><tr><td>Nov 13, 2026</td><td><a href="https://www.sebi.gov.in/filings/example.html">Example Limited - DRHP</a></td></tr><tr><td>Nov 12</td><td><a href="http://evil.test/a">Evil</a></td></tr></tbody></table>'
    rows=parse_filings(html)
    assert len(rows)==1 and rows[0]['opens'] is None and rows[0]['status']=='Filed · dates TBA'

def test_gmp_missing_percentage_never_prints_placeholder():
    from app.market_sources import format_gmp
    assert format_gmp('₹12.5 (-%)')=='₹12.5'
    assert format_gmp('₹12.5 (10.25%)')=='₹12.5 (10.25%)'
    assert format_gmp('Not published')=='Not published'
