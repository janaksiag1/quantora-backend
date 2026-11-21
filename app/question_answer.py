"""Question-specific answers using retrieved observations and deterministic arithmetic."""
import re
import math
from datetime import datetime, timezone, timedelta

def price_answer(question, evidence, owner):
    if re.search(r'52[- ]?week|all[- ]?time|\byear\b|dividend|revenue|earnings|profit|margin|valuation|p/e', question, re.I): return None
    high = bool(re.search(r'\b(high|highest)\b', question, re.I)) and not re.search(r'\bhigh[- ]risk\b', question, re.I)
    low = bool(re.search(r'\b(low|lowest)\b', question, re.I)) and not re.search(r'\blow[- ]risk\b', question, re.I)
    latest = bool(re.search(r'\b(price|ltp)\b', question, re.I))
    if not (high or low or latest): return None
    quote = evidence.get('intraday')
    if not quote: return None
    ist = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(ist).date()
    valid = lambda n: isinstance(n, (float, int)) and not isinstance(n, bool) and math.isfinite(n) and n > 0
    def day(point):
        try: return datetime.fromtimestamp(point['time'] / 1000, ist).date()
        except (ValueError, KeyError, TypeError, OSError): return None
    if high or low:
        points = [p for p in quote.get('points', []) if day(p) == today]
        field = 'high' if high else 'low'
        values = [p[field] for p in points if valid(p.get(field))]
        if not values:
            return f"{owner}, today's {field} is not available in the retrieved session candles for {quote.get('name', quote.get('symbol', 'this instrument'))}. Latest source update: {quote.get('asOf', 'unavailable')}. I will not substitute a previous session or another company."
        value = max(values) if high else min(values)
        unit = '₹' if quote.get('currency') == 'INR' else (quote.get('currency', '') + ' ')
        return f"{owner}, the {'highest high' if high else 'lowest low'} in the available intraday candles for {quote.get('name', quote.get('symbol'))} on {today.isoformat()} is {unit}{value:,.2f}. This covers the supplied candles, not a guaranteed complete exchange session. Source: {quote.get('source', 'market provider')}; updated {quote.get('asOf', 'time unavailable')}. Quotes may be delayed."
    if valid(quote.get('price')):
        unit = '₹' if quote.get('currency') == 'INR' else quote.get('currency', '') + ' '
        return f"{owner}, the latest available price of {quote.get('name', quote.get('symbol'))} is {unit}{quote['price']:,.2f}, updated {quote.get('asOf', 'time unavailable')}. Source: {quote.get('source', 'market provider')}. This is the provider's latest observation and may be delayed."
    return None

def answer_question(question, evidence, module, owner):
    if evidence.get('identityNeedsClarification'):
        options = '; '.join(f"{r['name']} ({r['symbol']})" for r in evidence.get('listingCandidates', []) if r.get('name') and r.get('symbol'))
        return f"{owner}, which exact company do you mean? Please choose the company or NSE/BSE symbol before I quote a price or assess it." + (f" Matching listings: {options}." if options else '')
    observed = price_answer(question, evidence, owner)
    if observed: return observed
    if module == 'stocks' and re.search(r'\b(today|todays|aaj)\b',question,re.I) and re.search(r'\b(highest|lowest|high|low)\b',question,re.I) and not re.search(r'risk|profit|dividend|earnings|revenue|margin',question,re.I):
        return f"{owner}, the requested current-session high or low could not be verified because intraday candles were not retrieved. Choose the exact company symbol and retry; a past price or another company is not a substitute."
    metrics=evidence.get('metrics') or {}
    if re.search(r'net profit|profit after tax|\bpat\b|ebitda|revenue|earnings|quarter|annual|\bfy\d|income|margin|cash flow|balance sheet|company.*profit|profit.*company',question,re.I) and not re.search(r'per lot|one lot|listing gain|my investment|mera profit|mujhe.*profit',question,re.I):
        return None
    profit=bool(re.search(r'profit|return|gain|loss|kitna|munafa|kamai|fayda|nuksan',question,re.I))
    if profit:
        lot=metrics.get('lot') if module=='ipo' else None
        if lot:
            scenarios=lot.get('scenarios',[])
            indication=next((s for s in scenarios if 'GMP' in s.get('label','')),None)
            downside=next((s for s in scenarios if s.get('returnPercent')==-20),None)
            text=f"{owner}, exact future profit cannot be known. The retrieved publisher lot is {lot['shares']} shares at ₹{lot['issuePrice']:,.2f}; one-lot capital is ₹{lot['applicationAmount']:,.2f}. "
            if indication:
                text+=f"At the unofficial publisher GMP indication, the arithmetic is ₹{indication['grossProfit']:,.2f} gross {'loss' if indication['grossProfit']<0 else 'gain'} per lot ({indication['returnPercent']:+.2f}%). This is a scenario, not an expected return or guaranteed listing price. "
            else:text+='No matched GMP indication was supplied, so a listing-gain amount cannot be calculated. '
            if downside:text+=f"A 20% fall from the issue price would mean a ₹{abs(downside['grossProfit']):,.2f} gross loss per lot. "
            return text+'Fees and taxes are excluded. Verify the official offer price and minimum application lots before using these figures.'
        history=metrics.get('history')
        text=f'{owner}, no reliable future-profit amount can be inferred from the retrieved evidence. '
        if history:text+=f"The observed historical return is {history['observedReturn']:+.2f}% over the available {history['observations']} observations; this is past performance, not a forecast. "
        if module=='ipo':text+='A uniquely matched issue price and lot size are needed for a one-lot calculation. '
        return text+'Choose your investment amount, horizon and loss scenario; the report does not invent a target price or average profit.'
    issues=evidence.get('officialIssues') or []
    if module=='ipo' and re.search(r'open|clos|date|timeline|kab|subscription|subscribe|allot',question,re.I):
        if len(issues)==1:
            i=issues[0]
            return f"{owner}, the retrieved exchange issue record for {i.get('name','this issuer')} reports bidding from {i.get('opens') or 'date not supplied'} to {i.get('closes') or 'date not supplied'}, with subscription {i.get('subscription') if i.get('subscription') is not None else 'not supplied'}×. Allotment for your application must be checked with the issue's official registrar; subscription does not confirm an allocation."
    return None
