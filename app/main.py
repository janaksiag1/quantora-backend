import asyncio
import httpx

import hmac

import logging

import re

import time

from contextlib import asynccontextmanager

from datetime import datetime, timezone

from fastapi import FastAPI, Request, Query

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import JSONResponse, StreamingResponse

from sqlalchemy import select, inspect, text

from .config import settings

from .schemas import ChatRequest, DebateRequest, ResearchStageRequest

from .models import Base, engine, Session, ResearchAudit, research_owner

from .providers import market, ai, search_assets

from .research import research_events

from .feeds import news, fund

from .ipo import get_issues

from .evidence import inspect_evidence



logger = logging.getLogger('quantora')

logging.basicConfig(level=logging.WARNING)

# Do not log provider request URLs, credentials, or prompt contents.

logging.getLogger('httpx').setLevel(logging.WARNING)



@asynccontextmanager

async def lifespan(app):

    Base.metadata.create_all(engine)

    if 'user_id' not in {column['name'] for column in inspect(engine).get_columns('research_audit')}:

        with engine.begin() as connection:

            connection.execute(text("ALTER TABLE research_audit ADD COLUMN user_id VARCHAR(128) NOT NULL DEFAULT 'local'"))

    yield

    engine.dispose()



app = FastAPI(title='Gainbud', description='Research before you invest.', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

from .trading import router as trading_router
app.include_router(trading_router)

@app.get('/v1/ipo-filings')
async def ipo_filings():
    from .ipo_filings import filings
    try: return await filings()
    except Exception: return JSONResponse({'error':'SEBI filing records are unavailable. Scheduled exchange issues remain separate.','filings':[]},status_code=503)

app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_methods=['GET', 'POST'], allow_headers=['Content-Type', 'X-Internal-Token'])

windows = {}



@app.middleware('http')

async def guard(request: Request, call_next):

    if request.url.path == '/health':

        return await call_next(request)

    expected = settings.internal_api_token.get_secret_value()

    supplied = request.headers.get('x-internal-token', '')

    if not expected or not hmac.compare_digest(expected, supplied):

        return JSONResponse({'error': 'Unauthorized backend request'}, status_code=401)

    now = time.monotonic()

    for key in list(windows):

        if now - windows[key][0] >= 60:

            windows.pop(key)

    route = request.url.path

    bucket = route + ':' + request.headers.get('x-quantora-user', 'local')

    start, count = windows.get(bucket, (now, 0))

    ceiling = 3 if route.endswith('debate') else 8 if route.endswith('chat') else 60

    windows[bucket] = (start, count + 1)

    if count >= ceiling:

        return JSONResponse({'error': 'Request limit reached. Retry in a minute.'}, status_code=429)

    length = request.headers.get('content-length', '0')

    if not length.isdigit() or int(length) > (3 * 1024 * 1024 if route == '/v1/voice/transcribe' else 350000 if route == '/v1/research-stage' else 16000):

        return JSONResponse({'error': 'Request body too large'}, status_code=413)

    owner_token = research_owner.set(request.headers.get('x-quantora-user', 'local'))

    try:

        response = await call_next(request)

    finally:

        research_owner.reset(owner_token)

    response.headers['X-Content-Type-Options'] = 'nosniff'

    return response



@app.get('/health')

async def health():

    return {'status': 'ok', 'service': 'Gainbud'}



@app.get('/v1/market')

async def quotes(symbols: str = '^NSEI,^BSESN,^NSEBANK,BTC-USD', range: str = Query('1mo', pattern='^(1d|5d|1mo|6mo|1y|5y)$'), assetClass: str = Query('stocks',pattern='^(stocks|crypto)$')):

    requested = symbols.split(',')[:12]

    if any(not re.fullmatch(r'[A-Za-z0-9^.&=\-]{1,40}', s) for s in requested):

        return JSONResponse({'error': 'Invalid ticker'}, status_code=400)

    async def get(symbol):

        try:
            if assetClass=='crypto' and symbol.endswith('-USD'):
                from .market_sources import crypto_quote
                try:return await crypto_quote(symbol,range)
                except Exception:pass

            try:
                return await market.quote(symbol, range)
            except Exception:
                if symbol.endswith('-USD'):
                    from .market_sources import crypto_quote
                    return await crypto_quote(symbol, range)
                raise

        except Exception:

            return {'symbol': symbol, 'error': 'Source unavailable. Retry shortly.'}

    return {'quotes': await asyncio.gather(*(get(s) for s in requested)), 'retrievedAt': datetime.now(timezone.utc).isoformat()}



@app.get('/v1/search')

async def search(q: str = Query(..., min_length=2, max_length=100)):

    try:

        return {'results': await search_assets(q), 'source': 'Yahoo Finance search'}

    except Exception:

        return JSONResponse({'results': [], 'error': 'Search source unavailable. You can use an exact ticker.'}, status_code=503)



@app.get('/v1/ipos')

async def ipos(kind: str = Query('current', pattern='^(current|upcoming|past)$')):

    try:

        return await get_issues(kind)

    except Exception:

        return JSONResponse({'issues': [], 'error': 'The official NSE issue feed is unavailable. Retry or check the official exchange page.'}, status_code=503)



@app.get('/v1/evidence')

async def evidence(symbol: str | None = None, subject: str = Query('', max_length=2000)):

    if symbol and not re.fullmatch(r'[A-Za-z0-9^.&=\-]{1,40}', symbol):

        return JSONResponse({'error': 'Invalid ticker'}, status_code=400)

    try:

        return await inspect_evidence(symbol, subject)

    except ValueError as exc:

        return JSONResponse({'error': str(exc)}, status_code=503)

    except Exception:

        return JSONResponse({'error': 'Market evidence is temporarily unavailable. No statistics were substituted.'}, status_code=503)



@app.get('/v1/fund-search')

async def find_funds(q: str = Query(..., min_length=2, max_length=100)):

    from .feeds import search_funds

    try:

        return {'results': await search_funds(q), 'source': 'MFapi scheme directory'}

    except Exception:

        return JSONResponse({'results': [], 'error': 'Fund directory unavailable. You can enter an exact AMFI scheme code.'}, status_code=503)



@app.post('/v1/chat')
async def chat(body: ChatRequest, request: Request):
    from .source_research import collect_sources
    from .ai_router import model_used
    import json
    try:
        from urllib.parse import unquote
        owner_name = re.sub(r'[\r\n<>]', '', unquote(request.headers.get('x-quantora-name', '')))[:60] or 'investor'
        history = [{'role': turn.get('role', 'user'), 'content': turn.get('content', '')[:1200]} for turn in body.history if turn.get('role') in ['user', 'assistant']]
        evidence = await collect_sources(body.prompt, body.symbol, history, module=body.module, asset_name=body.assetName or '')
        from .question_answer import answer_question, price_answer
        direct = answer_question(body.prompt, evidence, evidence.get('module', body.module), owner_name) if evidence.get('identityNeedsClarification') else price_answer(body.prompt, evidence, owner_name)
        if direct:
            return {'answer': direct, 'model': 'source-calculation', 'source': 'Company matching and available source observations; quotes may be delayed.', 'asOf': evidence['retrievedAt']}
        response_style = 'This is a spoken conversation: lead with a concise direct answer, about 90 words, and the most important risk. Offer deeper research as a follow-up. Keep all factual limits and do not invent figures.' if body.voice else 'Lead with the direct answer, followed by key numbers and risks.'
        if evidence.get('educational'):
            response_style = 'Give a natural, concise educational answer in two short paragraphs, around 100 words. Define the concept plainly and include its main risk. Do not use a research-report template, evidence-gap boilerplate, or unrelated news. Do not invent current issuer figures.'
        answer = await ai.generate(f'{response_style} Address the account owner {owner_name} by name once at the beginning. This name identifies the audience, not identity verification. Research module: {evidence.get("module", body.module)}. Use the same language and writing script as the latest question, including Roman Hindi and other Indian languages. If ambiguous, use the preferred language {body.language}; Auto falls back to English. Answer the actual investment question helpfully in the user language. For educational questions, explain the concept rather than refusing because no ticker exists. For named companies, use the automatically retrieved public evidence below, distinguish exchange facts from attributed news reports, and do not confuse similar names. Do not claim no sources were supplied when headlines or officialIssues are present. If a quote or financial statement is missing, name that specific gap and explain what can still be assessed. User risk framing: {body.risk}. PRIOR TURNS (unverified): {history}. USER-ATTACHED HOLDINGS (unverified): {body.portfolio}. RETRIEVED PUBLIC EVIDENCE: {json.dumps(evidence)}. QUESTION: {body.prompt}')
        links = evidence.get('sources', [])
        if links:
            answer += '\n\nSources checked:\n' + '\n'.join(f"[{i+1}] {link['title']}\n{link['url']}" for i, link in enumerate(links[:6]))
        count = sum(len(evidence.get(k, [])) for k in ['quotes','officialIssues','headlines','gmp']) + (1 if evidence.get('fund') else 0)
        return {'answer': answer, 'model': model_used.get(), 'source': 'Educational explanation' if evidence.get('educational') else f'{count} public observations retrieved automatically. News headlines are attributed reports; prices may be delayed.', 'asOf': evidence['retrievedAt']}
    except ValueError as exc:
        return JSONResponse({'error': str(exc)}, status_code=503)
    except Exception:
        return JSONResponse({'error': 'Research source or AI connection unavailable. Please retry.'}, status_code=503)

@app.post('/v1/voice/transcribe')
async def voice_transcribe(request: Request):
    from .voice import transcribe_audio, MAX_AUDIO_BYTES
    audio = bytearray()
    async for chunk in request.stream():
        audio.extend(chunk)
        if len(audio) > MAX_AUDIO_BYTES:
            return JSONResponse({'error': 'Recording too large. Keep your question under 30 seconds.'}, status_code=413)
    try:
        return await transcribe_audio(bytes(audio), request.headers.get('content-type',''), request.headers.get('x-voice-language','auto'))
    except ValueError as exc:
        return JSONResponse({'error': str(exc)}, status_code=422)
    except (RuntimeError, httpx.HTTPError):
        return JSONResponse({'error': 'Speech transcription is temporarily unavailable. Retry, or type your question.'}, status_code=503)


@app.post('/v1/debate')

async def research(body: DebateRequest, request: Request):

    return StreamingResponse(research_events(body.subject, body.symbol, body.risk, body.module, body.assetName, request.headers.get('x-quantora-name', ''), body.documentUrl,language=body.language), media_type='application/x-ndjson', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

@app.post('/v1/research-stage')
async def research_stage(body: ResearchStageRequest, request: Request):
    return StreamingResponse(research_events(body.subject, body.symbol, body.risk, body.module, body.assetName, request.headers.get('x-quantora-name', ''), body.documentUrl,phase=body.phase,checkpoint=body.checkpoint,language=body.language,previous_context=body.previousContext),media_type='application/x-ndjson',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})



@app.get('/v1/news')

async def headlines():

    try:

        return {'news': await news()}

    except Exception:

        return JSONResponse({'news': [], 'error': 'The news feed is unavailable. No stories have been invented.'}, status_code=503)



@app.get('/v1/funds')

async def funds(code: str = Query('120503', pattern=r'^\d{5,8}$')):

    try:

        return await fund(code)

    except Exception:

        try:
            from .market_sources import amfi_fallback
            return await amfi_fallback(code)
        except Exception:
            return JSONResponse({'error': 'NAV unavailable from MFapi and AMFI.'}, status_code=503)



@app.get('/v1/audit')

async def audit():

    with Session() as db:

        return [{'id': r.id, 'symbol': r.symbol, 'createdAt': r.created_at.isoformat(), 'source': r.source, 'payload': r.payload} for r in db.scalars(select(ResearchAudit).where(ResearchAudit.user_id==research_owner.get()).order_by(ResearchAudit.id.desc()).limit(50))]



@app.get('/v1/discover')
async def discover(module: str = Query('ipo', pattern='^(ipo|stocks|funds|crypto|etfs)$'), q: str = Query('', max_length=100)):
    from .market_sources import stock_directory, crypto_markets, etf_directory
    try:
        if module == 'crypto':
            return await crypto_markets()
        if module == 'etfs':
            rows=await etf_directory(q)
            return {'items':rows,'source':rows[0]['source'] if rows else 'NSE official ETF directory','asOf':datetime.now(timezone.utc).isoformat()}
        if module == 'stocks':
            rows=await stock_directory(q)
            return {'items':rows, 'source':rows[0].get('source','NSE official listed equity directory') if rows else 'NSE official listed equity directory', 'asOf':datetime.now(timezone.utc).isoformat()}
        if module == 'funds':
            from .feeds import search_funds
            return {'items': await search_funds(q or 'direct growth'), 'source':'MFapi / AMFI scheme directory', 'asOf':datetime.now(timezone.utc).isoformat()}
        results = await asyncio.gather(get_issues('current'), get_issues('upcoming'), return_exceptions=True)
        items=[]; sources=[]; errors=[]
        for r in results:
            if isinstance(r, Exception):
                errors.append('An exchange feed is temporarily unavailable.')
            else:
                items.extend(r['issues']);sources.append(r['source'])
        if not items and len(errors)==2:raise ValueError('Both exchange feeds unavailable')
        unique={r['symbol']:r for r in items}
        return {'items':list(unique.values()),'source':'NSE public issue feeds','sources':sources,'warnings':errors,'asOf':datetime.now(timezone.utc).isoformat()}
    except Exception:
        return JSONResponse({'items':[], 'error':'The source for this module is unavailable. Retry; no sample data has been substituted.'}, status_code=503)

@app.get('/v1/gmp')
async def gmp():
    from .market_sources import gmp_feed
    try:
        return await gmp_feed()
    except Exception:
        return JSONResponse({'items':[], 'error':'GMP publisher unavailable or its table could not be verified. No GMP estimate was generated.', 'source':'https://www.investorgain.com/report/ipo-gmp-live/331/'},status_code=503)

@app.get('/v1/providers')
async def providers():
    from .agent_models import AGENT_MODELS
    return {'assignedModels':AGENT_MODELS,'providers':[{'name':'Google Gemini / Gemma','configured':bool(settings.gemini_api_key_tertiary.get_secret_value() or settings.gemini_api_key.get_secret_value())},{'name':'OpenRouter free · NVIDIA / Qwen where offered','configured':bool(settings.openrouter_api_key.get_secret_value())},{'name':'Groq','configured':bool(settings.groq_api_key.get_secret_value())},{'name':'Cloudflare Workers AI','configured':bool(settings.cloudflare_api_token.get_secret_value() and settings.cloudflare_account_id)},{'name':'NVIDIA NIM (production entitlement required)','configured':bool(settings.nvidia_api_key.get_secret_value() and settings.nvidia_production_entitled)},{'name':'Ollama','configured':bool(settings.ollama_url and (settings.ollama_api_key.get_secret_value() or not __import__('os').getenv('VERCEL')))}], 'note':'Configured is not a guarantee of current quota or availability. Actual responding models appear in every research response.'}


@app.get('/v1/live')
async def live_prices(request: Request, symbols: str = Query(...,max_length=400)):
    import json
    selected=list(dict.fromkeys(symbols.split(',')))[:12]
    if any(not re.fullmatch(r'[A-Za-z0-9^.&=\-]{1,40}',s) for s in selected):
        return JSONResponse({'error':'Invalid symbol'},status_code=400)
    async def stream():
        started=time.monotonic()
        while time.monotonic()-started<270:
            if await request.is_disconnected():return
            async def get(symbol):
                try:
                    q=await market.quote(symbol,'1d')
                    return {key:q[key] for key in ['symbol','name','price','change','currency','asOf','source'] if key in q}
                except Exception:return None
            from .company_data import quote_batch
            try:batch=await quote_batch(selected)
            except Exception:batch={}
            missing=[s for s in selected if s not in batch]
            quotes=list(batch.values())+[q for q in await asyncio.gather(*(get(s) for s in missing)) if q]
            payload={'quotes':quotes,'retrievedAt':datetime.now(timezone.utc).isoformat(),'mode':'automatic source refresh · provider may be delayed'}
            if not quotes:payload['error']='Live source unavailable; reconnecting automatically.'
            yield 'data: '+json.dumps(payload)+'\n\n'
            await asyncio.sleep(5)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.get('/v1/market-status')
async def exchange_status():
    from .market_sources import market_status
    try:return await market_status()
    except Exception:return {'state':'unknown','message':'Exchange status unavailable; quote timestamps remain visible.'}

@app.get('/v1/ipos/live')
async def live_ipo_sources(request:Request):
    import json
    from .market_sources import gmp_feed
    async def stream():
        started=time.monotonic()
        while time.monotonic()-started<270:
            if await request.is_disconnected():return
            feed,publisher=await asyncio.gather(discover('ipo',''),gmp_feed(),return_exceptions=True)
            yield 'data: '+json.dumps({'feed':feed if isinstance(feed,dict) else None,'gmp':publisher if isinstance(publisher,dict) else None,'retrievedAt':datetime.now(timezone.utc).isoformat()})+'\n\n'
            await asyncio.sleep(20)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.get('/v1/company')
async def company_details(symbol: str = Query(...,pattern=r'^[A-Za-z0-9.&=\-]{1,40}$')):
    from .company_data import company
    try:return await company(symbol)
    except Exception:return JSONResponse({'error':'Company fundamentals are temporarily unavailable. Price history and custom research remain available.'},status_code=503)

# A source-only preview, available before starting a council/model request.
_issuer_context_cache = {}
@app.get('/v1/issuer-context')
async def issuer_context(name: str = Query(...,min_length=3,max_length=140)):
    from .source_research import company_news,lookup_query
    query=lookup_query(name)
    if not query:return JSONResponse({'error':'Enter an issuer name'},status_code=400)
    cached=_issuer_context_cache.get(query)
    if cached and time.monotonic()-cached[0]<600:return cached[1]
    try:
        async with asyncio.timeout(14):headlines=await company_news(query)
        result={'headlines':headlines,'retrievedAt':datetime.now(timezone.utc).isoformat(),'note':'Name-matched publisher headlines, not verified company financials. Similar names can refer to another entity.'}
    except Exception:return JSONResponse({'error':'Issuer headlines are temporarily unavailable. Issue facts remain available.'},status_code=503)
    if len(_issuer_context_cache)>=128:_issuer_context_cache.pop(next(iter(_issuer_context_cache)))
    _issuer_context_cache[query]=(time.monotonic(),result)
    return result


@app.get('/v1/metals')
async def precious_metals():
    from .precious_metals import metals_snapshot
    return await metals_snapshot()

@app.post('/v1/ipo-brief')
async def quick_ipo_review(body:DebateRequest,request:Request):
    if len(body.assetName.strip())<3:return JSONResponse({'error':'Choose an IPO issuer first.'},status_code=400)
    from .ipo_brief import ipo_brief
    try:return await ipo_brief(body.assetName,request.headers.get('x-quantora-name',''),body.symbol)
    except Exception:return JSONResponse({'error':'The IPO analyst could not finish after automatic retries. Source facts remain available; please try again shortly.'},status_code=503)

@app.get('/v1/metals/live')
async def live_precious_metals(request:Request):
    import json
    from .precious_metals import metals_snapshot
    async def stream():
        started=time.monotonic()
        while time.monotonic()-started<270:
            if await request.is_disconnected():return
            payload=await metals_snapshot()
            yield 'data: '+json.dumps(payload)+'\n\n'
            await asyncio.sleep(5)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

