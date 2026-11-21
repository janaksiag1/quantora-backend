import asyncio,httpx
import app.market_sources as sources
import app.ipo as ipo
def test_closed_status_comes_from_exchange_response(monkeypatch):
    sources.CACHE.clear()
    async def response(url):return {'marketState':[{'market':'Capital Market','marketStatus':'Close','marketStatusMessage':'Market is Closed','tradeDate':'30-Oct-2026 15:30'}]}
    monkeypatch.setattr(sources,'get_json',response)
    assert asyncio.run(sources.market_status())['state']=='closed'
    sources.CACHE.clear()
def test_bidding_flag_is_not_used_to_invent_listing_exchange(monkeypatch):
    ipo.cache.clear();real=httpx.AsyncClient
    row={'symbol':'EXAMPLE','companyName':'Example issuer','isBse':'1','series':'SME','noOfTime':'1.53'}
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=[row])),**kw))
    item=asyncio.run(ipo.get_issues())['issues'][0]
    assert item['exchange']=='NSE feed'
    ipo.cache.clear()
