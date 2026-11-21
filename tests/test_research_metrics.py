from app.research_metrics import research_metrics

def test_ipo_loss_and_gmp_arithmetic_are_separate_from_expected_profit():
    e={'gmp':[{'price':'₹100','lot':'1,200','gmp':'₹-5 (-5%)','source':'publisher'}]}
    r=research_metrics(e,'ipo')
    assert r['lot']['applicationAmount']==120000
    assert r['lot']['scenarios'][-1]['grossProfit']==-6000
    assert r['lot']['scenarios'][0]['grossProfit']==-24000
    assert r['averageProfit'] is None

def test_ambiguous_issuers_do_not_produce_lot_projection():
    assert 'lot' not in research_metrics({'gmp':[{'price':100,'lot':10}]*2},'ipo')

def test_history_computes_actual_drawdown_and_return():
    r=research_metrics({'quotes':[{'points':[{'time':1,'close':100},{'time':2,'close':80},{'time':3,'close':110}]}]},'stocks')
    assert r['history']['maxObservedDrawdown']==-20
    assert r['history']['observedReturn']==10

def test_full_retrieved_window_survives_compact_model_payload():
    from app.research_metrics import history_summary
    full=[{'time':i,'close':100+i} for i in range(250)]
    r=research_metrics({'quotes':[{'points':full[-60:],'historicalSummary':history_summary(full)}]},'stocks')
    assert r['history']['observations']==250 and r['history']['from']==0
