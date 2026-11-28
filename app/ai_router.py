import asyncio
import hashlib
import os
from contextvars import ContextVar
import httpx
from .config import settings
from .agent_policy import TEMPERATURE, active_persona, system_prompt

model_used = ContextVar('quantora_model', default='')
SYSTEM = system_prompt()

class ProviderError(ValueError):
    def __init__(self,status,retry_after=0):
        super().__init__(f'Provider HTTP {status}')
        self.status=status
        self.retry_after=retry_after

class AIRouter:
    def __init__(self, gemini):
        self.gemini = gemini
        self.semaphore = asyncio.Semaphore(4)
        self.cooldowns = {}

    async def generate_for_agent(self, prompt, agent_id):
        token = active_persona.set(agent_id)
        try:
            return await self._generate_for_agent(prompt, agent_id)
        finally:
            active_persona.reset(token)

    async def _generate_for_agent(self, prompt, agent_id):
        import json
        import time
        from .agent_models import AGENT_MODELS
        mapping = dict(AGENT_MODELS)
        if settings.agent_models_json:
            mapping.update(json.loads(settings.agent_models_json))
        requested = mapping.get(agent_id, settings.gemini_model)
        primary_failed = False
        # Distribute roles across verified configured services instead of spending
        # every specialist call on the small shared OpenRouter free daily allowance.
        if settings.groq_api_key.get_secret_value() and agent_id in ('vector','atlas','aegis','echo','nexus','prism'):
            try:
                models=[m.strip() for m in settings.groq_models.split(',') if m.strip()]
                selected=models[list(mapping).index(agent_id)%len(models)]
                async with asyncio.timeout(12):
                    answer=await self._compatible('https://api.groq.com/openai/v1',settings.groq_api_key.get_secret_value(),selected,prompt)
                return {'argument':answer,'model':model_used.get(),'requestedModel':selected,'fallback':False}
            except Exception:primary_failed=True
        if settings.openrouter_api_key.get_secret_value():
            try:
                from .free_models import free_candidates
                candidates=await free_candidates()
                if candidates:
                    selected=candidates[list(mapping).index(agent_id)%len(candidates)]
                    async with asyncio.timeout(10):
                        answer=await self._compatible('https://openrouter.ai/api/v1',settings.openrouter_api_key.get_secret_value(),selected,prompt)
                    return {'argument':answer,'model':model_used.get(),'requestedModel':selected,'fallback':False}
            except Exception:
                primary_failed=True
        if self.cooldowns.get('agent:'+requested, 0) <= time.monotonic():
            try:
                async with asyncio.timeout(12):
                    answer = await self.gemini.generate(prompt, requested_model=requested)
                return {'argument': answer, 'model': model_used.get(), 'requestedModel': 'google/'+requested, 'fallback': False}
            except Exception:
                primary_failed = True
                self.cooldowns['agent:'+requested] = time.monotonic()+300
        else:
            primary_failed = True
        # Keep a specialist usable when its requested free model is unavailable.
        # This is disclosed; fallback does not count as another distinct model.
        async with asyncio.timeout(30):
            answer = await self.generate(prompt)
        return {'argument': answer, 'model': model_used.get(), 'requestedModel': 'google/'+requested, 'fallback': primary_failed}

    async def _compatible(self, base, token, model, prompt):
        payload={'model': model, 'messages': [{'role':'system','content':system_prompt()},{'role':'user','content':prompt}], 'max_tokens': 2200, 'temperature': TEMPERATURE}
        if base.startswith('https://openrouter.ai/'):
            payload['reasoning']={'effort':'none','exclude':True}
        async with httpx.AsyncClient(timeout=14) as client:
            r = await client.post(base+'/chat/completions', headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'}, json=payload)
        if not r.is_success:
            try: retry_after=min(3600,max(0,int(r.headers.get('Retry-After','0'))))
            except ValueError: retry_after=60
            raise ProviderError(r.status_code,retry_after)
        data = r.json()
        from .ai_usage import record_usage
        provider = 'OpenRouter' if 'openrouter.ai' in base else 'Groq' if 'groq.com' in base else 'Vercel Gateway' if 'vercel.sh' in base else 'Compatible provider'
        record_usage(provider, data.get('model') or model, data)
        content = data.get('choices',[{}])[0].get('message',{}).get('content')
        if not isinstance(content,str) or not content.strip():
            raise ValueError('Provider returned no answer')
        model_used.set(data.get('model') or model)
        return content.strip()

    async def generate(self, prompt):
        import time
        errors = []
        # Prefer the dedicated free-tier Gemini project before Gateway providers.
        if settings.gemini_api_key_tertiary.get_secret_value():
            try:
                async with asyncio.timeout(12):
                    return await self.gemini.generate(prompt)
            except Exception:
                errors.append('Gemini unavailable')
        gateway_token = settings.ai_gateway_api_key.get_secret_value() or settings.vercel_oidc_token.get_secret_value() or os.getenv('VERCEL_OIDC_TOKEN','')
        candidates = []
        if gateway_token:
            models = [m.strip() for m in settings.ai_gateway_models.split(',') if m.strip()]
            # Rotate the starting model per specialist rather than claiming one model is many.
            if models:
                offset = int(hashlib.sha256(prompt[:120].encode()).hexdigest()[:4],16)%len(models)
                models = models[offset:]+models[:offset]
            candidates += [('Vercel AI Gateway','https://ai-gateway.vercel.sh/v1',gateway_token,m) for m in models]
        if settings.openrouter_api_key.get_secret_value():
            try:
                from .free_models import free_candidates
                candidates += [('OpenRouter','https://openrouter.ai/api/v1',settings.openrouter_api_key.get_secret_value(),m) for m in await free_candidates()]
            except Exception:pass
        if settings.groq_api_key.get_secret_value():
            candidates.append(('Groq','https://api.groq.com/openai/v1',settings.groq_api_key.get_secret_value(),settings.groq_model))
        if settings.cloudflare_api_token.get_secret_value() and settings.cloudflare_account_id:
            # Account identifiers are server configuration, never user-supplied URLs.
            if settings.cloudflare_account_id.isalnum():
                candidates.append(('Cloudflare','https://api.cloudflare.com/client/v4/accounts/'+settings.cloudflare_account_id+'/ai/v1',settings.cloudflare_api_token.get_secret_value(),settings.cloudflare_model))
        # Catalog trial access alone does not license production use.
        if settings.nvidia_production_entitled and settings.nvidia_api_key.get_secret_value():
            candidates.append(('NVIDIA','https://integrate.api.nvidia.com/v1',settings.nvidia_api_key.get_secret_value(),settings.nvidia_model))
        if settings.ollama_url.startswith('https://') and settings.ollama_api_key.get_secret_value():
            candidates.append(('Ollama',settings.ollama_url.rstrip('/')+'/v1',settings.ollama_api_key.get_secret_value(),settings.ollama_model))
        # One slow gateway family must not consume every fallback opportunity.
        provider_order=['Groq','Cloudflare','OpenRouter','Ollama','NVIDIA','Vercel AI Gateway']
        candidates.sort(key=lambda c:provider_order.index(c[0]))
        async with self.semaphore:
            for provider, base, token, model in candidates:
                if self.cooldowns.get(model,0)>time.monotonic() or self.cooldowns.get('provider:'+provider,0)>time.monotonic():
                    continue
                try:
                    return await self._compatible(base,token,model,prompt)
                except Exception as exc:
                    errors.append(provider+' unavailable')
                    status=getattr(exc,'status',0)
                    delay=max(45,getattr(exc,'retry_after',0))
                    self.cooldowns[model]=time.monotonic()+delay
                    if status in (401,403):
                        self.cooldowns['provider:'+provider]=time.monotonic()+3600
                    elif status==429:
                        self.cooldowns['provider:'+provider]=time.monotonic()+max(60,delay)
            if not settings.gemini_api_key_tertiary.get_secret_value() and any(key.get_secret_value() for key in [settings.gemini_api_key, settings.gemini_api_key_secondary]):
                try:
                    result=await self.gemini.generate(prompt)
                    model_used.set('google/'+settings.gemini_model)
                    return result
                except Exception:
                    errors.append('Gemini unavailable')
            if settings.ollama_url and not os.getenv('VERCEL'):
                try:
                    async with httpx.AsyncClient(timeout=45) as client:
                        r=await client.post(settings.ollama_url.rstrip('/')+'/api/chat',json={'model':settings.ollama_model,'stream':False,'options':{'temperature':TEMPERATURE},'messages':[{'role':'system','content':system_prompt()},{'role':'user','content':prompt}]})
                        r.raise_for_status()
                    answer=r.json().get('message',{}).get('content','')
                    if answer:
                        model_used.set('ollama/'+settings.ollama_model)
                        return answer
                except Exception:
                    errors.append('Ollama unavailable')
        raise ValueError('No configured AI provider is currently available. '+('; '.join(dict.fromkeys(errors)) if errors else 'Configure a server-side AI provider.'))
