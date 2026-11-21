import pytest
from app.company_data import normalize_company,numeric
def test_company_metrics_preserve_missing_zero_and_percent_units():
    result=normalize_company('TEST.NS',{'price':{'symbol':'TEST.NS','regularMarketPrice':{'raw':100},'currency':'INR'},'summaryDetail':{'trailingPE':None,'dividendYield':{'raw':.02}},'defaultKeyStatistics':{'trailingEps':{'raw':0}}})
    assert result['metrics']['trailingPE'] is None
    assert result['metrics']['trailingEPS']==0
    assert result['metrics']['dividendYieldPercent']==2
    assert result['reportingReference'] is None
def test_company_identity_and_non_numeric_fields_are_not_invented():
    with pytest.raises(ValueError):normalize_company('TCS.NS',{'price':{'symbol':'OTHER.NS','regularMarketPrice':100}})
    for value in ['N/A','100 crore',None,float('nan'),True]:assert numeric(value) is None

def test_quarterly_statements_keep_actual_periods_and_missing_values():
    result=normalize_company('TEST.NS',{'price':{'symbol':'TEST.NS','regularMarketPrice':100},'incomeStatementHistoryQuarterly':{'incomeStatementHistory':[{'endDate':{'raw':1711843200},'totalRevenue':{'raw':120},'netIncome':{'raw':-4}},{'netIncome':999}]}})
    assert len(result['quarterlyStatements'])==1
    assert result['quarterlyStatements'][0]['totalRevenue']==120
    assert result['quarterlyStatements'][0]['netIncome']==-4
    assert result['quarterlyStatements'][0]['operatingIncome'] is None
    assert result['annualStatements']==[]

def test_financial_units_negative_cash_flow_and_real_statement_periods():
    result=normalize_company('TEST.NS',{'price':{'symbol':'TEST.NS','regularMarketPrice':100,'currency':'USD'},'financialData':{'financialCurrency':'INR','profitMargins':{'raw':-.02},'debtToEquity':{'raw':85},'freeCashflow':{'raw':-500}},'incomeStatementHistory':{'incomeStatementHistory':[{'endDate':{'raw':1711843200},'netIncome':{'raw':0}},{'netIncome':999}]}})
    assert result['metrics']['profitMarginsPercent']==-2
    assert result['metrics']['debtToEquityPercent']==85
    assert result['metrics']['freeCashflow']==-500
    assert result['financialCurrency']=='INR' and result['currency']=='USD'
    assert len(result['annualStatements'])==1
    assert result['annualStatements'][0]['netIncome']==0
    assert result['annualStatements'][0]['totalRevenue'] is None

def test_optional_company_modules_can_fail_without_losing_basic_data(monkeypatch):
    from app import company_data as cd
    cd.CACHE.pop('BASIC.NS',None)
    calls=[]
    async def fake(path,params):
        calls.append(params['modules'])
        if 'financialData' in params['modules']:raise ValueError('Optional module unavailable')
        return {'quoteSummary':{'result':[{'price':{'symbol':'BASIC.NS','regularMarketPrice':100}}]}}
    monkeypatch.setattr(cd,'public_json',fake)
    import asyncio
    result=asyncio.run(cd.company('BASIC.NS'))
    assert len(calls)==2 and result['symbol']=='BASIC.NS'
    assert result['metrics']['totalDebt'] is None
