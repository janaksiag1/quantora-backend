import asyncio
import json
import pytest
from app.research_retry import retry_agent,parse_report


def test_retry_succeeds_on_third_attempt_and_announces_only_two_retries():
    async def run():
        calls=[];notices=[]
        async def operation():
            calls.append(1)
            if len(calls)<3:raise ConnectionError('temporary')
            return {'argument':'Recovered finding'}
        result=await retry_agent(operation,budget=2,delays=(0,0),on_retry=notices.append)
        assert len(calls)==3 and notices==[2,3]
        assert result['argument']=='Recovered finding'
    asyncio.run(run())


def test_failed_or_empty_responses_exhaust_retries_without_fake_success():
    async def run():
        calls=[]
        async def operation():calls.append(1);return {'argument':''}
        with pytest.raises(ValueError):await retry_agent(operation,budget=2,delays=(0,0))
        assert len(calls)==3
    asyncio.run(run())


def test_cancellation_never_restarts_an_agent():
    async def run():
        started=asyncio.Event();calls=[]
        async def operation():calls.append(1);started.set();await asyncio.sleep(30)
        task=asyncio.create_task(retry_agent(operation,budget=40,delays=(0,0)))
        await started.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert len(calls)==1
    asyncio.run(run())


@pytest.mark.parametrize('permanent_verification_failure',[False,True])
def test_council_recovers_specialists_synthesis_and_malformed_verification(monkeypatch,permanent_verification_failure):
    from app import research
    calls={}
    report={'classification':'Research further','summary':'QA owner, review evidence gaps.','positives':[],'risks':[],'missingEvidence':['QA fixture contains no market observations.'],'nextSteps':['Verify official sources.']}
    async def sources(*args,**kwargs):return {'retrievedAt':'2026-11-01T00:00:00Z','sources':[]}
    async def generate(prompt,agent):
        calls[agent]=calls.get(agent,0)+1
        if agent=='prism' and permanent_verification_failure:return {'argument':'not valid JSON'}
        if calls[agent]==1:
            if agent=='prism':return {'argument':'not valid JSON'}
            raise ConnectionError('temporary provider failure')
        return {'argument':json.dumps(report) if agent=='prism' else 'QA-only analyst response','model':'test'}
    async def quick(operation,**kwargs):return await retry_agent(operation,**kwargs,delays=(0,0))
    monkeypatch.setattr(research,'collect_sources',sources)
    monkeypatch.setattr(research.ai,'generate_for_agent',generate)
    monkeypatch.setattr(research,'retry_agent',quick)
    monkeypatch.setattr(research,'save_research',lambda *args:None)
    async def run():return [json.loads(item) async for item in research.research_events('QA research',None,owner_name='QA owner')]
    events=asyncio.run(run())
    if permanent_verification_failure:
        assert events[-1]['type']=='error'
        assert not any(e['type']=='complete' for e in events)
        assert len([e for e in events if e['type']=='agent'])==9
        assert calls['prism']==3
        return
    assert events[-1]['type']=='complete'
    assert {e['index'] for e in events if e['type']=='agent_retry'}==set(range(10))
    assert len([e for e in events if e['type']=='agent'])==10
    assert not any(e['type']=='agent_error' for e in events)
    assert events[-1]['result']['report']['classification']=='Insufficient evidence'
    assert calls['nexus']==2 and calls['prism']==2


def test_verifier_rejects_wrong_schema():
    with pytest.raises(ValueError):parse_report({'argument':'{"classification":"Buy","summary":"guaranteed"}'})


def test_retry_time_budget_does_not_multiply_with_attempts():
    async def run():
        started=asyncio.get_running_loop().time();calls=[]
        async def operation():calls.append(1);await asyncio.sleep(1)
        with pytest.raises(TimeoutError):await retry_agent(operation,budget=.2,delays=(0,0))
        assert asyncio.get_running_loop().time()-started<.5
        assert 1<=len(calls)<=3
    asyncio.run(run())
