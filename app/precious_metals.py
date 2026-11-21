"""Public spot quotes with explicit weights, currency, provenance and freshness."""
import asyncio
import math
import time
from datetime import datetime, timezone
import httpx

TROY_OUNCE_GRAMS=31.1034768
METALS={'XAU':('Gold',10,'10 g'),'XAG':('Silver',1000,'1 kg')}
CACHE={}
LAST_GOOD={}
LOCK=asyncio.Lock()

def positive(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:raise ValueError('Invalid metal quote')
    return float(value)

def timestamp(value):
    if not isinstance(value,str):raise ValueError('Missing source time')
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None or dt.timestamp()>time.time()+300:raise ValueError('Invalid source time')
    return dt.astimezone(timezone.utc).isoformat()

def quote(symbol,inr_oz,usd_oz,fx,at,source,url):
    name,grams,unit=METALS[symbol]
    at=timestamp(at)
    return {'symbol':symbol,'name':name,'priceInr':positive(inr_oz)*grams/TROY_OUNCE_GRAMS,'unitInr':unit,'priceUsdOz':positive(usd_oz) if usd_oz is not None else None,'fxRate':fx,'asOf':at,'source':source,'sourceUrl':url,'basis':'spot','stale':time.time()-datetime.fromisoformat(at).timestamp()>300}

def normalize_primary(symbol,raw):
    if raw.get('symbol')!=symbol or raw.get('currency')!='INR':raise ValueError('Metal identity or currency mismatch')
    inr=positive(raw.get('price'))
    try:fx=positive(raw.get('exchangeRate'))
    except ValueError:fx=None
    return quote(symbol,inr,inr/fx if fx else None,fx,raw.get('updatedAt'),'Gold API','https://gold-api.com/')

def normalize_backup(symbol,raw):
    xau=raw.get('xau',{})
    if xau.get('currency')!='INR' or xau.get('unit')!='troy_oz':raise ValueError('Backup currency or unit mismatch')
    fx=positive(raw.get('fx_rate'))
    usd=positive(raw.get('spot_usd_oz') if symbol=='XAU' else raw.get('silver_usd_oz'))
    return quote(symbol,positive(xau.get('price')) if symbol=='XAU' else usd*fx,usd,fx,raw.get('updated_at'),'XAUS','https://xaus.com/api/')

async def get_json(url):
    async with httpx.AsyncClient(timeout=10,follow_redirects=True) as client:
        response=await client.get(url,headers={'User-Agent':'GainbudResearch/1.0'})
        response.raise_for_status()
        return response.json()

async def metals_snapshot():
    async with LOCK:
        if CACHE.get('value') and CACHE.get('at',0)>time.monotonic()-5:return CACHE['value']
        results=await asyncio.gather(*(get_json('https://api.gold-api.com/price/'+s+'/INR') for s in METALS),return_exceptions=True)
        items={};missing=[]
        for symbol,raw in zip(METALS,results):
            try:
                if isinstance(raw,Exception):raise raw
                items[symbol]=normalize_primary(symbol,raw)
            except Exception:missing.append(symbol)
        if missing:
            try:
                backup=await get_json('https://xaus.com/api/v1/spot?currency=INR')
                for symbol in missing:
                    try:items[symbol]=normalize_backup(symbol,backup)
                    except Exception:pass
            except Exception:pass
        for symbol in METALS:
            if symbol in items:LAST_GOOD[symbol]=(time.monotonic(),items[symbol].copy())
            elif symbol in LAST_GOOD and time.monotonic()-LAST_GOOD[symbol][0]<900:
                items[symbol]={**LAST_GOOD[symbol][1],'stale':True,'retained':True}
            else:items[symbol]={'symbol':symbol,'name':METALS[symbol][0],'unitInr':METALS[symbol][2],'error':'Spot source temporarily unavailable'}
        value={'items':[items[s] for s in METALS],'retrievedAt':datetime.now(timezone.utc).isoformat(),'refreshSeconds':5,'note':'Indicative international spot values converted to INR and weight. Not a jeweller or MCX quote. Taxes, premiums and making charges excluded. Source times represent feed refresh, not a guaranteed last trade. XAUS may use the same upstream provider.'}
        CACHE.update(at=time.monotonic(),value=value)
        return value
