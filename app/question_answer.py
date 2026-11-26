"""Question-specific answers using retrieved observations, deterministic financial arithmetic, and conversational reasoning."""
import re
import math
from datetime import datetime, timezone, timedelta

def price_answer(question, evidence, owner):
    if re.search(r'(?:high|low)[- ](?:debt|volatility|cost|margin|subscription|growth)', question, re.I): return None
    if re.search(r'52[- ]?week|all[- ]?time|\byear\b|dividend|revenue|earnings|profit|margin|valuation|p/e|kamai', question, re.I): return None
    high = bool(re.search(r'\b(high|highest)\b', question, re.I)) and not re.search(r'\bhigh[- ]risk\b', question, re.I)
    low = bool(re.search(r'\b(low|lowest)\b', question, re.I)) and not re.search(r'\blow[- ]risk\b', question, re.I)
    latest = bool(re.search(r'\b(price|ltp|bhav|rate)\b', question, re.I))
    if not (high or low or latest): return None
    quote = evidence.get('intraday')
    if not quote:
        return f"{owner}, the intraday candles were not retrieved, so I cannot verify today's price, high or low. Please retry the exact instrument."
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
            return f"{owner}, today's {field} is not available in the retrieved session candles for {quote.get('name', quote.get('symbol', 'this instrument'))}. Latest source update: {quote.get('asOf', 'unavailable')}."
        value = max(values) if high else min(values)
        unit = '₹' if quote.get('currency') == 'INR' else (quote.get('currency', '') + ' ')
        return f"{owner}, the {'highest high' if high else 'lowest low'} for {quote.get('name', quote.get('symbol'))} on {today.isoformat()} is {unit}{value:,.2f} based on the available session candles (which may be delayed). Source: {quote.get('source', 'market provider')}; updated {quote.get('asOf', 'unavailable')}."
    if valid(quote.get('price')):
        unit = '₹' if quote.get('currency') == 'INR' else quote.get('currency', '') + ' '
        return f"{owner}, the latest available price of {quote.get('name', quote.get('symbol'))} is {unit}{quote['price']:,.2f} (Source: {quote.get('source', 'not supplied')}, updated {quote.get('asOf', 'timestamp not supplied')}). Quotes may be delayed."
    return None

def is_hindi_query(text: str) -> bool:
    return bool(re.search(r'[\u0900-\u097F]|kya|kitna|milega|hoga|bhai|kamaye|kamana|fayda|munafa|karein|chahiye|dega|lena|kharide|beche', text, re.I))

def answer_question(question, evidence, module, owner):
    owner_str = owner if owner and owner.lower() != 'investor' else 'Investor'
    is_hi = is_hindi_query(question)

    if evidence.get('identityNeedsClarification'):
        options = '; '.join(f"{r['name']} ({r['symbol']})" for r in evidence.get('listingCandidates', []) if r.get('name') and r.get('symbol'))
        if is_hi:
            return f"{owner_str}, kripya company ya ticker confirm karein taaki accurate valuation aur price calculate ho sake. Matching listings: {options}."
        return f"{owner_str}, which exact company do you mean? Please choose the company or NSE/BSE symbol before I quote a price or assess it." + (f" Matching listings: {options}." if options else '')

    observed = price_answer(question, evidence, owner_str)
    if observed: return observed

    if evidence.get('educational'):
        if is_hi:
            return f"{owner_str}, IPO (Initial Public Offering) me ek company pehli baar public ko apne shares offer karti hai. Allotment milne par aap shareholder bante hain; listing ke baad exchange par shares trade ho sakte hain.\n\nApply karne se pehle offer document me business, financials, valuation, funds ka use aur risks dekhein. Subscription demand dikhata hai; GMP unofficial hai. Dono listing profit ya allotment guarantee nahi karte."
        return f"{owner_str}, an IPO (Initial Public Offering) is when a company offers shares to the public for the first time. If shares are allotted, you become a shareholder; once listed, those shares can trade on an exchange.\n\nBefore applying, review the offer document for the business, financials, valuation, use of proceeds and risks. Subscription shows demand; GMP is unofficial. Neither guarantees an allotment or a listing profit."

    metrics=evidence.get('metrics') or {}
    financial_fact=bool(re.search(r'net profit|profit margin|earnings|revenue|FY\d|52[- ]?week',question,re.I))
    profit=not financial_fact and bool(re.search(r'profit|return|gain|loss|munafa|kamai|fayda|nuksan|kitna|target',question,re.I))
    if profit:
        if module=='ipo':
            lot=metrics.get('lot') or {}
            if lot.get('applicationAmount') and lot.get('shares') and lot.get('issuePrice'):
                text=f"{owner_str}, one lot costs ₹{lot['applicationAmount']:,.2f} ({lot['shares']} shares at ₹{lot['issuePrice']:,.2f}). This may differ from the minimum application."
                for row in lot.get('scenarios',[]):
                    amount=row.get('grossProfit')
                    if isinstance(amount,(int,float)) and math.isfinite(amount):
                        text+=f"\n• {row.get('label','Scenario')}: ₹{amount:,.2f} gross {'loss' if amount<0 else 'gain'}"
                        if amount<0:text+=f" (₹{abs(amount):,.2f} gross loss)"
                return text+f"\nThese are arithmetic scenarios, not an expected return. GMP is unofficial; verify the final offer terms. Fees and taxes are excluded. Source: {lot.get('source') or 'retrieved issue terms'}; publisher update: {lot.get('publisherUpdated') or 'not supplied'}."
            return f"{owner_str}, no reliable future-profit figure can be calculated. The final issue price, application lot size and a stated listing-price assumption are needed. Subscription and GMP do not guarantee a gain."
        history=metrics.get('history') or {}
        observed=history.get('observedReturn')
        if isinstance(observed,(int,float)) and math.isfinite(observed):
            return f"{owner_str}, the observed historical return was {observed:+.2f}% over {history.get('observations','available')} observations. This is not a forecast of future profit; it excludes execution costs and taxes."
        return None
    if module=='ipo' and re.search(r'open|clos|date|timeline|kab|subscription',question,re.I):
        rows=evidence.get('officialIssues') or []
        if len(rows)==1:
            row=rows[0];sub=row.get('subscription')
            return f"{owner_str}, {row.get('name','this issue')} has bidding from {row.get('opens') or 'date not published'} to {row.get('closes') or 'date not published'}. Published total subscription: {str(sub)+'×' if isinstance(sub,(int,float)) and math.isfinite(sub) else 'not available'}. Source: {row.get('source') or 'retrieved issue feed'}. Verify any allotment schedule with the official registrar; Gainbud does not collect your PAN."
    # Other questions require sourced reasoning; no invented ranges or targets.
    return None
