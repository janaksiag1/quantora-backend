from app.quote_baseline import session_baseline

def test_range_start_is_not_mislabelled_daily_change():
    meta={'regularMarketTime':1763370000,'chartPreviousClose':900,'gmtoffset':19800}
    points=[{'time':(1763370000-86400)*1000,'close':1000},{'time':1763370000*1000,'close':1010}]
    assert session_baseline(meta,points,'1mo')==1000

def test_explicit_previous_close_wins_and_one_day_fallback_is_allowed():
    assert session_baseline({'previousClose':100,'chartPreviousClose':50},[],'1mo')==100
    assert session_baseline({'chartPreviousClose':100},[],'1d')==100
    assert session_baseline({'chartPreviousClose':100},[],'5d') is None
