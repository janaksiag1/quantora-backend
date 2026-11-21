import asyncio,time
from app import feeds

def test_fund_directory_deduplicates_codes_without_merging_plan_options(monkeypatch):
    rows=[{'schemeCode':100001,'schemeName':'Example Direct Growth'}, {'schemeCode':100001,'schemeName':'Example Direct Growth'}, {'schemeCode':100002,'schemeName':'Example Regular Growth'}, {'schemeCode':100003,'schemeName':'Example Direct Growth'}]
    monkeypatch.setattr(feeds,'_fund_directory',(time.monotonic(),rows))
    result=asyncio.run(feeds.search_funds('growth'))
    assert [r['symbol'] for r in result]==['100001','100002','100003']
    direct=asyncio.run(feeds.search_funds('direct growth'))
    assert [r['symbol'] for r in direct]==['100001','100003']
