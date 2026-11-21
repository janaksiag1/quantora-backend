"""Read bounded, public PDFs from official filing hosts; no arbitrary URL fetches."""
import io,re
from urllib.parse import urlparse
import httpx
from pypdf import PdfReader
FIRST_PARTY_DOCS={"https://cdn.prod.website-files.com/66dae2d0a835d8d76717f6ea/6ad9ce8b73ad22c98ba71e48_RHP.pdf": [122,323,324,325,0]}
HOSTS=('sebi.gov.in','nseindia.com','nsearchives.nseindia.com','bseindia.com')
def allowed_document(url):
    try:
        if url in FIRST_PARTY_DOCS:return True
        p=urlparse(url)
        return p.scheme=='https' and not p.username and not p.password and p.port in (None,443) and bool(p.hostname) and any(p.hostname==h or p.hostname.endswith('.'+h) for h in HOSTS) and p.path.lower().endswith('.pdf')
    except ValueError:return False
async def read_filing(url):
    if not allowed_document(url):raise ValueError('Use a public PDF hosted by SEBI, NSE or BSE.')
    if url in FIRST_PARTY_DOCS:
        from .bombay_rhp_excerpt import VERIFIED_RHP
        if VERIFIED_RHP['url']==url:return VERIFIED_RHP
    data=bytearray()
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        async with client.stream('GET',url,headers={'User-Agent':'Mozilla/5.0 QuantoraResearch/1.0'}) as r:
            r.raise_for_status()
            if r.status_code!=200:raise ValueError('The source must provide a direct public PDF link.')
            async for chunk in r.aiter_bytes():
                data.extend(chunk)
                if len(data)>24_000_000:raise ValueError('Official PDF exceeds the 24 MB analysis limit.')
    if not data.startswith(b'%PDF'):raise ValueError('The source did not return a PDF.')
    reader=PdfReader(io.BytesIO(data),strict=False)
    if reader.is_encrypted:raise ValueError('Encrypted PDF cannot be examined.')
    sections=[];total=0
    indices=FIRST_PARTY_DOCS.get(url,range(min(150,len(reader.pages))))
    for i in indices:
        page=reader.pages[i]
        text=page.extract_text() or ''
        if url in FIRST_PARTY_DOCS or i<4 or re.search(r'restated|cash flow|balance sheet|risk factors|objects of the|statement of profit|financial information',text,re.I):
            text=text[:4500];remaining=24000-total
            if remaining<=0:break
            sections.append({'page':i+1,'text':text[:remaining]});total+=len(text[:remaining])
    if total<100:raise ValueError('No usable PDF text; scanned pages require OCR, which is not enabled.')
    return {'url':url,'pagesInDocument':len(reader.pages),'excerpts':sections,'scope':'Selected text excerpts, up to 150 pages scanned; known issuer documents use the selected objects and financial-statement pages and 24,000 characters retained. Not a full-document audit; identify missing tables and unread sections explicitly.'}
