import pytest
import asyncio
from app import source_research

@pytest.mark.parametrize('prompt', ['Can you tell me what is IPO?', 'What is an IPO?', 'IPO kya hai?'])
def test_ipo_definition_does_not_search_unrelated_news(monkeypatch, prompt):
    async def unwanted(*args, **kwargs):
        raise AssertionError('Educational definition must not request company sources')
    monkeypatch.setattr(source_research, 'search_assets', unwanted)
    monkeypatch.setattr(source_research, 'company_news', unwanted)
    evidence = asyncio.run(source_research.collect_sources(prompt))
    assert evidence['educational'] is True
    assert evidence['sources'] == []
    assert evidence['headlines'] == []
