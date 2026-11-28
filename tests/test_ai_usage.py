from app.ai_usage import normalize_usage

def test_google_reported_tokens_do_not_imply_zero_cost():
    r=normalize_usage('Google','gemma',{'usageMetadata':{'promptTokenCount':12,'candidatesTokenCount':0,'totalTokenCount':12}})
    assert r['inputTokens']==12 and r['outputTokens']==0
    assert r['reportedCostUSD'] is None

def test_explicit_openrouter_zero_cost_is_kept_but_invalid_counts_are_unknown():
    r=normalize_usage('OpenRouter','model',{'usage':{'prompt_tokens':True,'completion_tokens':-2,'total_tokens':float('nan'),'cost':0}})
    assert r['reportedCostUSD']==0
    assert r['inputTokens'] is None and r['outputTokens'] is None and r['totalTokens'] is None
    assert 'prompt' not in r and 'answer' not in r

def test_absent_metadata_is_unknown_not_fabricated():
    r=normalize_usage('Groq','model',{})
    assert all(r[k] is None for k in ['inputTokens','outputTokens','totalTokens','reportedCostUSD'])
