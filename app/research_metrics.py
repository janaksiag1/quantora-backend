"""Arithmetic from published observations, never model-generated profit forecasts."""
import math,re

async def listing_outcomes(evidence):
    """Only matched, dated official records with an unambiguous issue price."""
    from datetime import datetime,timezone,timedelta
    import httpx
    out=[];seen=set()
    for row in evidence.get('officialIssues',[]):
        raw=str(row.get('priceBand') or '').strip().replace(',','')
        if not re.fullmatch(r'(?:Rs\.?\s*|₹\s*)?\d+(?:\.\d+)?',raw):continue
        try:
            date=datetime.strptime(row.get('listingDate') or '','%d-%b-%Y').replace(tzinfo=timezone(timedelta(hours=5,minutes=30)))
            if not 0<=(datetime.now(timezone.utc)-date).days<=365:continue
        except (ValueError,TypeError):continue
        symbol=str(row.get('symbol',''))+('.BO' if row.get('exchange')=='BSE' else '.NS')
        if symbol in seen:continue
        seen.add(symbol)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r=await client.get('https://query1.finance.yahoo.com/v8/finance/chart/'+symbol,params={'period1':int(date.timestamp()),'period2':int((date+timedelta(days=5)).timestamp()),'interval':'1d'},headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status()
            data=r.json()['chart']['result'][0];q=data['indicators']['quote'][0]
            observation=next((i for i,t in enumerate(data.get('timestamp',[])) if q['close'][i] is not None and date.timestamp()<=t<=(date+timedelta(days=3)).timestamp()),None)
            if observation is None:continue
            issue=number(raw);close=float(q['close'][observation])
            if not issue or issue<=0 or not math.isfinite(close):continue
            out.append({'symbol':symbol,'issuePrice':issue,'firstClose':round(close,2),'observedGainPercent':round((close/issue-1)*100,2),'date':datetime.fromtimestamp(data['timestamp'][observation],date.tzinfo).isoformat(),'source':'https://finance.yahoo.com/quote/'+symbol+'/history/','officialSource':row.get('source'),'basis':'First available close within three days of the official listing date, compared with the published issue price. Not an executed trade or future forecast.'})
        except Exception:continue
        if len(out)>=3:break
    return out

def number(value):
    if value is None:return None
    raw=str(value).replace(',','')
    match=re.search(r'-?\d+(?:\.\d+)?',raw)
    if not match:return None
    n=float(match[0])
    return n if math.isfinite(n) else None

def history_summary(points):
    valid=[p for p in points if isinstance(p.get('close'),(int,float)) and math.isfinite(p['close']) and p['close']>0]
    if len(valid)<2:return None
    closes=[p['close'] for p in valid];peak=closes[0];drawdown=0
    for close in closes:peak=max(peak,close);drawdown=min(drawdown,(close/peak-1)*100)
    return {'observations':len(valid),'from':valid[0]['time'],'to':valid[-1]['time'],'observedReturn':round((closes[-1]/closes[0]-1)*100,2),'maxObservedDrawdown':round(drawdown,2),'lowClose':min(closes),'highClose':max(closes),'basis':'Available observed closing prices/NAV only; not a strategy backtest or expected future return.'}

def research_metrics(evidence,module):
    result={'module':module,'method':'Arithmetic on retrieved source observations. Scenarios are not forecasts. Fees and taxes excluded.'}
    if module=='ipo':
        matches=evidence.get('gmp',[])
        # Multiple matched issuers are ambiguous; never average unrelated companies.
        if len(matches)==1:
            row=matches[0];price=number(row.get('price'));lot=number(row.get('lot'));gmp=number(row.get('gmp'))
            if price and price>0 and lot and lot>0 and lot.is_integer():
                cost=round(price*lot,2)
                result['lot']={'shares':int(lot),'issuePrice':price,'applicationAmount':cost,'source':row.get('source'),'publisherUpdated':row.get('updated'),'basis':'Publisher issue price; verify the final offer price and minimum application lots in the offer document. One lot may not be the minimum application.'}
                result['lot']['scenarios']=[{'label':'Price falls 20%','listingPrice':round(price*.8,2),'grossProfit':round(-cost*.2,2),'returnPercent':-20},{'label':'Price falls 10%','listingPrice':round(price*.9,2),'grossProfit':round(-cost*.1,2),'returnPercent':-10},{'label':'At issue price','listingPrice':price,'grossProfit':0,'returnPercent':0}]
                if gmp is not None:
                    result['lot']['scenarios'].append({'label':'Publisher GMP indication (unofficial)','listingPrice':round(price+gmp,2),'grossProfit':round(gmp*lot,2),'returnPercent':round(gmp/price*100,2)})
        result['averageProfit']=None
        result['averageProfitReason']='No verified, comparable listing-day outcome sample was supplied. An average profit is not estimated from GMP.'
        result['priorIssues']=[{k:r.get(k) for k in ['name','symbol','opens','closes','listingDate','priceBand','subscription','source']} for r in evidence.get('officialIssues',[]) if r.get('listingDate')][:8]
    points=[]
    if evidence.get('quotes'):points=evidence['quotes'][0].get('points',[])
    if evidence.get('fund'):
        from datetime import datetime
        for row in reversed(evidence['fund'].get('data',[])):
            try:points.append({'time':int(datetime.strptime(row['date'],'%d-%m-%Y').timestamp()*1000),'close':float(row['nav'])})
            except (ValueError,KeyError,TypeError):continue
    summary=evidence.get('quotes',[{}])[0].get('historicalSummary') if evidence.get('quotes') else None
    summary=summary or history_summary(points)
    if summary:result['history']=summary
    return result
