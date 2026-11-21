import asyncio
import httpx
import app.market_sources as sources

def test_stock_directory_survives_exchange_cloud_block(monkeypatch):
    sources.CACHE.clear()
    monkeypatch.setattr(sources.time,'monotonic',lambda:0.5)
    real_client=httpx.AsyncClient
    def handle(request):
        if request.url.host=='nsearchives.nseindia.com':return httpx.Response(403)
        assert request.headers['user-agent']=='Mozilla/5.0'
        return httpx.Response(200,json={'quotes':[{'symbol':'TEST.NS','shortname':'Test only issuer','quoteType':'EQUITY','exchDisp':'NSE'}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handle),**kwargs))
    result=asyncio.run(sources.stock_directory())
    assert len(result)==1 and result[0]['symbol']=='TEST.NS'
    assert 'Yahoo' in result[0]['source']
    sources.CACHE.clear()

def test_gmp_dates_do_not_include_historical_gmp_annotation(monkeypatch):
    sources.CACHE.clear()
    real_client=httpx.AsyncClient
    html='<table><tr>'+''.join('<td>'+v+'</td>' for v in ['<a href="/gmp/test/1/">Test issuer IPO</a> NSE SME C','₹ 12 (10.00%) 8 ↓ / 14 ↑','rating','2x','120','100 Cr','100','27-Oct GMP: 10','29-Oct GMP: 11','30-Oct','3-Nov','31-Oct 10:00'])+'</tr></table>'
    def handle(request):
        return httpx.Response(200,text='User-agent: *\nAllow: /' if request.url.path=='/robots.txt' else html)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handle),**kwargs))
    result=asyncio.run(sources.gmp_feed())['items'][0]
    assert result['name']=='Test issuer IPO'
    assert result['segment']=='SME'
    assert result['gmp']=='₹12 (10.00%)'
    assert result['opens']=='27-Oct' and result['closes']=='29-Oct'
    sources.CACHE.clear()
