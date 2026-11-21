import asyncio
from app import market_sources as sources


def test_etf_directory_filters_only_official_identities(monkeypatch):
    class Reply:
        text='Symbol,Underlying Asset,SecurityName,ETF Underlying\nNIFTYBEES,Nifty 50,Nippon India ETF Nifty 50 BeES,EQUITY\nGOLDBEES,Gold,Nippon India ETF Gold BeES,COMMODITY\n'
        def raise_for_status(self):pass
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,*args,**kwargs):return Reply()
    monkeypatch.setattr(sources.httpx,'AsyncClient',Client)
    monkeypatch.setattr(sources,'CACHE',{})
    rows=asyncio.run(sources.etf_directory('gold'))
    assert len(rows)==1 and rows[0]['symbol']=='GOLDBEES.NS'
    assert rows[0]['type']=='ETF' and 'price' not in rows[0]
    assert rows[0]['benchmark']=='Gold' and rows[0]['category']=='COMMODITY'


def test_etf_fallback_does_not_leak_equity_companies(monkeypatch):
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):raise ValueError('Source down')
        async def __aexit__(self,*args):pass
    async def search(*args,**kwargs):return {'quotes':[{'symbol':'GOLDBEES.NS','shortname':'Gold ETF','quoteType':'ETF'},{'symbol':'RELIANCE.NS','quoteType':'EQUITY'}]}
    monkeypatch.setattr(sources.httpx,'AsyncClient',Client)
    monkeypatch.setattr(sources,'get_json',search)
    monkeypatch.setattr(sources,'CACHE',{})
    rows=asyncio.run(sources.etf_directory())
    assert [r['symbol'] for r in rows]==['GOLDBEES.NS']

