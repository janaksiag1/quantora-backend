import asyncio
from app import ipo

def test_issue_value_is_not_misreported_as_number_of_shares(monkeypatch):
    class Response:
        def raise_for_status(self):pass
        def json(self):return [{'symbol':'QAISSUE','companyName':'QA issuer','category':'Total','issueSize':'500 crore','issuePrice':82,'noOfsharesBid':0}]
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,*args,**kwargs):return Response()
    monkeypatch.setattr(ipo.httpx,'AsyncClient',Client)
    monkeypatch.setattr(ipo,'cache',{})
    result=asyncio.run(ipo.get_issues())['issues'][0]
    assert result['offeredShares'] is None
    assert result['sharesBid']==0
    assert result['issueSize']=='500 crore'
    assert result['priceBand']=='82'
