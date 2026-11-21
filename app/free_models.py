"""Current zero-price OpenRouter discovery. Never route paid models implicitly."""
import time
import httpx
from .config import settings
_cache=(0,[])
async def free_models():
 global _cache
 if time.monotonic()-_cache[0]<3600 and _cache[1]:return _cache[1]
 async with httpx.AsyncClient(timeout=10) as c:
  r=await c.get('https://openrouter.ai/api/v1/models');r.raise_for_status()
 models=[{'id':m['id'],'name':m.get('name',m['id'])} for m in r.json().get('data',[]) if float(m.get('pricing',{}).get('prompt','1'))==0 and float(m.get('pricing',{}).get('completion','1'))==0 and m.get('architecture',{}).get('output_modalities',['text'])==['text'] and 'safety' not in m['id'] and 'code' not in m['id']]
 _cache=(time.monotonic(),models)
 return models
async def free_candidates():
 models=await free_models()
 desired=[m.strip() for m in settings.openrouter_models.split(',') if m.strip()]
 allowed={m['id'] for m in models}
 selected=[m for m in desired if m in allowed or m=='openrouter/free']
 for family in ['nvidia/','qwen/','google/gemma']:
  match=next((m['id'] for m in models if m['id'].startswith(family) and 'omni' not in m['id']),None)
  if match and match not in selected:selected.append(match)
 return selected[:4]
