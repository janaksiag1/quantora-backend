"""Question-level regression fixtures; no network calls, generated prices or LLM spending."""
from datetime import datetime, timezone, timedelta
import asyncio
import pytest
from app.question_answer import answer_question, price_answer
from app import source_research, market_sources

@pytest.mark.parametrize('prompt', ['What is an IPO?', 'Can you tell me what is IPO?', 'IPO kya hai?'])
def test_definition_is_direct_without_issuer_or_llm(monkeypatch,prompt):
    async def forbidden(*args,**kwargs): raise AssertionError('No company lookup for a definition')
    monkeypatch.setattr(source_research,'search_assets',forbidden)
    evidence=asyncio.run(source_research.collect_sources(prompt))
    answer=answer_question(prompt,evidence,'ipo','Janak')
    assert 'Initial Public Offering' in answer
    assert 'guarantee' in answer
    assert len(answer)<1100

def test_jio_ambiguity_never_substitutes_another_listing():
    answer=answer_question('Jio stock today highest',{'identityNeedsClarification':True,'listingCandidates':[{'name':'Jio Financial Services','symbol':'JIOFIN.NS'},{'name':'Jio Platforms','symbol':'UNLISTED'}]},'stocks','Janak')
    assert 'choose' in answer
    assert '₹' not in answer

@pytest.mark.parametrize('question',['How much profit will TCS give?','What is the 52-week high?','TCS target kitna hoga?'])
def test_missing_financials_never_create_ranges_targets_or_returns(question):
    evidence={'intraday':{'price':100,'currency':'INR','name':'TCS'}}
    assert answer_question(question,evidence,'stocks','Janak') is None

@pytest.mark.parametrize('field,expected',[('highest','104.00'),('lowest','95.00')])
def test_today_session_extrema_use_candles_and_timestamp(field,expected):
    now=datetime.now(timezone.utc);t=now.timestamp()*1000
    quote={'price':101,'name':'Fixture','currency':'INR','source':'fixture-only','asOf':now.isoformat(),'points':[{'time':t,'high':104,'low':96},{'time':t-1000,'high':103,'low':95},{'time':t-86400000,'high':999,'low':1}]}
    answer=price_answer('today '+field,{'intraday':quote},'Janak')
    assert expected in answer and now.isoformat() in answer and 'fixture-only' in answer
    assert '999' not in answer and 'verified market ticks' not in answer

def test_yesterday_candles_cannot_answer_today_high():
    yesterday=(datetime.now(timezone.utc)-timedelta(days=2)).timestamp()*1000
    answer=price_answer('today highest',{'intraday':{'points':[{'time':yesterday,'high':999}], 'name':'Fixture'}},'Janak')
    assert 'not available' in answer and '999' not in answer

@pytest.mark.parametrize('price',[float('nan'),float('inf'),-1,0,True,None])
def test_non_finite_and_invalid_price_is_not_quoted(price):
    assert price_answer('latest price',{'intraday':{'price':price}},'Janak') is None

def test_closed_message_wins_over_contradictory_exchange_flag(monkeypatch):
    async def raw(*args): return {'marketState':[{'market':'Capital Market','marketStatus':'Open','marketStatusMessage':'Normal Market has Closed'}]}
    monkeypatch.setattr(market_sources,'get_json',raw)
    monkeypatch.setattr(market_sources,'CACHE',{})
    assert asyncio.run(market_sources.market_status())['state']=='closed'
