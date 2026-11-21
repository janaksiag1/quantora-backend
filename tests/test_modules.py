import asyncio,json
import pytest
from app.schemas import DebateRequest
from app.source_research import collect_sources

def test_invalid_module_is_rejected():
    with pytest.raises(ValueError):DebateRequest(module='unknown',subject='Research')

def test_fund_research_uses_nav_not_equity_chart(monkeypatch):
    import app.source_research as sources
    import app.feeds as feeds
    observed=[]
    async def fund(code):
        observed.append(code)
        return {'meta':{'scheme_name':'Test scheme'},'data':[{'date':'30-10-2026','nav':'100'}],'source':'Test fixture'}
    async def no_news(q):return []
    async def forbidden(*args):raise AssertionError('An equity price must not be requested for an AMFI scheme')
    monkeypatch.setattr(feeds,'fund',fund)
    monkeypatch.setattr(sources,'company_news',no_news)
    monkeypatch.setattr(sources.market,'quote',forbidden)
    result=asyncio.run(collect_sources('Test scheme','120503',module='funds'))
    assert observed==['120503']
    assert result['quotes']==[] and result['officialIssues']==[]
    assert result['fund']['source']=='Test fixture'

def test_crypto_evidence_does_not_query_ipo_feed(monkeypatch):
    import app.source_research as sources
    async def quote(symbol,period):
        assert symbol=='BTC-USD'
        assert period=='1y'
        return {'symbol':symbol,'name':'Test Bitcoin','points':[],'source':'Test fixture'}
    async def no_news(q):return []
    async def forbidden(*args):raise AssertionError('IPO feed must not be called for crypto')
    monkeypatch.setattr(sources.market,'quote',quote)
    monkeypatch.setattr(sources,'company_news',no_news)
    monkeypatch.setattr(sources,'get_issues',forbidden)
    result=asyncio.run(collect_sources('Bitcoin','BTC-USD',module='crypto'))
    assert result['quotes'][0]['symbol']=='BTC-USD'
    assert result['officialIssues']==[] and result['gmp']==[]

def test_partial_council_preserves_findings_and_reports_missing_role(monkeypatch):
    import app.research as research
    async def sources(*args,**kwargs):return {'quotes':[],'officialIssues':[],'headlines':[],'sources':[],'retrievedAt':'2026-01-01T00:00:00Z'}
    async def generate(prompt,agent_id):
        if agent_id=='atlas':raise ValueError('Quota unavailable')
        if agent_id=='prism':argument=json.dumps({'classification':'Insufficient evidence','summary':'Test-only report','positives':[],'risks':['Test risk'],'missingEvidence':['Atlas did not respond'],'nextSteps':['Verify source']})
        else:argument='Test-only '+agent_id+' findings'
        return {'argument':argument,'model':'test/'+agent_id,'fallback':False}
    monkeypatch.setattr(research,'collect_sources',sources)
    monkeypatch.setattr(research.ai,'generate_for_agent',generate)
    monkeypatch.setattr(research,'save_research',lambda *args:None)
    async def run():return [json.loads(e) async for e in research.research_events('Test question',None)]
    events=asyncio.run(run());result=events[-1]
    assert result['type']=='complete' and result['result']['partial'] is True
    assert result['result']['rounds'][1] is None
    assert sum(e['type']=='discussion' for e in events)==2
    assert any(e['type']=='agent_error' and e['index']==1 for e in events)
