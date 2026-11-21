"""Bounded public-source discovery for a company name, not just a ticker."""
import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from lxml import etree

from .providers import market, search_assets
from .ipo import get_issues

STOP = set('tell me about analyze analyse explain compare research please stock stocks share shares company investment invest buy sell should could would what why how is are the a an and or for of in on with this that long term risks risk key missing evidence conditions invalidate thesis hindi hinglish mujhe batao kya ka ki ke hai h mein aur karo kr do ye'.split())
STOP.update(['limited','ltd','inc','corporation','corp','pvt','private'])
STOP.update('today todays highest lowest high low price prices current latest intraday aaj abhi bata bta batao btao'.split())
STOP.update('today todays yesterday current latest highest lowest high low price prices rate rates now aaj abhi bata bta batao btao'.split())

def select_listing(query, candidates):
    """Only resolve a ticker or an unambiguous full name, never a bare brand."""
    wanted = set(terms(query))
    exact = [c for c in candidates if query.upper() in {c.get('symbol', '').upper(), c.get('symbol', '').upper().split('.')[0]}]
    matches_name = [c for c in candidates if wanted and wanted <= set(terms(c.get('name', '')))]
    options = exact or matches_name
    identities = {c.get('symbol', '').removesuffix('.NS').removesuffix('.BO') for c in options}
    full_name = bool(options) and (len(wanted) > 1 or wanted == set(terms(options[0].get('name', ''))))
    if len(identities) == 1 and (exact or full_name):
        return next((c['symbol'] for c in options if c['symbol'].endswith('.NS')), options[0]['symbol']), []
    return None, [{'name': c.get('name', ''), 'symbol': c.get('symbol', '')} for c in options[:5]]


def terms(text):
    return [t[:-1] if t.endswith('s') and len(t) > 5 else t for t in re.findall(r'[a-zA-Z][a-zA-Z&.-]*', text.lower()) if t not in STOP]


def matches(query, title):
    wanted = set(terms(query))
    found = set(terms(title))
    return bool(wanted) and len(wanted & found) >= min(2, len(wanted))


def lookup_query(prompt, history=None):
    # Keep a research sentence such as "BLS polymer IPO: review the risks"
    # from turning into an over-constrained news query containing every verb.
    prompt = re.sub(r'^(?:can|could|would) you (?:please )?', '', prompt.strip(), flags=re.I)
    entity_part = re.split(r'\bipo\b|[:?;]', prompt, maxsplit=1, flags=re.IGNORECASE)[0]
    words = terms(entity_part or prompt)
    # A short follow-up can reuse the previous user's company name. Assistant
    # statements are never used as verified facts or as a resolved ticker.
    if (not words or set(words) <= {'summarize', 'summary', 'more', 'details', 'gap', 'it', 'its', 'now'}) and history:
        previous = [t.get('content', '') for t in history if t.get('role') == 'user']
        if previous and len(terms(previous[-1])) <= 8:
            words = terms(previous[-1]) or words
    return ' '.join(words[:10])[:120]


async def company_news(query):
    if not query:
        return []
    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.get('https://news.google.com/rss/search', params={
            'q': query, 'hl': 'en-IN', 'gl': 'IN', 'ceid': 'IN:en',
        }, headers={'User-Agent': 'QuantoraResearch/1.0'})
        response.raise_for_status()
    if len(response.content) > 1_500_000 or b'<!ENTITY' in response.content:
        return []
    root = etree.fromstring(response.content, etree.XMLParser(resolve_entities=False, no_network=True, recover=True))
    output = []
    for item in root.findall('.//item'):
        title = item.findtext('title', '')
        link = item.findtext('link', '')
        if not matches(query, title) or urlparse(link).hostname != 'news.google.com':
            continue
        output.append({'title': title, 'url': link, 'date': item.findtext('pubDate', ''),
                       'publisher': item.findtext('source', 'Google News'),
                       'verification': 'Published headline only; full article and claims not independently verified.'})
        if len(output) == 6:
            break
    return output


async def collect_sources(prompt, symbol=None, history=None, module='ipo', document_url='', asset_name=''):
    identity_name = asset_name if asset_name.strip().lower() not in {'custom research', 'market research', 'custom', 'research'} else ''
    query = lookup_query(identity_name or prompt, history)
    if not re.search(r'\bipo\b|prospectus|allotment', prompt, re.I) and re.search(r'\bstock\b|\bshares?\b|\bintraday\b', prompt, re.I):
        module = 'stocks'
    if not symbol and re.search(r'\b(bitcoin|ethereum|solana|crypto|btc|eth)\b', prompt, re.I) and 'ipo' not in prompt.lower():
        module='crypto'
    result = {'query': query, 'module': module, 'quotes': [], 'officialIssues': [], 'headlines': [], 'gmp': [],
              'retrievedAt': datetime.now(timezone.utc).isoformat(),
              'limitations': 'Headlines are attributed reports, not verified filings. Never infer missing financials or a listing from similar company names.'}
    links = []
    concept = re.sub(r'[^a-z\s]', '', prompt.lower()).strip()
    concept = re.sub(r'^(?:can|could|would) you (?:please )?(?:tell me |explain )?', '', concept)
    concept = re.sub(r'^please\s+', '', concept)
    if not symbol and not identity_name and not document_url and re.fullmatch(
        r'(?:what (?:is|are) (?:an? |the )?(?:ipo|initial public offering)|explain (?:an? |the )?ipo|ipo kya hai)', concept
    ):
        result.update({'query': '', 'sources': [], 'metrics': {}, 'educational': True,
                       'limitations': 'General educational explanation. No current issuer or market observations were requested or retrieved.'})
        return result
    if not symbol and module=='crypto':
        try:
            from .market_sources import crypto_markets
            rows=(await crypto_markets())['items']
            found=[r for r in rows if r['name'].lower() in prompt.lower() or r['symbol'].split('-')[0].lower() in query.split()]
            if len(found)==1:symbol=found[0]['symbol']
        except Exception:pass
    if not symbol and module=='funds':
        try:
            from .feeds import search_funds
            candidates=await search_funds(prompt[:100])
            if len(candidates)==1:symbol=candidates[0]['symbol']
            elif candidates:result['listingCandidates']=candidates[:5]
        except Exception:pass
    if not symbol and query and module not in ['funds', 'crypto']:
        try:
            candidates = await search_assets(query)
            symbol, options = select_listing(query, candidates)
            if options:
                result['listingCandidates'] = options
                result['identityNeedsClarification'] = True
        except Exception:
            pass

    if not symbol and query and module == 'stocks' and re.search(r'\b(today|todays|aaj|abhi|ltp|highest|lowest)\b', prompt, re.I):
        result['identityNeedsClarification'] = True

    async def quote():
        if symbol:
            try:
                if module == 'funds':
                    from .feeds import fund
                    from .market_sources import amfi_fallback
                    try: data = await fund(symbol)
                    except Exception: data = await amfi_fallback(symbol)
                    result['fund'] = data
                    links.append({'title':'Scheme NAV · MFapi / AMFI','url':'https://api.mfapi.in/mf/'+symbol})
                    return
                from .research_metrics import history_summary
                data = {**await market.quote(symbol,'1y')}
                if re.search(r'\b(today|todays|highest|lowest|high|low|current|latest|intraday|aaj|abhi)\b', prompt, re.I):
                    try:
                        result['intraday'] = await market.quote(symbol, '1d')
                    except Exception:
                        result['intradayError'] = 'Current-session candles were not retrieved.'
                if module=='stocks' and symbol.endswith('.NS') and data.get('currency')=='INR':
                    from .trading_engine import candles,setups,IST
                    data['technicalResearch']=setups(candles(data.get('points',[])))
                    observed=data['technicalResearch'].get('asOf')
                    if observed:data['technicalResearch']['asOf']=datetime.fromtimestamp(observed/1000,IST).date().isoformat()
                    data['technicalMethod']='Completed daily candles; deterministic setup observations, not investment recommendations or calibrated probabilities.'
                data['historicalSummary']=history_summary(data.get('points',[]))
                data['points'] = data.get('points', [])[-60:]
                result['quotes'].append(data)
                links.append({'title': data.get('name', symbol) + ' · Yahoo Finance', 'url': 'https://finance.yahoo.com/quote/' + symbol})
            except Exception:
                if module == 'crypto' and symbol.endswith('-USD'):
                    try:
                        from .market_sources import crypto_quote
                        from .research_metrics import history_summary
                        data=await crypto_quote(symbol,'1y');data['historicalSummary']=history_summary(data.get('points',[]));data['points']=data.get('points',[])[-60:]
                        result['quotes'].append(data)
                        links.append({'title':'Binance public spot observations · USDT','url':'https://www.binance.com/en/trade/'+symbol.replace('-USD','_USDT')})
                        return
                    except Exception: pass
                result['quoteError'] = 'No quote retrieved for ' + symbol

    async def issues(kind):
        if not query or module != 'ipo':
            return
        try:
            feed = await get_issues(kind)
            for issue in feed['issues']:
                if matches(query, issue.get('name', '') + ' ' + issue.get('symbol', '')):
                    result['officialIssues'].append(issue)
            if result['officialIssues'] and not any(l['title'] == 'NSE public issue source' for l in links):
                links.append({'title': 'NSE public issue source', 'url': 'https://www.nseindia.com/market-data/all-upcoming-issues-ipo'})
        except Exception:
            pass

    async def headlines():
        if result.get('identityNeedsClarification'): return
        try:
            result['headlines'] = await company_news(query)
            links.extend({'title': h['title'], 'url': h['url']} for h in result['headlines'][:4])
        except Exception:
            try:
                from .feeds import news
                result['headlines']=[h for h in await news() if matches(query,h['title'])][:6]
                links.extend({'title':h['title'],'url':h['url']} for h in result['headlines'])
            except Exception:result['newsError'] = 'Company headline sources unavailable.'

    async def gmp():
        if module != 'ipo':return
        try:
            from .market_sources import gmp_feed
            feed=await gmp_feed()
            result['gmp']=[r for r in feed['items'] if matches(query,r['name'])][:3]
            if result['gmp']:links.append({'title':'InvestorGain · unofficial GMP, not guaranteed listing price','url':feed['source']})
        except Exception:result['gmpError']='GMP publisher unavailable. No premium estimated.'

    async def filing():
        if not document_url:return
        try:
            from .filings import read_filing
            result['filing']=await read_filing(document_url)
            links.append({'title':'Official filing · selected PDF excerpts with page numbers','url':document_url})
        except Exception as exc:result['filingError']=str(exc) if isinstance(exc,ValueError) else 'Official document could not be retrieved. No financial statements were inferred.'
    async def company_details():
        if module not in ['stocks','ipo'] or not symbol or symbol.startswith('^'):return
        try:
            from .company_data import company
            result['company']=await company(symbol)
            links.append({'title':'Company ratios/profile · Yahoo Finance aggregator data','url':result['company']['url']})
        except Exception:result['companyError']='Company ratios/profile unavailable; no fundamentals inferred from prices.'
    await asyncio.gather(quote(), issues('current'), issues('past'), headlines(), gmp(),filing(),company_details())
    result['sources'] = [{**link,'id':f'S{i+1}'} for i,link in enumerate(links)]
    from .research_metrics import research_metrics
    result['metrics']=research_metrics(result,module)
    if module=='ipo':
        from .research_metrics import listing_outcomes
        outcomes=await listing_outcomes(result)
        if outcomes:
            result['metrics']['listingOutcomes']=outcomes
            result['metrics']['averageProfitReason']='Verified listing observations below describe past closes. This limited sample does not establish an expected average profit.'
    return result
