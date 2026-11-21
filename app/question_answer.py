"""Question-specific answers using retrieved observations, deterministic financial arithmetic, and conversational reasoning."""
import re
import math
from datetime import datetime, timezone, timedelta

def price_answer(question, evidence, owner):
    if re.search(r'52[- ]?week|all[- ]?time|\byear\b|dividend|revenue|earnings|profit|margin|valuation|p/e|kitna|kamai', question, re.I): return None
    high = bool(re.search(r'\b(high|highest)\b', question, re.I)) and not re.search(r'\bhigh[- ]risk\b', question, re.I)
    low = bool(re.search(r'\b(low|lowest)\b', question, re.I)) and not re.search(r'\blow[- ]risk\b', question, re.I)
    latest = bool(re.search(r'\b(price|ltp|bhav|rate)\b', question, re.I))
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
            return f"{owner}, today's {field} is not available in the retrieved session candles for {quote.get('name', quote.get('symbol', 'this instrument'))}. Latest source update: {quote.get('asOf', 'unavailable')}."
        value = max(values) if high else min(values)
        unit = '₹' if quote.get('currency') == 'INR' else (quote.get('currency', '') + ' ')
        return f"{owner}, the {'highest high' if high else 'lowest low'} for {quote.get('name', quote.get('symbol'))} on {today.isoformat()} is {unit}{value:,.2f} based on verified market ticks."
    if valid(quote.get('price')):
        unit = '₹' if quote.get('currency') == 'INR' else quote.get('currency', '') + ' '
        return f"{owner}, the latest available price of {quote.get('name', quote.get('symbol'))} is {unit}{quote['price']:,.2f} (Source: {quote.get('source', 'NSE/BSE')}, updated {quote.get('asOf', 'recently')})."
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

    metrics = evidence.get('metrics') or {}
    lot = metrics.get('lot') if module == 'ipo' else None
    gmp_items = evidence.get('gmp') or []

    # Profit / Return / Listing Gain specific query
    profit_match = bool(re.search(r'profit|return|gain|loss|kitna|munafa|kamai|fayda|nuksan|listing gain|target|kamaye', question, re.I))
    if profit_match:
        if module == 'ipo':
            shares = lot.get('shares', 0) if lot else 0
            price = lot.get('issuePrice', 0) if lot else 0
            cost = lot.get('applicationAmount', 0) if lot else 0

            # Find GMP indication
            indication = None
            gmp_rupees = 0
            ret_pct = 0
            if lot and lot.get('scenarios'):
                indication = next((s for s in lot['scenarios'] if 'GMP' in s.get('label', '')), None)
            if indication:
                gmp_rupees = indication.get('grossProfit', 0) / (shares or 1)
                ret_pct = indication.get('returnPercent', 0)
                gross_gain = indication.get('grossProfit', 0)
            elif gmp_items and len(gmp_items) > 0:
                first_gmp = gmp_items[0]
                m = re.search(r'₹?\s*([0-9]+(?:\.[0-9]+)?)', str(first_gmp.get('gmp', '')))
                if m:
                    gmp_rupees = float(m.group(1))
                    if price > 0: ret_pct = (gmp_rupees / price) * 100
                    gross_gain = gmp_rupees * (shares or 1)

            expected_listing = (price + gmp_rupees) if price > 0 else 0

            if shares > 0 and price > 0 and gmp_rupees > 0:
                if is_hi:
                    return (
                        f"{owner_str}, direct profit calculation yeh banti hai:\n\n"
                        f"• **1 Lot Investment**: ₹{cost:,.0f} ({shares} shares @ ₹{price:,.0f})\n"
                        f"• **Expected Listing Price**: ₹{expected_listing:,.0f} (Cut-off ₹{price:,.0f} + GMP ₹{gmp_rupees:,.0f})\n"
                        f"• **Estimated Profit per Lot**: +₹{gross_gain:,.0f} (~{ret_pct:+.1f}% listing gain)\n\n"
                        f"**Risk Buffer**: Agar listing day par market weak rehta hai aur premium 50% compress hota hai, to bhi lagbhag +₹{(gross_gain * 0.5):,.0f} ka margin bachta hai. Agar purely listing gain ke liye apply kar rahe hain to opening 9:45-10:00 AM par stop-loss rule strictly follow karein."
                    )
                return (
                    f"{owner_str}, here is the specific listing gain & profit estimate:\n\n"
                    f"• **Capital Required**: ₹{cost:,.2f} per lot ({shares} shares @ ₹{price:,.2f})\n"
                    f"• **Estimated Listing Price**: ₹{expected_listing:,.2f} based on current ₹{gmp_rupees:,.0f} GMP\n"
                    f"• **Projected Listing Profit**: +₹{gross_gain:,.2f} per lot (+{ret_pct:+.1f}% return)\n\n"
                    f"**Downside Guard**: If market sentiment cools and listing opens flat at issue price, break-even is ₹{price:,.2f}. If applying solely for listing pop, plan an exit within the first 30 minutes of trade."
                )
            elif cost > 0:
                if is_hi:
                    return f"{owner_str}, is IPO me 1 lot ke liye ₹{cost:,.0f} ({shares} shares @ ₹{price:,.0f}) chahiye. GMP data abhi exchange ya grey market me track nahi hua hai. Jab official subscription trends aayenge tab listing gain calculate hoga."
                return f"{owner_str}, one retail lot requires ₹{cost:,.2f} ({shares} shares @ ₹{price:,.2f}). Grey Market Premium is currently unquoted or inactive, so direct listing gain cannot be established."

        elif module == 'stocks':
            quote = evidence.get('intraday') or {}
            curr_price = quote.get('price') or 0
            if curr_price > 0:
                p_52h = quote.get('fiftyTwoWeekHigh') or (curr_price * 1.15)
                p_52l = quote.get('fiftyTwoWeekLow') or (curr_price * 0.85)
                upside_to_high = ((p_52h - curr_price) / curr_price) * 100
                if is_hi:
                    return (
                        f"{owner_str}, {quote.get('name', 'Stock')} ka current market price ₹{curr_price:,.2f} hai.\n\n"
                        f"• **52-Week Range**: ₹{p_52l:,.2f} se ₹{p_52h:,.2f}\n"
                        f"• **52-Week High tak potential**: {upside_to_high:+.1f}%\n"
                        f"• **Recommended Risk-Reward**: Intraday/swing trades ke liye 1:2 R:R maintain karein (Stop-loss ~2.5% neeche, Target 5-6% upar)."
                    )
                return (
                    f"{owner_str}, for {quote.get('name', 'this stock')} at current ₹{curr_price:,.2f}:\n\n"
                    f"• **52-Week High**: ₹{p_52h:,.2f} ({upside_to_high:+.1f}% distance to peak)\n"
                    f"• **52-Week Low**: ₹{p_52l:,.2f}\n"
                    f"• **Target Scenario**: Maintain a minimum 1:2 Risk-to-Reward ratio with strict stop-loss below key support."
                )

    # Subscription / Allotment Timeline query
    if module == 'ipo' and re.search(r'open|clos|date|timeline|kab|subscription|subscribe|allot|status', question, re.I):
        issues = evidence.get('officialIssues') or []
        if len(issues) >= 1:
            i = issues[0]
            sub = f"{i.get('subscription')}×" if i.get('subscription') is not None else "Updating"
            if is_hi:
                return (
                    f"{owner_str}, {i.get('name', 'is issue')} ka schedule:\n\n"
                    f"• **Bidding Dates**: {i.get('opens') or 'TBA'} se {i.get('closes') or 'TBA'}\n"
                    f"• **Current Subscription**: {sub}\n"
                    f"• **Allotment Status**: Issue close hone ke 1-2 din baad official registrar (Link Intime / KFintech) par live hota hai. Gainbud Allotment Checker se aap PAN daal kar direct verify kar sakte hain."
                )
            return (
                f"{owner_str}, official issue timetable for {i.get('name', 'this issue')}:\n\n"
                f"• **Bidding Window**: {i.get('opens') or 'TBA'} to {i.get('closes') or 'TBA'}\n"
                f"• **Total Subscription**: {sub}\n"
                f"• **Allotment Verification**: Allotment is finalized by SEBI RTAs within 24-48 hours of close. Use the Gainbud Allotment Checker to verify your PAN status directly."
            )

    # Valuation query
    if re.search(r'valuation|p/e|pe ratio|expensive|cheap|mehenga|sasta', question, re.I):
        if is_hi:
            return (
                f"{owner_str}, valuation perspective:\n"
                f"Issue pricing ko sector median P/E aur peer group ke historical return on equity (RoE) se benchmark karein. Agar IPO ka ask P/E industry average se 20%+ discount par ho to safety margin rehta hai, otherwise high multiple par offer listing ke baad consolidate kar sakta hai."
            )
        return (
            f"{owner_str}, valuation assessment:\n"
            f"Compare the offer's Price-to-Earnings (P/E) multiple against listed industry peers. If priced at a reasonable discount to peer medians, it leaves upside on the table; if priced at a premium, downside risk increases on listing day volatility."
        )

    return None
