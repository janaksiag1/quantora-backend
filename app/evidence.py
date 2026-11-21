import math
import statistics
from .providers import market, search_assets

async def inspect_evidence(symbol: str | None, subject: str = ''):
    if not symbol:
        results = await search_assets(subject[:100])
        if not results:
            raise ValueError('Select an exact market listing to inspect its evidence.')
        symbol = results[0]['symbol']
    quote = await market.quote(symbol, '6mo')
    closes = [p['close'] for p in quote['points']]
    if len(closes) < 2:
        raise ValueError('Insufficient source observations to calculate price statistics.')
    returns = [math.log(b/a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]
    peak, drawdown = closes[0], 0
    for close in closes:
        peak = max(peak, close)
        drawdown = min(drawdown, close / peak - 1)
    rsi = None
    if len(closes) > 14:
        differences = [b-a for a,b in zip(closes, closes[1:])]
        gain = sum(max(d,0) for d in differences[:14])/14
        loss = sum(max(-d,0) for d in differences[:14])/14
        for d in differences[14:]:
            gain = (gain*13+max(d,0))/14
            loss = (loss*13+max(-d,0))/14
        rsi = 100-100/(1+gain/loss) if loss else 100 if gain else 50
    periods = 365 if symbol.endswith('-USD') else 252
    metrics = {'observations': len(closes), 'periodReturn': (closes[-1]/closes[0]-1)*100, 'maxDrawdown': drawdown*100, 'annualizedVolatility': statistics.stdev(returns)*math.sqrt(periods)*100 if len(returns)>1 else None, 'sma20': sum(closes[-20:])/20 if len(closes)>=20 else None, 'sma50': sum(closes[-50:])/50 if len(closes)>=50 else None, 'rsi14': rsi}
    return {'quote': quote, 'metrics': metrics, 'method': f'Six-month source window; available daily closes; Wilder RSI 14; sample standard deviation of log returns annualized using {periods} sessions. Drawdown uses observed closes, not intraday lows. Price observations may include an incomplete latest session. No prediction, recommendation, fees, taxes or independently verified fundamentals.'}
