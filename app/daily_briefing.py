"""Short spoken digest built only from available provider observations."""
import math
from datetime import datetime, timezone

def build_briefing(quotes):
    lines=[]
    sources=[]
    for quote in quotes:
        price=quote.get('price');change=quote.get('changePercent');stamp=quote.get('asOf')
        if isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or price<=0 or not stamp:
            continue
        name={'^NSEI':'Nifty 50','^BSESN':'Sensex'}.get(quote.get('symbol'))
        if not name:continue
        movement=f", {change:+.2f} percent versus the previous close" if isinstance(change,(int,float)) and not isinstance(change,bool) and math.isfinite(change) else ''
        lines.append(f"{name}: {price:,.2f} points{movement}. Source update: {stamp}.")
        sources.append({'symbol':quote['symbol'],'asOf':stamp,'source':quote.get('source','Market provider')})
    if not lines:
        return {'date':datetime.now(timezone.utc).date().isoformat(),'headline':'Market digest unavailable','script':'Published market observations could not be retrieved. Try again later. No market direction or institutional flow has been inferred.','available':False,'sources':[],'cached':False}
    return {'date':datetime.now(timezone.utc).date().isoformat(),'headline':'Published market snapshot','script':'Gainbud market snapshot. '+' '.join(lines)+' Quotes may be delayed. This snapshot does not establish market breadth, institutional flows or future returns.','available':True,'sources':sources,'cached':False}
