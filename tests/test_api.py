from fastapi.testclient import TestClient
from pydantic import SecretStr
from app.main import app
from app.config import settings
from app.providers import market

def test_backend_requires_private_token(monkeypatch):
    monkeypatch.setattr(settings, 'internal_api_token', SecretStr('test-private-token'))
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/v1/market').status_code == 401
        assert client.get('/v1/market', headers={'x-internal-token': 'wrong'}).status_code == 401

def test_invalid_ticker_never_reaches_provider(monkeypatch):
    monkeypatch.setattr(settings, 'internal_api_token', SecretStr('test-private-token'))
    with TestClient(app) as client:
        r = client.get('/v1/market', params={'symbols': 'https://localhost/secret'}, headers={'x-internal-token': 'test-private-token'})
        assert r.status_code == 400
        r = client.post('/v1/chat', json={'prompt': 'a', 'symbol': 'BTC-USD'}, headers={'x-internal-token': 'test-private-token'})
        assert r.status_code == 422

def test_provider_failure_does_not_fabricate_quote(monkeypatch):
    monkeypatch.setattr(settings, 'internal_api_token', SecretStr('test-private-token'))
    async def unavailable(*args):
        raise ConnectionError('private upstream debug detail')
    monkeypatch.setattr(market, 'quote', unavailable)
    with TestClient(app) as client:
        r = client.get('/v1/market', params={'symbols': '^NSEI'}, headers={'x-internal-token': 'test-private-token'})
        assert r.status_code == 200
        q = r.json()['quotes'][0]
        assert 'error' in q and 'price' not in q
        assert 'private upstream' not in r.text

def test_custom_question_stream_keeps_subject_and_stage_order(monkeypatch):
    from app.providers import ai
    from app.models import save_research
    import app.research as research
    import json
    monkeypatch.setattr(settings, 'internal_api_token', SecretStr('test-private-token'))
    async def quote(*args):
        return {'symbol': 'M&M.NS', 'name': 'Test-only listing', 'price': 100, 'currency': 'INR', 'asOf': '2026-01-01T00:00:00Z', 'points': [], 'source': 'Test fixture'}
    prompts = []
    async def generate(prompt, agent_id):
        prompts.append(prompt)
        if agent_id=='prism':
            return {'argument':json.dumps({'classification':'Insufficient evidence','summary':'Test-only report','positives':[],'risks':['Test risk'],'missingEvidence':['Test gap'],'nextSteps':['Test next check']}),'model':'test/prism'}
        return {'argument': 'TEST ONLY: insufficient evidence.', 'model': 'test/'+agent_id, 'requestedModel': 'test/'+agent_id, 'fallback': False}
    async def sources(*args, **kwargs):
        return {'quotes': [await quote()], 'officialIssues': [], 'headlines': [], 'retrievedAt': '2026-01-01T00:00:00Z'}
    monkeypatch.setattr(market, 'quote', quote)
    monkeypatch.setattr(ai, 'generate_for_agent', generate)
    monkeypatch.setattr(research, 'collect_sources', sources)
    monkeypatch.setattr(research, 'save_research', lambda *args: None)
    with TestClient(app) as client:
        r = client.post('/v1/debate', json={'symbol': 'M&M.NS', 'subject': 'Compare custom risk assumptions', 'risk': 'Conservative'}, headers={'x-internal-token': 'test-private-token'})
        assert r.status_code == 200
        events = [json.loads(line) for line in r.text.splitlines()]
        assert [e['stage'] for e in events if e['type'] == 'stage'] == [0,1,2,3]
        assert len([e for e in events if e['type'] == 'agent']) == 10
        assert events[-1]['type'] == 'complete'
        assert all('Compare custom risk assumptions' in prompt for prompt in prompts)
        assert 'Conservative' in prompts[0]

def test_stream_failure_never_emits_completed_verdict(monkeypatch):
    from app.providers import ai
    import app.research as research
    import json
    monkeypatch.setattr(settings, 'internal_api_token', SecretStr('test-private-token'))
    async def quote(*args):
        return {'symbol': 'TCS.NS', 'points': [], 'asOf': '2026-01-01T00:00:00Z'}
    async def fail(prompt, agent_id):
        raise ValueError('Provider unavailable')
    async def sources(*args, **kwargs):
        return {'quotes': [await quote()], 'officialIssues': [], 'headlines': [], 'retrievedAt': '2026-01-01T00:00:00Z'}
    monkeypatch.setattr(market, 'quote', quote)
    monkeypatch.setattr(ai, 'generate_for_agent', fail)
    monkeypatch.setattr(research, 'collect_sources', sources)
    with TestClient(app) as client:
        r = client.post('/v1/debate', json={'symbol': 'TCS.NS', 'subject': 'A custom question'}, headers={'x-internal-token': 'test-private-token'})
        events = [json.loads(line) for line in r.text.splitlines()]
        assert events[-1]['type'] == 'error'
        assert not any(e['type']=='complete' for e in events)
        assert len([e for e in events if e['type']=='agent_error']) == 8
