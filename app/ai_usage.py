"""Provider-reported observations only; missing cost is never converted to zero."""
import json
import math
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from .models import Session, ResearchAudit, research_owner

request_usage = ContextVar('gainbud_ai_usage', default=None)

def normalize_usage(provider, model, payload):
    raw = payload.get('usageMetadata') if provider == 'Google' else payload.get('usage')
    if not isinstance(raw, dict):
        raw = {}
    def number(key):
        value = raw.get(key)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None
    return {'provider': provider, 'model': str(model)[:160],
            'inputTokens': number('promptTokenCount' if provider == 'Google' else 'prompt_tokens'),
            'outputTokens': number('candidatesTokenCount' if provider == 'Google' else 'completion_tokens'),
            'totalTokens': number('totalTokenCount' if provider == 'Google' else 'total_tokens'),
            'reportedCostUSD': number('cost') if provider == 'OpenRouter' else None,
            'observedAt': datetime.now(timezone.utc).isoformat()}

def record_usage(provider, model, payload):
    observation = normalize_usage(provider, model, payload)
    events = request_usage.get()
    if isinstance(events, list):
        events.append(observation)
    try:
        with Session.begin() as db:
            db.add(ResearchAudit(symbol='AI-USAGE', source='provider-usage-v1', user_id=research_owner.get(), payload=json.dumps(observation)))
    except Exception:
        logging.getLogger('gainbud.usage').warning('Provider usage could not be persisted')
    return observation

def summarize_usage(payloads):
    totals={}
    for raw in payloads:
        try:
            r=json.loads(raw)
            if not isinstance(r,dict) or not isinstance(r.get('provider'),str) or not isinstance(r.get('model'),str):
                continue
            key=(r['provider'],r['model'])
            t=totals.setdefault(key,{'provider':key[0][:80],'model':key[1][:160],'calls':0,'tokens':0,'unknownTokenCalls':0,'knownCostUSD':0,'costUnknown':0})
            t['calls']+=1
            for field,target,unknown in [('totalTokens','tokens','unknownTokenCalls'),('reportedCostUSD','knownCostUSD','costUnknown')]:
                value=r.get(field)
                if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0:
                    t[target]+=value
                else:
                    t[unknown]+=1
        except (ValueError,TypeError):
            continue
    return list(totals.values())
