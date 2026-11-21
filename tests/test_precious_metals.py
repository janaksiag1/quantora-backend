import asyncio
from datetime import datetime,timezone
import pytest
from app import precious_metals as m


def raw(symbol,**patch):
    return {'symbol':symbol,'currency':'INR','price':3110.34768,'exchangeRate':80,'updatedAt':datetime.now(timezone.utc).isoformat(),**patch}

def test_weight_conversion_uses_troy_ounces_not_regular_ounces():
    gold=m.normalize_primary('XAU',raw('XAU'))
    silver=m.normalize_primary('XAG',raw('XAG'))
    assert gold['priceInr']==pytest.approx(1000)
    assert silver['priceInr']==pytest.approx(100000)
    assert gold['unitInr']=='10 g' and silver['unitInr']=='1 kg'
    assert gold['priceUsdOz']==pytest.approx(3110.34768/80)

def test_wrong_currency_identity_and_invalid_prices_are_never_relabelled():
    for patch in [{'currency':'USD'},{'symbol':'XAG'},{'price':0},{'price':-1},{'price':True},{'price':float('nan')},{'updatedAt':None},{'updatedAt':'2026-01-01'}]:
        with pytest.raises((ValueError,TypeError)):m.normalize_primary('XAU',raw('XAU',**patch))
    no_fx=m.normalize_primary('XAU',raw('XAU',exchangeRate=0))
    assert no_fx['priceInr']>0 and no_fx['priceUsdOz'] is None

def test_backup_requires_explicit_unit_and_currency():
    backup={'xau':{'price':3110.34768,'currency':'INR','unit':'troy_oz'},'fx_rate':80,'spot_usd_oz':38.879346,'silver_usd_oz':10,'updated_at':datetime.now(timezone.utc).isoformat()}
    assert m.normalize_backup('XAU',backup)['priceInr']==pytest.approx(1000)
    assert m.normalize_backup('XAG',backup)['priceInr']==pytest.approx(800/m.TROY_OUNCE_GRAMS*1000)
    backup['xau']['unit']='gram'
    with pytest.raises(ValueError):m.normalize_backup('XAU',backup)

def test_partial_failure_uses_backup_and_cache_deduplicates_requests(monkeypatch):
    monkeypatch.setattr(m,'CACHE',{});monkeypatch.setattr(m,'LAST_GOOD',{});monkeypatch.setattr(m,'LOCK',asyncio.Lock())
    calls=[]
    async def fetch(url):
        calls.append(url)
        if '/XAU/' in url:return raw('XAU')
        if '/XAG/' in url:raise ConnectionError('temporary')
        return {'xau':{'price':3110.34768,'currency':'INR','unit':'troy_oz'},'fx_rate':80,'spot_usd_oz':38.879346,'silver_usd_oz':10,'updated_at':datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(m,'get_json',fetch)
    async def run():return await asyncio.gather(m.metals_snapshot(),m.metals_snapshot())
    results=asyncio.run(run())
    assert len(calls)==3
    assert results[0]==results[1]
    assert [r['source'] for r in results[0]['items']]==['Gold API','XAUS']

def test_outage_retains_real_timestamp_and_marks_stale_then_expires(monkeypatch):
    import time
    saved=m.normalize_primary('XAU',raw('XAU'))
    monkeypatch.setattr(m,'CACHE',{});monkeypatch.setattr(m,'LOCK',asyncio.Lock());monkeypatch.setattr(m,'LAST_GOOD',{'XAU':(time.monotonic(),saved)})
    async def fail(url):raise ConnectionError('outage')
    monkeypatch.setattr(m,'get_json',fail)
    snapshot=asyncio.run(m.metals_snapshot());gold,silver=snapshot['items']
    assert gold['stale'] and gold['retained'] and gold['asOf']==saved['asOf']
    assert gold['priceInr']==saved['priceInr']
    assert silver.get('priceInr') is None and silver['error']
    m.CACHE.clear();m.LAST_GOOD['XAU']=(time.monotonic()-901,saved)
    expired=asyncio.run(m.metals_snapshot())['items'][0]
    assert expired.get('priceInr') is None and expired['error']
