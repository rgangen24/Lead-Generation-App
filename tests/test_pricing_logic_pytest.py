import pytest
from lead_generation_app.config.pricing import BASE_PLANS, LEAD_PRICING, INDUSTRY_TIERS


@pytest.mark.unit
def test_discounts_applied():
    tier = INDUSTRY_TIERS['restaurants']
    base_price = LEAD_PRICING[tier]
    assert round(base_price * (1 - BASE_PLANS['starter']['discount']), 2) == 9.0
    assert round(base_price * (1 - BASE_PLANS['pro']['discount']), 2) == 6.0
    assert round(base_price * (1 - BASE_PLANS['elite']['discount']), 2) == 4.5


@pytest.mark.unit
def test_caps_defined():
    assert BASE_PLANS['starter']['lead_cap'] == 50
    assert BASE_PLANS['pro']['lead_cap'] == 150
    assert BASE_PLANS['elite']['lead_cap'] == 500
