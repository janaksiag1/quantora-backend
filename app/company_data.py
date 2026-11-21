"""Anonymous public Yahoo session data, with original normalization and bounded caches."""
import asyncio,math,re,time
from datetime import datetime,timezone
import httpx
SESSION={};CACHE={};LIVE={};LOCK=asyncio.Lock()
UA={'User-Agent':'Mozilla/5.0'}
def numeric(value):
    if isinstance(value,dict):value=value.get('raw')
    return float(value) if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) else None
def epoch(value):
    n=numeric(value)
    return datetime.fromtimestamp(n,timezone.utc).isoformat() if n and 0<n<10_000_000_000 else None
async def public_session(force=False):
    async with LOCK:
        if not force and SESSION.get('until',0)>time.monotonic():return SESSION['cookie'],SESSION['crumb']
        async with httpx.AsyncClient(timeout=6,headers=UA) as c:
            await c.get('https://fc.yahoo.com')
            r=await c.get('https://query1.finance.yahoo.com/v1/test/getcrumb');r.raise_for_status()
            crumb=r.text.strip();cookie='; '.join(k+'='+v for k,v in c.cookies.items())
        if not cookie or not re.fullmatch(r'[A-Za-z0-9._~+/=\-]{3,160}',crumb):raise ValueError('Company session unavailable')
        SESSION.update(cookie=cookie,crumb=crumb,until=time.monotonic()+2400)
        return cookie,crumb
async def public_json(path,params):
    for attempt in range(2):
        cookie,crumb=await public_session(force=attempt>0)
        async with httpx.AsyncClient(timeout=7,headers={**UA,'Cookie':cookie}) as c:r=await c.get('https://query1.finance.yahoo.com'+path,params={**params,'crumb':crumb})
        if r.status_code==401 and attempt==0:continue
        r.raise_for_status();return r.json()
    raise ValueError('Company data unavailable')
def normalize_company(symbol,data):
    p=data.get('price',{});s=data.get('summaryDetail',{});k=data.get('defaultKeyStatistics',{});a=data.get('assetProfile',{});f=data.get('financialData',{})
    if p.get('symbol') and p['symbol'].upper()!=symbol.upper():raise ValueError('Company identity mismatch')
    if numeric(p.get('regularMarketPrice')) is None:raise ValueError('Company identity not available')
    dividend=numeric(s.get('dividendYield'))
    extras={key:numeric(origin.get(field)) for key,origin,field in [
        ('fiftyTwoWeekHigh',s,'fiftyTwoWeekHigh'),('fiftyTwoWeekLow',s,'fiftyTwoWeekLow'),('volume',s,'volume'),('averageVolume',s,'averageVolume'),('forwardPE',s,'forwardPE'),('priceToBook',k,'priceToBook'),('totalRevenue',f,'totalRevenue'),('ebitda',f,'ebitda'),('totalCash',f,'totalCash'),('totalDebt',f,'totalDebt'),('freeCashflow',f,'freeCashflow'),('operatingCashflow',f,'operatingCashflow'),('debtToEquityPercent',f,'debtToEquity')]}
    for key in ['profitMargins','operatingMargins','returnOnEquity','returnOnAssets','revenueGrowth','earningsGrowth']:
        value=numeric(f.get(key));extras[key+'Percent']=value*100 if value is not None else None
    annual=[]
    for row in data.get('incomeStatementHistory',{}).get('incomeStatementHistory',[])[:4]:
        end=epoch(row.get('endDate'))
        if end:annual.append({'periodEnd':end,**{key:numeric(row.get(key)) for key in ['totalRevenue','netIncome','operatingIncome']}})
    quarterly=[]
    for row in data.get('incomeStatementHistoryQuarterly',{}).get('incomeStatementHistory',[])[:4]:
        end=epoch(row.get('endDate'))
        if end:quarterly.append({'periodEnd':end,**{key:numeric(row.get(key)) for key in ['totalRevenue','netIncome','operatingIncome']}})
    return {'symbol':symbol,'name':p.get('longName') or p.get('shortName') or symbol,'currency':p.get('currency'),'sector':a.get('sector'),'industry':a.get('industry'),'businessSummary':str(a.get('longBusinessSummary') or '')[:1800],
        'financialCurrency':f.get('financialCurrency'),'website':a.get('website'),'employees':numeric(a.get('fullTimeEmployees')),'country':a.get('country'),'annualStatements':annual,'quarterlyStatements':quarterly,
        'metrics':{**extras,'marketCap':numeric(p.get('marketCap')) if numeric(p.get('marketCap')) is not None else numeric(s.get('marketCap')),'trailingPE':numeric(s.get('trailingPE')),'trailingEPS':numeric(k.get('trailingEps')),'bookValue':numeric(k.get('bookValue')),'dividendYieldPercent':dividend*100 if dividend is not None else None},
        'reportingReference':epoch(k.get('mostRecentQuarter')),'priceAsOf':epoch(p.get('regularMarketTime')),'retrievedAt':datetime.now(timezone.utc).isoformat(),'source':'Yahoo Finance company data · aggregator values; verify filings','url':'https://finance.yahoo.com/quote/'+symbol+'/key-statistics/','note':'TTM/quarterly fields have different reporting periods. Retrieval time is not a financial-statement publication date.'}
async def company(symbol):
    if not re.fullmatch(r'[A-Za-z0-9.&=\-]{1,40}',symbol):raise ValueError('Choose a company ticker')
    old=CACHE.get(symbol)
    if old and time.monotonic()-old[0]<900:return old[1]
    async with asyncio.timeout(18):
        try:raw=await public_json('/v10/finance/quoteSummary/'+symbol,{'modules':'price,summaryDetail,defaultKeyStatistics,assetProfile,financialData,incomeStatementHistory,incomeStatementHistoryQuarterly'})
        except (httpx.HTTPError,ValueError):raw=await public_json('/v10/finance/quoteSummary/'+symbol,{'modules':'price,summaryDetail,defaultKeyStatistics,assetProfile'})
    rows=raw.get('quoteSummary',{}).get('result') or []
    if not rows:raise ValueError('Company fundamentals not published for this ticker')
    result=normalize_company(symbol,rows[0]);CACHE[symbol]=(time.monotonic(),result)
    return result
async def quote_batch(symbols):
    selected=[s for s in symbols[:12] if re.fullmatch(r'[A-Za-z0-9^.&=\-]{1,40}',s)]
    missing=[s for s in selected if s not in LIVE or time.monotonic()-LIVE[s][0]>5]
    if missing:
        async with asyncio.timeout(12):raw=await public_json('/v7/finance/quote',{'symbols':','.join(missing)})
        for q in raw.get('quoteResponse',{}).get('result',[]):
            symbol=q.get('symbol');price=numeric(q.get('regularMarketPrice'));date=epoch(q.get('regularMarketTime'))
            if symbol not in selected or price is None or price<=0 or not date or not q.get('currency'):continue
            LIVE[symbol]=(time.monotonic(),{'symbol':symbol,'name':q.get('longName') or q.get('shortName') or symbol,'price':price,'change':numeric(q.get('regularMarketChangePercent')),'currency':q['currency'],'asOf':date,'source':'Yahoo Finance quote · may be delayed'})
    return {s:LIVE[s][1] for s in selected if s in LIVE and time.monotonic()-LIVE[s][0]<30}
