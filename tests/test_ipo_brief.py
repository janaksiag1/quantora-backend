import asyncio,json
from app import ipo_brief

def test_quick_review_uses_one_analyst_and_excludes_unverified_financial_claims(monkeypatch):
    calls=[]
    async def sources(*args,**kwargs):return {'retrievedAt':'2026-11-01T00:00:00Z','sources':[{'id':'S1','url':'https://www.nseindia.com/','title':'Issue facts'},{'id':'S2','url':'https://www.investorgain.com/','title':'Publisher'}],'officialIssues':[{'name':'Test IPO','opens':'01-Nov-2026','closes':'03-Nov-2026','subscription':1.5}]}
    async def analyst(prompt,role):
        calls.append(role)
        return {'argument':json.dumps({'classification':'Watch','summary':'Guaranteed profit of 99 percent','positives':['Revenue grew 12345 percent [S1]'],'risks':['Issue information is incomplete.'],'missingEvidence':[],'nextSteps':['Confirm official documents.']}),'model':'test'}
    monkeypatch.setattr(ipo_brief,'collect_sources',sources)
    monkeypatch.setattr(ipo_brief.ai,'generate_for_agent',analyst)
    result=asyncio.run(ipo_brief.ipo_brief('Test IPO','Test owner'))
    assert calls==['nova']
    assert '12345' not in json.dumps(result['report']['positives'])
    assert 'Guaranteed' not in result['report']['summary']
    assert result['report']['summary'].startswith('Test owner,')
    assert result['checks']['excludedNarrativeClaims']>0
    assert any('official offer document' in gap for gap in result['report']['missingEvidence'])
