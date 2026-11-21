from app.report_checks import reviewed_report
def test_unsupplied_financial_claims_do_not_enter_final_findings():
    report={'classification':'Watch','summary':'Capex is 19.36 crore and export share is 84%.','positives':['DRHP highlights 19.36 crore capex','Exports are 84% of revenue'],'risks':['Export dependence is high','SME liquidity may be limited'],'missingEvidence':[]}
    evidence={'sources':[{'url':'a'},{'url':'b'}],'officialIssues':[{'name':'Test issuer','opens':'30-Oct-2026','closes':'3-Nov-2026','subscription':1.53}],'metrics':{}}
    checked,meta=reviewed_report(report,evidence,'ipo','Aarav')
    assert '19.36' not in str(checked['positives']) and '84%' not in str(checked['positives'])
    assert checked['summary'].startswith('Aarav,')
    assert meta['excludedNarrativeClaims']==3
    assert checked['classification']=='Research further'
def test_empty_sources_cannot_become_a_watch_conclusion():
    report={'classification':'Watch','summary':'Looks good','positives':[],'risks':[],'missingEvidence':[]}
    checked,_=reviewed_report(report,{},'stocks','Aarav')
    assert checked['classification']=='Insufficient evidence'
