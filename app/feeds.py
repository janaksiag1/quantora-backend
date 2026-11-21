import re

import time

from lxml import etree as ET

import httpx



_cache: tuple[float, list] = (0, [])



async def news():
    global _cache
    if _cache[1] and time.monotonic()-_cache[0]<300:return _cache[1]
    import asyncio
    from urllib.parse import urlparse
    from email.utils import parsedate_to_datetime
    from bs4 import BeautifulSoup
    feeds=[('https://www.business-standard.com/rss/markets-106.rss','Business Standard','business-standard.com'),('https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms','The Economic Times','economictimes.indiatimes.com')]
    async with httpx.AsyncClient(timeout=15,follow_redirects=True) as client:
        async def load(feed,name,domain):
            try:
                r=await client.get(feed,headers={'User-Agent':'QuantoraResearch/1.0'});r.raise_for_status()
                if len(r.content)>2_000_000 or b'<!ENTITY' in r.content:return []
                root=ET.fromstring(r.content,parser=ET.XMLParser(recover=True,resolve_entities=False,no_network=True));rows=[]
                for item in root.xpath('//*[local-name()="item"]'):
                    title=item.findtext('title','').strip();url=item.findtext('link','').strip();host=urlparse(url).hostname or ''
                    if not title or not url.startswith('https://') or not(host==domain or host.endswith('.'+domain)):continue
                    image=None
                    candidates=item.xpath('.//*[local-name()="content" or local-name()="thumbnail" or local-name()="enclosure"]/@url')
                    summary=BeautifulSoup(item.findtext('description',''),'lxml')
                    candidates += [i.get('src','') for i in summary.find_all('img')]
                    for candidate in candidates:
                        parsed=urlparse(candidate)
                        if parsed.scheme=='https' and parsed.hostname and any(parsed.hostname==h or parsed.hostname.endswith('.'+h) for h in ['business-standard.com','bsmedia.business-standard.com','economictimes.indiatimes.com','etimg.com']):image=candidate;break
                    date=item.findtext('pubDate','')
                    try:published=parsedate_to_datetime(date).timestamp()
                    except Exception:published=0
                    rows.append({'title':title,'url':url,'date':date,'source':name,'image':image,'summary':summary.get_text(' ',strip=True)[:1200],'published':published,'verification':'Publisher reporting; not independently verified'})
                return rows
            except (httpx.HTTPError,ET.XMLSyntaxError,AttributeError):return []
        batches=await asyncio.gather(*(load(*f) for f in feeds))
    seen=set();result=[]
    for row in sorted([r for batch in batches for r in batch],key=lambda r:r['published'],reverse=True):
        key=re.sub(r'\W+','',row['title'].lower())
        if key not in seen:seen.add(key);result.append(row)
    if not result:raise ValueError('Published headlines are temporarily unavailable.')
    _cache=(time.monotonic(),result[:80]);return _cache[1]


async def fund(code: str):

    async with httpx.AsyncClient(timeout=15) as client:

        r = await client.get(f'https://api.mfapi.in/mf/{code}')

        r.raise_for_status()

    data = r.json()

    if not data.get('data'):

        raise ValueError('No NAV data')

    return {'meta': data['meta'], 'data': data['data'][:365], 'source': 'MFapi · AMFI-derived NAV', 'code': code}



_fund_directory = (0, [])



async def search_funds(query: str):

    global _fund_directory

    if time.monotonic() - _fund_directory[0] > 86400 or not _fund_directory[1]:

        async with httpx.AsyncClient(timeout=25) as client:

            r = await client.get('https://api.mfapi.in/mf')

            r.raise_for_status()

        _fund_directory = (time.monotonic(), r.json())

    words = query.lower().split()

    seen=set(); rows=[]
    for f in _fund_directory[1]:
        code=str(f.get('schemeCode','')); name=f.get('schemeName','')
        if not code.isdigit() or not isinstance(name,str) or not name or code in seen:continue
        if not all(word in (name+' '+code).lower() for word in words):continue
        seen.add(code);rows.append({'symbol':code,'name':name,'exchange':'AMFI','type':'Mutual fund'})
        if len(rows)>=15:break
    return rows

