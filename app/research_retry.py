"""Bounded retries for research stages; never manufacture a successful result."""
import asyncio
import json
import re


def parse_report(response):
    raw=response['argument'].strip()
    raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw)
    report=json.loads(raw[raw.index('{'):raw.rindex('}')+1])
    if report.get('classification') not in ['Watch','Research further','High risk','Insufficient evidence'] or not isinstance(report.get('summary'),str) or not report['summary'].strip():
        raise ValueError('Invalid report')
    for key in ['positives','risks','missingEvidence','nextSteps']:
        if not isinstance(report.get(key),list) or not all(isinstance(v,str) for v in report[key]):
            raise ValueError('Invalid report fields')
    return report


async def retry_agent(operation, *, budget, on_retry=None, validate=None, delays=(1,2)):
    deadline=asyncio.get_running_loop().time()+budget
    for attempt in range(3):
        remaining=deadline-asyncio.get_running_loop().time()
        try:
            async with asyncio.timeout(min(max(remaining,0),budget/2)):
                result=await operation()
                if not isinstance(result,dict) or not isinstance(result.get('argument'),str) or not result['argument'].strip():
                    raise ValueError('Empty agent response')
                if validate:validate(result)
                return result
        except asyncio.CancelledError:
            raise
        except Exception:
            delay=delays[attempt] if attempt<len(delays) else 0
            if attempt==2 or deadline-asyncio.get_running_loop().time()<=delay+.05:
                raise
            if on_retry:on_retry(attempt+2)
            await asyncio.sleep(delay)
