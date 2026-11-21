import asyncio
from app.ai_router import AIRouter, model_used
from app.agent_models import AGENT_MODELS


def test_every_role_uses_a_verified_model_family():
    assert len(AGENT_MODELS) == 10
    assert set(AGENT_MODELS.values()) <= {'gemini-3.1-flash-lite','gemini-3.5-flash-lite','gemini-3-flash-preview','gemini-3.6-flash','gemma-4-26b-a4b-it'}


def test_fallback_preserves_actual_model_and_discloses_request(monkeypatch):
    from pydantic import SecretStr
    from app.config import settings
    monkeypatch.setattr(settings,"groq_api_key",SecretStr(""))
    monkeypatch.setattr(settings,"openrouter_api_key",SecretStr(""))
    class Unavailable:
        async def generate(self, prompt, requested_model=None):
            raise ValueError('Free quota unavailable')

    router = AIRouter(Unavailable())

    async def fallback(prompt):
        model_used.set('test/actual-fallback')
        return 'TEST ONLY response'

    monkeypatch.setattr(router, 'generate', fallback)
    result = asyncio.run(router.generate_for_agent('Test prompt', 'nexus'))
    assert result['fallback'] is True
    assert result['model'] == 'test/actual-fallback'
    assert result['requestedModel'] == 'google/'+AGENT_MODELS['nexus']

def test_synthesis_and_verifier_can_use_configured_fast_provider(monkeypatch):
    from pydantic import SecretStr
    from app.config import settings
    monkeypatch.setattr(settings,'groq_api_key',SecretStr('TEST ONLY'))
    router=AIRouter(None)
    async def compatible(base,key,model,prompt):
        assert base=='https://api.groq.com/openai/v1'
        model_used.set('test/fast-model')
        return 'TEST ONLY answer'
    monkeypatch.setattr(router,'_compatible',compatible)
    for role in ['nexus','prism']:
        result=asyncio.run(router.generate_for_agent('Test only',role))
        assert result['model']=='test/fast-model'
