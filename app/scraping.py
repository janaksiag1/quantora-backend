"""Allowlisted public-document extraction. Not used as a substitute for verified live IPO data."""
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup

ALLOWED = {'www.sebi.gov.in', 'www.nseindia.com', 'www.bseindia.com'}

async def extract_public_document(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED or parsed.username or parsed.port:
        raise ValueError('Only allowlisted official HTTPS sources are supported.')
    origin = f'https://{parsed.hostname}'
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        robots = await client.get(origin + '/robots.txt')
        if robots.status_code != 200:
            raise ValueError('Robots policy unavailable; extraction skipped.')
        policy = RobotFileParser()
        policy.parse(robots.text.splitlines())
        if not policy.can_fetch('QuantoraResearch', url):
            raise ValueError('Source robots policy disallows this document.')
        response = await client.get(url, headers={'User-Agent': 'QuantoraResearch/1.0'})
        response.raise_for_status()
        if 'text/html' not in response.headers.get('content-type', '') or len(response.content) > 2_000_000:
            raise ValueError('Only bounded HTML documents are supported.')
    soup = BeautifulSoup(response.text, 'lxml')
    for tag in soup(['script', 'style', 'nav', 'footer']):
        tag.decompose()
    return {'url': url, 'title': soup.title.get_text(strip=True) if soup.title else '', 'text': soup.get_text(' ', strip=True)[:18000], 'verification': 'Official-source text extraction; claims require human review.'}
