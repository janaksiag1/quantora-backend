"""Public directories, independent crypto pricing, NAV fallback and unofficial GMP."""
import asyncio, csv, io, json, re, time
from datetime import datetime, timezone
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup

CACHE = {}

def format_gmp(text):
    value=re.search(r'(?:₹|Rs\.?\s*)?\s*([+-]?\d[\d,]*(?:\.\d+)?)',text or '')
    if not value:return 'Not published'
    percent=re.search(r'\(\s*([+-]?\d+(?:\.\d+)?)\s*%\s*\)',text or '')
    return '₹'+value[1]+(' ('+percent[1]+'%)' if percent else '')

async def market_status():
    old=CACHE.get('market-status')
    if old and time.monotonic()-old[0]<60:return old[1]
    raw=await get_json('https://www.nseindia.com/api/marketStatus')
    row=next((r for r in raw.get('marketState',[]) if r.get('market')=='Capital Market'),None)
    if not row:raise ValueError('Exchange status unavailable')
    state=str(row.get('marketStatus','')).lower()
    if re.search(r'closed|halted|suspended|not\s+open',str(row.get('marketStatusMessage','')),re.I):
        state='closed'
    result={'state':'closed' if state in ['close','closed'] else 'open' if state=='open' else 'unknown','message':row.get('marketStatusMessage') or 'See exchange status','tradeDate':row.get('tradeDate'),'source':'https://www.nseindia.com/market-data/market-status','asOf':now()}
    CACHE['market-status']=(time.monotonic(),result)
    return result
def now(): return datetime.now(timezone.utc).isoformat()
async def get_json(url, params=None):
    async with httpx.AsyncClient(timeout=16, follow_redirects=True) as c:
        r = await c.get(url, params=params, headers={'User-Agent':'Mozilla/5.0'})
        r.raise_for_status()
        return r.json()

async def stock_directory(query=''):
    cached=CACHE.get('stocks-fallback',(0,[]))
    if not query and cached[1] and time.monotonic()-cached[0]<300:return cached[1]
    if not CACHE.get('stocks') or time.monotonic()-CACHE['stocks'][0]>86400:
        try:
            async with httpx.AsyncClient(timeout=12) as c:
                r=await c.get('https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv',headers={'User-Agent':'Mozilla/5.0'})
                r.raise_for_status()
            rows=list(csv.DictReader(io.StringIO(r.text)))
            CACHE['stocks']=(time.monotonic(),[{'symbol':x['SYMBOL']+'.NS','name':x['NAME OF COMPANY'],'exchange':'NSE','type':'EQUITY','source':'NSE official equity directory'} for x in rows if x.get('SYMBOL')])
        except Exception:
            # These are discovery queries, not seed financial records. Every
            # displayed identity comes from the live provider response.
            queries=[query] if query else ['Reliance','Tata','HDFC','Infosys','State Bank']
            feeds=await asyncio.gather(*(get_json('https://query1.finance.yahoo.com/v1/finance/search',{'q':q,'quotesCount':12,'newsCount':0}) for q in queries),return_exceptions=True)
            records=[x for data in feeds if isinstance(data,dict) for x in data.get('quotes',[])]
            unique={x['symbol']:x for x in records if x.get('symbol','').endswith(('.NS','.BO')) and x.get('quoteType')=='EQUITY'}
            results=[{'symbol':x['symbol'],'name':x.get('longname') or x.get('shortname') or x['symbol'],'exchange':x.get('exchDisp',''),'type':x.get('quoteType',''),'source':'Yahoo Finance Indian listing discovery · NSE directory unavailable'} for x in unique.values()]
            if not results:raise ValueError('Both listing sources unavailable')
            if not query:CACHE['stocks-fallback']=(time.monotonic(),results)
            return results
    words=query.lower().split()
    return [r for r in CACHE['stocks'][1] if all(w in (r['name']+' '+r['symbol']).lower() for w in words)][:30]

async def etf_directory(query=''):
    """Exchange identities only. Never substitute equity-company search results."""
    old=CACHE.get('etfs',(0,[]))
    rows=old[1]
    if not rows or time.monotonic()-old[0]>86400:
        try:
            async with httpx.AsyncClient(timeout=12,follow_redirects=True) as c:
                response=await c.get('https://nsearchives.nseindia.com/content/equities/eq_etfseclist.csv',headers={'User-Agent':'Mozilla/5.0'})
                response.raise_for_status()
            raw=list(csv.DictReader(io.StringIO(response.text.lstrip('\ufeff'))))
            rows=[]
            for record in raw:
                row={k.strip().upper():str(v or '').strip() for k,v in record.items() if k}
                symbol=row.get('SYMBOL','');name=row.get('NAME OF COMPANY') or row.get('NAME OF THE COMPANY') or row.get('SECURITYNAME') or row.get('SECURITY NAME') or row.get('NAME')
                if re.fullmatch(r'[A-Z0-9&\-]+',symbol) and name:
                    rows.append({'symbol':symbol+'.NS','name':name,'exchange':'NSE','type':'ETF','benchmark':row.get('UNDERLYING ASSET'),'category':row.get('ETF UNDERLYING'),'isin':row.get('ISINNUMBER'),'listed':row.get('DATEOFLISTING'),'source':'NSE official ETF directory'})
            if not rows:raise ValueError('ETF directory missing expected fields')
            CACHE['etfs']=(time.monotonic(),rows)
        except Exception:
            if not rows:
                feeds=await asyncio.gather(*(get_json('https://query1.finance.yahoo.com/v1/finance/search',{'q':q,'quotesCount':30,'newsCount':0}) for q in ([query] if query else ['Nifty ETF','Gold ETF','Bank ETF'])),return_exceptions=True)
                unique={r['symbol']:r for feed in feeds if isinstance(feed,dict) for r in feed.get('quotes',[]) if r.get('quoteType')=='ETF' and r.get('symbol','').endswith(('.NS','.BO'))}
                rows=[{'symbol':r['symbol'],'name':r.get('longname') or r.get('shortname') or r['symbol'],'exchange':r.get('exchDisp',''),'type':'ETF','source':'Yahoo Finance ETF discovery · NSE directory unavailable'} for r in unique.values()]
                if not rows:raise ValueError('ETF directories unavailable')
    words=query.lower().split()
    return [r for r in rows if all(w in (r['name']+' '+r['symbol']+' '+str(r.get('benchmark',''))+' '+str(r.get('category',''))).lower() for w in words)][:400]

async def crypto_markets():
    old=CACHE.get('crypto',(0,None))
    if old[1] and time.monotonic()-old[0]<90:return old[1]
    try:
        rows=await get_json('https://api.coingecko.com/api/v3/coins/markets',{'vs_currency':'usd','order':'market_cap_desc','per_page':30,'page':1,'sparkline':'false'})
        if not isinstance(rows,list):raise ValueError('Invalid CoinGecko feed')
        data={'items':[{'symbol':r['symbol'].upper()+'-USD','name':r['name'],'image':r.get('image'),'price':r['current_price'],'change':r.get('price_change_percentage_24h'),'marketCap':r.get('market_cap'),'volume':r.get('total_volume'),'currency':'USD','asOf':r.get('last_updated'),'source':'CoinGecko'} for r in rows], 'source':'CoinGecko public API','asOf':now()}
    except Exception:
        async def quote(pair,name):
            r=await get_json('https://data-api.binance.vision/api/v3/ticker/24hr',{'symbol':pair+'USDT'})
            return {'symbol':pair+'-USD','name':name,'price':float(r['lastPrice']),'change':float(r['priceChangePercent']),'volume':float(r['quoteVolume']),'currency':'USDT','asOf':datetime.fromtimestamp(r['closeTime']/1000,timezone.utc).isoformat(),'source':'Binance public · USDT pair'}
        data={'items':await asyncio.gather(*(quote(p,n) for p,n in [('BTC','Bitcoin'),('ETH','Ethereum'),('SOL','Solana'),('BNB','BNB'),('XRP','XRP'),('DOGE','Dogecoin')])),'source':'Binance public · USDT pairs','asOf':now()}
    CACHE['crypto']=(time.monotonic(),data)
    return data

async def crypto_quote(symbol,period='1mo'):
    base=symbol.upper().removesuffix('-USD')
    if not re.fullmatch(r'[A-Z0-9]{2,15}',base):raise ValueError('Unsupported crypto pair')
    interval,limit={'1d':('5m',288),'5d':('30m',240),'1mo':('1d',30),'6mo':('1d',180),'1y':('1d',365),'5y':('1w',260)}[period]
    ticker, candles=await asyncio.gather(get_json('https://data-api.binance.vision/api/v3/ticker/24hr',{'symbol':base+'USDT'}),get_json('https://data-api.binance.vision/api/v3/klines',{'symbol':base+'USDT','interval':interval,'limit':limit}))
    return {'symbol':symbol,'name':{'BTC':'Bitcoin','ETH':'Ethereum','SOL':'Solana'}.get(base,base),'price':float(ticker['lastPrice']),'change':float(ticker['priceChangePercent']),'currency':'USDT','asOf':datetime.fromtimestamp(ticker['closeTime']/1000,timezone.utc).isoformat(),'points':[{'time':r[0],'open':float(r[1]),'high':float(r[2]),'low':float(r[3]),'close':float(r[4]),'volume':float(r[5])} for r in candles], 'source':'Binance public · USDT quote, 24h change'}

async def gmp_feed():
    old=CACHE.get('gmp',(0,None))
    if old[1] and time.monotonic()-old[0]<60:return old[1]
    source='https://www.investorgain.com/report/ipo-gmp-live/331/'
    async with httpx.AsyncClient(timeout=18, follow_redirects=True) as c:
        robots=await c.get('https://www.investorgain.com/robots.txt')
        if robots.status_code!=200:raise ValueError('GMP robots policy unavailable')
        policy=RobotFileParser();policy.parse(robots.text.splitlines())
        if not policy.can_fetch('QuantoraResearch',source):raise ValueError('GMP source disallows extraction')
        r=await c.get(source,headers={'User-Agent':'QuantoraResearch/1.0'})
        r.raise_for_status()
    if len(r.content)>4_000_000:raise ValueError('GMP page too large')
    soup=BeautifulSoup(r.text,'lxml')
    rows=[]
    # Extract the table supplied by the publisher, without model-generated values.
    for tr in soup.select('table tr'):
        cells=tr.find_all('td')
        if len(cells)<10:continue
        text=[x.get_text(' ',strip=True) for x in cells]
        link=cells[0].find('a',href=True)
        name=link.get_text(' ',strip=True) if link else text[0]
        segment='SME' if re.search(r'\bSME\b',text[0],re.I) else 'Mainboard' if re.search(r'\bIPO\b',text[0],re.I) else None
        gmp_value=format_gmp(text[1])
        date_value=lambda index: (re.search(r'\b\d{1,2}-[A-Za-z]{3}(?:-\d{4})?\b',text[index]).group(0) if len(text)>index and re.search(r'\b\d{1,2}-[A-Za-z]{3}(?:-\d{4})?\b',text[index]) else None)
        rows.append({'name':name,'gmp':gmp_value,'subscription':text[3] if len(text)>3 else None,'price':text[4] if len(text)>4 else None,'lot':text[6] if len(text)>6 else None,'opens':date_value(7),'closes':date_value(8),'listing':date_value(10),'updated':text[11] if len(text)>11 else None,'source':source,'url':('https://www.investorgain.com'+link['href']) if link and link['href'].startswith('/') else source})
        rows[-1]['segment']=segment
    # Server-rendered Next.js data is part of the same public page. Never fetch
    # hidden/private endpoints when its table is delivered through RSC.
    if not rows:
        for script in soup.find_all('script'):
            content=script.string or ''
            if 'self.__next_f.push' not in content:continue
            try:
                payload=json.loads(content[content.index('['):content.rindex(']')+1])
                body=payload[1] if len(payload)>1 and isinstance(payload[1],str) else ''
            except Exception:continue
            decoder=json.JSONDecoder()
            for match in re.finditer(r'\{"Name"\s*:',body):
                try:raw,_=decoder.raw_decode(body[match.start():])
                except Exception:continue
                clean=lambda v:BeautifulSoup(str(v or ''),'lxml').get_text(' ',strip=True)
                rows.append({'name':clean(raw.get('Name')),'gmp':format_gmp(clean(raw.get('GMP'))),'subscription':clean(raw.get('Sub')),'price':clean(raw.get('Price (₹)')),'lot':clean(raw.get('Lot')),'opens':clean(raw.get('Open')),'closes':clean(raw.get('Close')),'listing':clean(raw.get('Listing')),'updated':clean(raw.get('Updated-On')),'source':source,'url':source})
    if not rows:raise ValueError('Publisher GMP table not available')
    data={'items':rows,'source':source,'asOf':now(),'warning':'Unofficial grey-market indications, not exchange prices or guaranteed listing gains.'}
    CACHE['gmp']=(time.monotonic(),data)
    return data

async def amfi_fallback(code):
    if not CACHE.get('amfi') or time.monotonic()-CACHE['amfi'][0]>3600:
        async with httpx.AsyncClient(timeout=20) as c:
            r=await c.get('https://portal.amfiindia.com/spages/NAVAll.txt');r.raise_for_status()
        CACHE['amfi']=(time.monotonic(),[line.split(';') for line in r.text.splitlines() if line.count(';')>=5])
    row=next((r for r in CACHE['amfi'][1] if r[0]==str(code)),None)
    if not row:raise ValueError('Scheme not found in AMFI NAV feed')
    return {'meta':{'scheme_name':row[3],'scheme_category':'See scheme documents','fund_house':'AMFI published NAV'},'data':[{'date':row[5],'nav':row[4]}],'source':'AMFI official latest NAV · history unavailable','code':str(code),'historyAvailable':False}
