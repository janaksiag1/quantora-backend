"""Conservative final-report checks; facts come from adapters, not model memory."""
import json,re,math

def tokens(text):
    return [float(x.replace(',','')) for x in re.findall(r'(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?',str(text))]

def reviewed_report(report,evidence,module,owner):
    corpus=json.dumps(evidence,ensure_ascii=False).lower()
    available=tokens(corpus)
    excluded=[]
    def supported(text):
        if not evidence.get('filing') and re.search(r'\b(drhp|rhp|audited|prospectus|balance sheet)\b',text,re.I):return False
        for number in tokens(text):
            if not any(abs(number-source)<=max(.015,abs(source)*.00001) for source in available):return False
        for topic in ['export','capex','revenue','margin','promoter','pledge','litigation','debt','customer concentration']:
            if topic in text.lower() and topic not in corpus:return False
        return True
    observations=[]
    for issue in evidence.get('officialIssues',[])[:2]:
        observations.append(f"Exchange-published issue record: {issue.get('name','selected issue')}; bidding {issue.get('opens') or 'not supplied'} to {issue.get('closes') or 'not supplied'}. Verify the listing venue in the offer document.")
        subscription=issue.get('subscription')
        if isinstance(subscription,(float,int)) and math.isfinite(subscription):observations.append(f"Source-reported subscription: {subscription:.2f}×. Counts and publication times can differ across exchanges.")
    for q in evidence.get('quotes',[])[:1]:
        if isinstance(q.get('price'),(int,float)):observations.append(f"Retrieved price: {q['price']} {q.get('currency','')}; source timestamp {q.get('asOf','not supplied')}. Prices can be delayed.")
    if evidence.get('fund'):
        rows=evidence['fund'].get('data',[])
        if rows:observations.append(f"Published scheme NAV: {rows[0].get('nav')} on {rows[0].get('date')}. NAV is not an intraday traded price.")
    company=evidence.get('company',{});metrics=company.get('metrics',{})
    if company.get('sector'):observations.append(f"Aggregator company profile: sector {company['sector']}; industry {company.get('industry') or 'not supplied'}. Verify current business details against filings.")
    for key,label in [('trailingPE','Trailing P/E'),('trailingEPS','Trailing EPS'),('bookValue','Book value per share')]:
        value=metrics.get(key)
        if isinstance(value,(int,float)) and math.isfinite(value):observations.append(f"Aggregator-reported {label}: {value:.2f}{' '+str(company.get('currency') or '') if key!='trailingPE' else '×'}. Reporting reference: {company.get('reportingReference') or 'not supplied'}; not an audited figure supplied by the app.")
    if evidence.get('metrics',{}).get('lot'):
        lot=evidence['metrics']['lot'];observations.append(f"Publisher reports {lot['shares']} shares in one lot at {lot['issuePrice']} per share. One-lot capital is {lot['applicationAmount']}; this is not confirmation of the minimum application.")
    if evidence.get('filing'):
        for claim in report.get('positives',[]):
            ids=re.findall(r'\[(S\d+)\]',claim);known={s.get('id') for s in evidence.get('sources',[])}
            if supported(claim) and ids and all(i in known for i in ids):observations.append('Document interpretation: '+claim)
            else:excluded.append(claim)
    else:excluded.extend(report.get('positives',[]))
    report['positives']=observations[:8] or ['No sufficiently attributable facts were retrieved for this question.']
    risks=[]
    for risk in report.get('risks',[]):
        if supported(risk):risks.append('Risk consideration: '+risk)
        else:excluded.append(risk)
    report['risks']=risks or ['The retrieved evidence is incomplete; do not infer safety from missing information.']
    next_steps=[]
    for step in report.get('nextSteps',[]):
        if supported(step):next_steps.append(step)
        else:excluded.append(step)
    report['nextSteps']=next_steps or ['Read the official offer/scheme documents and confirm the source observations before deciding.']
    if not supported(report.get('summary','')) or module=='ipo':
        report['summary']=f'{owner}, this review separates retrieved source observations from risk interpretations. Use the figures and source links below to assess the question. Lot scenarios are illustrations, not promised profits or confirmation of minimum application size. Missing financial documents and unverified claims remain gaps.'
    report.setdefault('missingEvidence',[])
    for key in ['companyError','quoteError','gmpError','filingError','newsError']:
        gap=evidence.get(key)
        if gap and gap not in report['missingEvidence']:report['missingEvidence'].append(gap)
    if evidence.get('listingCandidates'):report['missingEvidence'].append('The company name is ambiguous. Choose the exact listing before relying on company-specific conclusions.')
    if excluded:report['missingEvidence'].append('Unverified narrative claims were excluded from the final findings. Obtain the official financial/offer documents before drawing a business-quality conclusion.')
    if module=='ipo' and not evidence.get('filing'):report['missingEvidence'].append('An official offer document has not been examined. Minimum application lots and listing venue require document confirmation.')
    if len(evidence.get('sources',[]))<2:report['classification']='Insufficient evidence'
    elif excluded and report.get('classification')=='Watch':report['classification']='Research further'
    return report,{'sourceLedFacts':True,'excludedNarrativeClaims':len(excluded),'scope':'Unsupported numerical and document claims are excluded. This is a consistency check, not an independent audit or a guarantee of correctness.'}
