"""A source-checked single analyst review, independent from the council workflow."""
import asyncio,json,re
from urllib.parse import unquote
from .source_research import collect_sources
from .providers import ai
from .research_retry import retry_agent,parse_report
from .report_checks import reviewed_report

async def ipo_brief(name,owner_name='',symbol=None):
    owner=re.sub(r'[\r\n<>]','',unquote(owner_name))[:60] or 'Investor'
    async with asyncio.timeout(75):
        evidence=await collect_sources(name,symbol,module='ipo')
        prompt=f'''You are Nova, an IPO research analyst. Give {owner} a concise first-pass review of {name}, independent of any council. Use ONLY the supplied retrieved evidence. Separate positive observations from downside considerations. GMP is unofficial, never a guaranteed profit. Do not infer business strengths from a price band or subscription count. Do not claim an RHP or financial statement was reviewed unless its excerpts are supplied. Cite supplied source IDs such as [S1]. Missing fundamentals must stay missing. Return ONLY JSON with classification (Watch, Research further, High risk, or Insufficient evidence), summary (start with {owner}, maximum 70 words), positives (array), risks (array), missingEvidence (array), nextSteps (array). No buy/apply advice, predictions or invented figures. EVIDENCE:{json.dumps(evidence)}'''
        generated=await retry_agent(lambda:ai.generate_for_agent(prompt,'nova'),budget=40,validate=parse_report)
        report,checks=reviewed_report(parse_report(generated),evidence,'ipo',owner)
        return {'analyst':'Nova','report':report,'checks':checks,'sources':evidence.get('sources',[]),'asOf':evidence.get('retrievedAt'),'scope':'Single-agent source review. It does not run the research council.'}
