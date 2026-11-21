import asyncio
from pydantic import SecretStr
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.source_research import matches, lookup_query


def test_company_matching_does_not_substitute_bls_international():
    assert matches('BLS polymer', 'BLS Polymers Limited')
    assert not matches('BLS polymer', 'BLS International Services')
    assert not matches('BLS polymer', 'BLS E-Services')
    assert lookup_query('TCS', [{'role': 'user', 'content': 'BLS polymer'}]) == 'tcs'
    assert lookup_query('BLS polymer IPO: review official issue facts and reported headlines') == 'bls polymer'


def test_chat_fetches_sources_without_attached_ticker(monkeypatch):
    import app.source_research as sources
    from app.providers import ai
    monkeypatch.setattr(settings, 'internal_api_token', SecretStr('test-private-token'))
    observed = []

    async def collect(prompt, symbol, history, **kwargs):
        observed.append((prompt, symbol))
        return {'officialIssues': [{'name': 'Test-only issuer'}], 'headlines': [], 'quotes': [],
                'sources': [{'title': 'Test-only source', 'url': 'https://www.nseindia.com/'}], 'retrievedAt': '2026-01-01T00:00:00Z'}

    async def generate(prompt):
        assert 'Test-only issuer' in prompt
        return 'TEST FIXTURE: The supplied issue record was retrieved.'

    monkeypatch.setattr(sources, 'collect_sources', collect)
    monkeypatch.setattr(ai, 'generate', generate)
    with TestClient(app) as client:
        response = client.post('/v1/chat', json={'prompt': 'BLS polymer'}, headers={'x-internal-token': 'test-private-token'})
    assert response.status_code == 200
    assert observed == [('BLS polymer', None)]
    assert 'https://www.nseindia.com/' in response.json()['answer']
    assert '1 public observations' in response.json()['source']
