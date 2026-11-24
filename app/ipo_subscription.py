import math
import re

def number(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(',', '').rstrip('xX×').strip()
    if not re.fullmatch(r'\d+(?:\.\d+)?', text):
        return None
    n = float(text)
    return n if math.isfinite(n) and n >= 0 else None

def subscription_value(row):
    for key in ('subscription', 'noOfTime', 'noOfTimes', 'timesSubscribed', 'subscriptionTimes'):
        value = number(row.get(key))
        if value is not None:
            return value
    offered = number(row.get('offeredShares', row.get('noOfSharesOffered')))
    bids = number(row.get('sharesBid', row.get('noOfsharesBid', row.get('noOfSharesBid'))))
    return bids / offered if offered is not None and offered > 0 and bids is not None else None
