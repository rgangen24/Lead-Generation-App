# Base subscription plans
BASE_PLANS = {
    "starter": {
        "price": 499,            # Small business-friendly starter plan
        "discount": 0.4,         # 40% off lead price
        "lead_cap": 50,          # Maximum number of leads per month included
        "period_days": 30
    },
    "pro": {
        "price": 999,
        "discount": 0.6,         # 60% off lead price
        "lead_cap": 150,
        "period_days": 30
    },
    "elite": {
        "price": 1999,
        "discount": 0.7,         # 70% off lead price
        "lead_cap": 500,
        "period_days": 30
    }
}

# Pay-per-lead pricing tiers
LEAD_PRICING = {
    "basic": 15,      # Cleaning, electricians, plumbers
    "mid": 45,        # Real estate, insurance, SaaS
    "high": 150       # Legal, consulting, high-ticket B2B
}

# Lead caps per month for pay-per-lead clients
PAY_PER_LEAD_CAP = {
    "basic": 50,
    "mid": 100,
    "high": 200
}

# Trial configuration
TRIAL_CONFIG = {
    "price": 49,          # One-time trial cost
    "leads": 10,          # Number of leads in trial pack
    "days_valid": 7       # Trial validity
}

# Industry mapping to tiers
INDUSTRY_TIERS = {
    "restaurants": "basic",
    "fitness": "mid",
    "salons": "basic",
    "cleaning": "basic",
    "plumbing": "basic",
    "electricians": "basic",
    "real_estate": "mid",
    "insurance": "mid",
    "saas": "mid",
    "law": "high",
    "consulting": "high"
}

# Grace period and auto-downgrade
GRACE_PERIOD_DAYS = 5
AUTO_DOWNGRADE = True