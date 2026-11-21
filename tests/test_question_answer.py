from app.question_answer import answer_question
from app.research_metrics import research_metrics

def test_profit_answer_uses_exact_matched_lot_and_shows_downside():
    e={'gmp':[{'price':'100','lot':'1200','gmp':'-5'}]}
    e['metrics']=research_metrics(e,'ipo')
    a=answer_question('Kitna profit dega ye?',e,'ipo','Aarav')
    assert '₹120,000.00' in a and '₹-6,000.00 gross loss' in a
    assert '₹24,000.00 gross loss' in a
    assert 'not an expected return' in a

def test_profit_question_without_lot_does_not_invent_a_target():
    a=answer_question('Expected profit?',{'metrics':{}},'ipo','Aarav')
    assert 'no reliable future-profit' in a and 'needed' in a
    assert '₹' not in a

def test_changed_question_has_different_answer_and_preserves_context():
    e={'officialIssues':[{'name':'Issuer','opens':'1-Nov','closes':'3-Nov','subscription':2.5}], 'metrics':{}}
    assert 'bidding from' in answer_question('When does it close?',e,'ipo','Aarav')
    assert 'future-profit' in answer_question('How much profit?',e,'ipo','Aarav')
    assert answer_question('Review business risks',e,'ipo','Aarav') is None

def test_history_is_not_a_future_profit_forecast():
    a=answer_question('Will I gain 20 percent?',{'metrics':{'history':{'observedReturn':3.4,'observations':90}}},'stocks','Aarav')
    assert '+3.40%' in a and 'not a forecast' in a
