"""A quote's session change must not use the first close of a chart range."""
import math
from datetime import datetime, timezone

def session_baseline(meta, points, period):
    def valid(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0
    for key in ('previousClose', 'regularMarketPreviousClose'):
        if valid(meta.get(key)): return meta[key]
    stamp = meta.get('regularMarketTime')
    offset = meta.get('gmtoffset') or 0
    if valid(stamp):
        session = datetime.fromtimestamp(stamp + offset, timezone.utc).date()
        prior = [p for p in points if valid(p.get('close')) and p.get('time', 0) <= stamp * 1000 and datetime.fromtimestamp(p['time'] / 1000 + offset, timezone.utc).date() < session]
        if prior: return max(prior, key=lambda p: p['time'])['close']
    # Only a one-session range establishes what chartPreviousClose means.
    return meta.get('chartPreviousClose') if period == '1d' and valid(meta.get('chartPreviousClose')) else None
