"""Bounded, deterministic research calculations. No orders, network or filesystem I/O.

Setup definitions adapted from day-trader-skill-nse (MIT, Jake Schincariol).
See docs/third-party/day-trader-LICENSE.txt. No upstream CLI is executed.
"""
import hashlib
import json
import math
import random
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def candles(rows, now=None, interval=86400):
    now = now or datetime.now(timezone.utc)
    out = {}
    for row in rows:
        try:
            t = float(row['time']) / 1000
            values = {k: float(row[k]) for k in ('open', 'high', 'low', 'close')}
            if not all(math.isfinite(v) and v > 0 for v in values.values()):
                continue
            if values['high'] < max(values.values()) or values['low'] > min(values.values()):
                continue
            local = datetime.fromtimestamp(t, IST)
            complete = t + interval <= now.timestamp() if interval < 86400 else (local.date() < now.astimezone(IST).date() or (local.date() == now.astimezone(IST).date() and now.astimezone(IST).hour * 60 + now.astimezone(IST).minute >= 930))
            if not complete or t > now.timestamp():
                continue
            if interval < 86400 and not (555 <= local.hour * 60 + local.minute < 930):
                continue
            try:
                volume=float(row['volume']) if row.get('volume') is not None else None
                if volume is not None and (not math.isfinite(volume) or volume<0):volume=None
            except (ValueError,TypeError):volume=None
            out[t] = {'time': int(t * 1000), **values, 'volume': volume}
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
    return [out[t] for t in sorted(out)]


def rsi(values, length=14):
    if len(values) <= length:
        return None
    differences = [b-a for a, b in zip(values, values[1:])]
    up = sum(max(0, d) for d in differences[:length]) / length
    down = sum(max(0, -d) for d in differences[:length]) / length
    for d in differences[length:]:
        up = (up*(length-1)+max(d, 0))/length
        down = (down*(length-1)+max(-d, 0))/length
    return 100 - 100/(1+up/down) if down else (100.0 if up else 50.0)


def setups(rows, momentum=3, oversold=30):
    c = [r['close'] for r in rows]
    if len(c) < 30:
        return {'state': 'unavailable', 'reason': 'At least 30 completed daily candles are required.', 'signals': []}
    ma = sum(c[-20:])/20
    strength = rsi(c)
    move = (c[-1]/c[-6]-1)*100
    tr = [max(r['high']-r['low'], abs(r['high']-p['close']), abs(r['low']-p['close'])) for p, r in zip(rows[-15:-1], rows[-14:])]
    signals = []
    if c[-1] > max(c[-21:-1]): signals.append('breakout_20d')
    if move >= momentum and c[-1] > ma: signals.append('momentum')
    if rsi(c[:-1]) < oversold and c[-1] > c[-2]: signals.append('oversold_bounce')
    if c[-2] < sum(c[-21:-1])/20 and c[-1] > ma: signals.append('reclaim_ma20')
    return {'state': 'ready', 'signals': signals, 'rsi14': strength, 'ma20': ma, 'momentum5d': move, 'atr14': sum(tr)/len(tr), 'asOf': rows[-1]['time']}


def opening_range(rows):
    if not rows: return {'state': 'unavailable', 'reason': 'No completed five-minute candles.'}
    day = datetime.fromtimestamp(rows[-1]['time']/1000, IST).date()
    session = [r for r in rows if datetime.fromtimestamp(r['time']/1000, IST).date() == day]
    minutes = [datetime.fromtimestamp(r['time']/1000, IST).hour*60+datetime.fromtimestamp(r['time']/1000, IST).minute for r in session]
    if minutes[:3] != [555, 560, 565] or len(session) < 4:
        return {'state': 'unavailable', 'reason': 'Complete 09:15–09:30 opening range and a confirmation bar required.', 'session': str(day)}
    if any(b-a != 300000 for a,b in zip([r['time'] for r in session], [r['time'] for r in session][1:])):
        return {'state': 'unavailable', 'reason': 'Session has missing five-minute candles.', 'session': str(day)}
    high, low = max(r['high'] for r in session[:3]), min(r['low'] for r in session[:3])
    confirmed = next((r for r in session[3:] if r['close'] > high), None)
    return {'state': 'confirmed' if confirmed else 'waiting', 'high': high, 'low': low, 'session': str(day), 'confirmedAt': confirmed['time'] if confirmed else None}


def size_position(capital, risk_pct, entry, stop, target, allocation_pct=25, costs_bps=10):
    if not all(math.isfinite(v) for v in [capital, risk_pct, entry, stop, target, allocation_pct, costs_bps]) or not (capital > 0 and 0 < risk_pct <= 10 and 0 < stop < entry < target and 0 < allocation_pct <= 100 and 0 <= costs_bps <= 200):
        raise ValueError('Use positive capital and stop < entry < target; risk 0–10%, allocation 0–100%.')
    cost = (entry+stop)*costs_bps/10000
    risk = entry-stop+cost
    qty = max(0, min(math.floor(capital*risk_pct/100/risk), math.floor(capital*allocation_pct/100/(entry*(1+costs_bps/10000)))))
    reward = target-entry-(entry+target)*costs_bps/10000
    return {'quantity': qty, 'riskBudget': capital*risk_pct/100, 'estimatedLoss': qty*risk, 'estimatedReward': qty*reward, 'rewardRisk': reward/risk, 'capitalRequired': qty*entry*(1+costs_bps/10000), 'costsBpsPerSide': costs_bps, 'assumptions': 'Long-only, whole shares; modeled all-in costs per side. Gaps can exceed the planned loss.'}


def outcome(rows, entry, stop, target, costs_bps):
    for r in rows:
        if r['open'] <= stop: return r['open'], 'gap_stop'
        if r['open'] >= target: return target, 'target'
        if r['low'] <= stop: return stop, 'stop'  # stop first if both hit intrabar
        if r['high'] >= target: return target, 'target'
    return rows[-1]['close'], 'horizon'


def time_machine(rows, entry, stop, target, seed=19, paths=1000, horizon=10, costs_bps=10, as_of=None):
    if not 0 < stop < entry < target: raise ValueError('Require stop < entry < target.')
    if not 100 <= paths <= 5000 or not 1 <= horizon <= 30: raise ValueError('Bounded paths 100–5000 and horizon 1–30.')
    # Daily provider timestamps mark the opening of a bar, not availability of
    # its closing price. Never admit that day's OHLC before the NSE close.
    last_close = datetime.fromtimestamp(rows[-1]['time']/1000, IST).replace(hour=15, minute=30, second=0, microsecond=0) if rows else None
    cutoff = int(as_of) if as_of is not None else int(last_close.timestamp()*1000) if last_close else 0
    if cutoff > int(datetime.now(timezone.utc).timestamp()*1000): raise ValueError('Historical cutoff cannot be in the future.')
    sample = candles(rows, datetime.fromtimestamp(cutoff/1000, timezone.utc))
    if len(sample) < max(40, horizon+22): raise ValueError('Not enough completed history before the selected cutoff.')
    pool = [(r['open']/p['close'], r['high']/p['close'], r['low']/p['close'], r['close']/p['close']) for p,r in zip(sample, sample[1:])]
    rng = random.Random(seed)
    results, chart = [], []
    for n in range(paths):
        price, simulated = entry, []
        for _ in range(horizon):
            o,h,l,c = rng.choice(pool)
            simulated.append({'open':price*o, 'high':price*h, 'low':price*l, 'close':price*c})
            price *= c
        exit_price, kind = outcome(simulated, entry, stop, target, costs_bps)
        net = exit_price-entry-(entry+exit_price)*costs_bps/10000
        results.append({'returnPct': net/entry*100, 'exit': kind})
        if n < 12: chart.append([entry]+[round(r['close'], 4) for r in simulated])
    # Walk-forward 20-day breakout: each signal only sees preceding candles.
    replay, i = [], 21
    while i+1 < len(sample):
        if sample[i]['close'] > max(r['close'] for r in sample[i-20:i]):
            fill = sample[i+1]['open']
            risk_pct = (entry-stop)/entry
            s, t = fill*(1-risk_pct), fill*(1+(target-entry)/entry)
            forward = sample[i+1:i+1+horizon]
            if len(forward) < horizon: break
            exited, kind = outcome(forward, fill, s, t, costs_bps)
            replay.append({'signalAt': sample[i]['time'], 'entryAt': forward[0]['time'], 'entry': fill, 'exit': exited, 'reason': kind, 'netPct': (exited-fill-(fill+exited)*costs_bps/10000)/fill*100})
            i += horizon+1
        else: i += 1
    values = sorted(r['returnPct'] for r in results)
    return {'seed': seed, 'paths': paths, 'horizon': horizon, 'cutoff': cutoff, 'sampleBars': len(sample), 'dataHash': hashlib.sha256(json.dumps(sample, sort_keys=True).encode()).hexdigest(), 'modelVersion': 'gb-bootstrap-2', 'positivePathsPct': sum(v>0 for v in values)/paths*100, 'p05': values[int(paths*.05)], 'median': values[paths//2], 'p95': values[int(paths*.95)], 'samplePaths': chart, 'historicalTrades': replay, 'assumptions': ['Daily OHLC bootstrap sampled with replacement; independent bars do not preserve regime or volatility clustering.', 'Only candles at/before cutoff used. Known opening gaps are handled first; stops win ambiguous intrabar touches.', 'Long only; no leverage. Gap stops fill at opening price. Targets capped at target.', f'{costs_bps} basis points modeled costs per side; no liquidity, taxes or corporate-action adjustment guarantee.', 'Historical replay: 20-day closing breakout, next-session open, non-overlapping trades, same stop/target percentages. Not a backtest of every scanner setup.', 'Simulated frequencies are not calibrated probabilities or guaranteed predictions.']}
