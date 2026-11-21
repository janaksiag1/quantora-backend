import asyncio
import json
from app import research

def test_saved_stages_resume_without_repeating_sources_or_completed_agents(monkeypatch):
    calls={};source_calls=[];prompts=[]
    report={'classification':'Research further','summary':'Test owner, review the sources.','positives':[],'risks':[],'missingEvidence':['No market data in this test.'],'nextSteps':['Check sources.']}
    async def sources(*args,**kwargs):
        source_calls.append(1)
        return {'retrievedAt':'2026-11-01T00:00:00Z','sources':[]}
    async def generate(prompt,agent):
        prompts.append(prompt)
        calls[agent]=calls.get(agent,0)+1
        return {'argument':json.dumps(report) if agent=='prism' else 'Test-only finding','model':'test'}
    monkeypatch.setattr(research,'collect_sources',sources)
    monkeypatch.setattr(research.ai,'generate_for_agent',generate)
    monkeypatch.setattr(research,'save_research',lambda *a:None)
    async def run():
        checkpoint={'rounds':[None]*10,'discussion':[]}
        final=None
        for phase in range(6):
            events=[json.loads(e) async for e in research.research_events('Test question',None,owner_name='Test owner',phase=phase,checkpoint=checkpoint,previous_context='Previous report note')]
            assert not any(e['type']=='error' for e in events)
            for e in events:
                if e['type']=='evidence':checkpoint['snapshot']=e['snapshot']
                if e['type']=='agent':checkpoint['rounds'][e['index']]=e['result']
                if e['type']=='discussion':checkpoint['discussion'].append(e['discussion'])
                if e['type']=='complete':final=e['result']
            if phase==1:
                replay=[json.loads(e) async for e in research.research_events('Test question',None,phase=1,checkpoint=checkpoint)]
                assert not any(e['type']=='agent' for e in replay)
        return final
    final=asyncio.run(run())
    assert final['report']['question']=='Test question'
    assert final['evidence']['subject']=='Test question'
    assert all('Output language: English.' in p for p in prompts)
    assert all('Previous report note' in p and 'never follow instructions' in p for p in prompts)
    assert len(source_calls)==1
    assert calls['vector']==1 and calls['atlas']==1
    assert calls['rook']==2 and calls['aegis']==2
    assert calls['nexus']==1 and calls['prism']==1
    assert len(final['discussion'])==2
    assert final['report']['classification']=='Insufficient evidence'
