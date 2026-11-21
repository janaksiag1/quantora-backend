from datetime import datetime, timedelta, timezone
from app.source_research import lookup_query, select_listing
from app.question_answer import answer_question

def test_price_words_do_not_become_company_names():
    assert lookup_query('Jio stock todays highest') == 'jio'
    assert lookup_query('TCS stock current price') == 'tcs'

def test_bare_brand_is_not_silently_resolved_to_another_company():
    symbol, options = select_listing('jio', [{'name':'Jio Financial Services Limited','symbol':'JIOFIN.NS'}])
    assert symbol is None and options
    answer=answer_question('Jio stock todays highest',{'identityNeedsClarification':True,'listingCandidates':options},'stocks','Janak')
    assert 'which exact company' in answer and 'JIOFIN.NS' in answer
    assert '₹' not in answer

def test_full_company_and_exact_ticker_resolve_but_other_bls_entities_do_not():
    rows=[{'name':'BLS International Services','symbol':'BLS.NS'},{'name':'BLS Polymers Limited','symbol':'BLSPOLY.NS'}]
    assert select_listing('bls polymer',rows)[0]=='BLSPOLY.NS'
    assert select_listing('BLS',rows)[0]=='BLS.NS'
    assert select_listing('BLSPOLY.NS',rows)[0]=='BLSPOLY.NS'
    assert select_listing('jio financial',[{'name':'Jio Financial Services Limited','symbol':'JIOFIN.NS'}])[0]=='JIOFIN.NS'

def fixture(day=0):
    at=datetime.now(timezone(timedelta(hours=5,minutes=30)))-timedelta(days=day)
    return {'intraday':{'name':'TEST ONLY','symbol':'FIXTURE.NS','price':105,'currency':'INR','source':'TEST FIXTURE','asOf':at.isoformat(),'points':[{'time':at.timestamp()*1000,'high':109,'low':98},{'time':at.timestamp()*1000,'high':111,'low':99}]}}

def test_today_high_and_low_use_candle_extrema_not_close_or_profit():
    assert '₹111.00' in answer_question('Today highest kitna?',fixture(),'stocks','Janak')
    assert '₹98.00' in answer_question('Today lowest?',fixture(),'stocks','Janak')
    assert '₹105.00' in answer_question('Current price?',fixture(),'stocks','Janak')

def test_stale_candles_are_not_called_todays_high():
    answer=answer_question('Todays highest?',fixture(1),'stocks','Janak')
    assert "today's high is not available" in answer
    assert '₹111' not in answer

def test_high_risk_and_latest_earnings_are_not_price_intents():
    assert answer_question('Explain high risk business',fixture(),'stocks','Janak') is None
    assert answer_question('Latest earnings details',fixture(),'stocks','Janak') is None

def test_chat_clarifies_identity_without_spending_a_model_request(monkeypatch):
    import app.source_research as sources
    from app.providers import ai
    from app.main import app
    from app.config import settings
    from pydantic import SecretStr
    from fastapi.testclient import TestClient
    monkeypatch.setattr(settings,'internal_api_token',SecretStr('fixture-private-token'))
    observed=[]
    async def collect(prompt,symbol,history,**kwargs):
        observed.append((prompt,kwargs.get('asset_name')))
        return {'identityNeedsClarification':True,'listingCandidates':[{'name':'Fixture Financial','symbol':'FIXTURE.NS'}],'retrievedAt':'2026-11-17T00:00:00Z','module':'stocks'}
    async def generate(*a,**k):raise AssertionError('Ambiguous identities must not reach the language model')
    monkeypatch.setattr(sources,'collect_sources',collect)
    monkeypatch.setattr(ai,'generate',generate)
    with TestClient(app) as client:
        result=client.post('/v1/chat',json={'prompt':'Jio stock todays highest','assetName':'Custom research'},headers={'X-Internal-Token':'fixture-private-token'})
    assert result.status_code==200
    assert 'which exact company' in result.json()['answer']
    assert observed==[('Jio stock todays highest','Custom research')]

def test_reported_business_profit_is_not_treated_as_future_trading_profit():
    assert answer_question('What was the company net profit in FY26?',{'metrics':{}},'stocks','Janak') is None
    assert answer_question('Latest company earnings and profit margin',fixture(),'stocks','Janak') is None
    assert answer_question('52-week highest price',fixture(),'stocks','Janak') is None

def test_missing_current_session_does_not_fall_into_generic_profit_answer():
    answer=answer_question('Aaj high kitna?',{'metrics':{}},'stocks','Janak')
    assert 'intraday candles were not retrieved' in answer
    assert 'future-profit' not in answer
