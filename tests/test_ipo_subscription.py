from app.ipo_subscription import subscription_value

def test_alternate_fields_and_zero_are_preserved():
    assert subscription_value({'noOfTimes': '1,234.50x'}) == 1234.5
    assert subscription_value({'noOfTime': '0.00'}) == 0

def test_only_published_bid_counts_produce_a_ratio():
    assert subscription_value({'noOfSharesOffered': '1,000', 'noOfsharesBid': '2,350'}) == 2.35
    assert subscription_value({'noOfSharesOffered': '0', 'noOfsharesBid': '20'}) is None
    assert subscription_value({'noOfTime': 'Not published'}) is None
    assert subscription_value({}) is None
