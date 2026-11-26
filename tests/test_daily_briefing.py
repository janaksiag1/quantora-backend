from app.daily_briefing import build_briefing

def test_missing_quotes_do_not_create_positive_market_claims():
    result=build_briefing([])
    assert not result['available']
    assert 'positive' not in result['script']
    assert result['sources']==[]

def test_snapshot_retains_negative_move_and_source_timestamp():
    result=build_briefing([{'symbol':'^NSEI','price':25000,'changePercent':-1.2,'asOf':'2026-11-20T10:00:00Z','source':'test-only'}])
    assert result['available']
    assert '-1.20' in result['script'] and '2026-11-20T10:00:00Z' in result['script']
    assert 'positive structural breadth' not in result['script']
    assert result['sources'][0]['source']=='test-only'

def test_invalid_or_undated_quote_cannot_be_a_spoken_fact():
    assert not build_briefing([{'symbol':'^NSEI','price':float('nan'),'asOf':'today'},{'symbol':'^BSESN','price':25000}])['available']
