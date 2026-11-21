from app.filings import allowed_document
def test_official_pdf_policy_rejects_private_and_lookalike_hosts():
    assert allowed_document('https://www.sebi.gov.in/filings/offer.pdf')
    assert allowed_document('https://nsearchives.nseindia.com/content/ipo/report.pdf')
    for url in ['http://www.sebi.gov.in/a.pdf','https://127.0.0.1/a.pdf','https://sebi.gov.in.evil.test/a.pdf','https://user:pass@www.sebi.gov.in/a.pdf','https://www.sebi.gov.in:8080/a.pdf','https://www.sebi.gov.in/api']:
        assert not allowed_document(url)
