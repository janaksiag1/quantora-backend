"""Recent proposed IPO filings; never represented as confirmed offer dates."""
import hashlib
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup

SOURCE='https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&smid=10&ssid=15'
_cache=(0, {})

def parse_filings(html):
    soup=BeautifulSoup(html,'lxml'); rows=[]
    for tr in soup.select('table#sample_1 tbody tr')[:50]:
        cells=tr.find_all('td')
        if len(cells)<2: continue
        anchors=cells[1].find_all('a',href=True)
        if not anchors: continue
        first=anchors[0];title=first.get_text(' ',strip=True);url=urljoin(SOURCE,first['href'])
        if urlparse(url).hostname!='www.sebi.gov.in' or not url.startswith('https://') or not title: continue
        # Preserve regulator link labels; do not infer issue dates or approval status.
        name=title.split(' - ')[0].split(' – ')[0].strip()
        rows.append({'id':hashlib.sha256(url.encode()).hexdigest()[:20],'name':name,'title':title,'filedAt':cells[0].get_text(' ',strip=True),'status':'Filed · dates TBA','documentUrl':url,'source':'SEBI','opens':None,'closes':None})
    return rows

async def filings():
    global _cache
    if _cache[1] and time.monotonic()-_cache[0]<3600:return _cache[1]
    try:
        async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
            robots=await client.get('https://www.sebi.gov.in/robots.txt');robots.raise_for_status()
            policy=RobotFileParser();policy.parse(robots.text.splitlines())
            if not policy.can_fetch('GainbudResearch',SOURCE):raise ValueError('Source access policy prevents extraction')
            response=await client.get(SOURCE,headers={'User-Agent':'GainbudResearch/1.0'});response.raise_for_status()
            if len(response.content)>2000000 or 'html' not in response.headers.get('content-type',''):raise ValueError('Unexpected filing response')
        rows=parse_filings(response.text)
        if not rows:raise ValueError('Regulator filing format unavailable')
        result={'filings':rows,'source':SOURCE,'asOf':datetime.now(timezone.utc).isoformat(),'stale':False,'coverage':'Latest 25 SEBI filing records, including amendments. Not an exhaustive pipeline or an approved issue calendar.'}
        _cache=(time.monotonic(),result);return result
    except Exception:
        if _cache[1]:return {**_cache[1],'stale':True,'warning':'SEBI filing feed unavailable; showing last retrieved records.'}
        raise
