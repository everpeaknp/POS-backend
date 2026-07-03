"""Subscription plan catalog for KHATA SaaS billing."""

from decimal import Decimal

SUBSCRIPTION_PLANS = {
    'starter': {
        'code': 'starter',
        'name': 'Starter',
        'plan_type': 'basic',
        'price': Decimal('999.00'),
        'max_users': 2,
        'features': [
            'Up to 2 users',
            'Sales & Purchase',
            'Basic Reports',
            'Email Support',
        ],
        'modules': ['sales', 'purchase', 'inventory', 'reports'],
    },
    'business': {
        'code': 'business',
        'name': 'Business',
        'plan_type': 'premium',
        'price': Decimal('2499.00'),
        'max_users': 10,
        'features': [
            'Up to 10 users',
            'All Modules',
            'Advanced Reports',
            'Priority Support',
            'API Access',
        ],
        'modules': [
            'sales', 'purchase', 'inventory', 'accounting',
            'reports', 'pos', 'hr',
        ],
    },
    'enterprise': {
        'code': 'enterprise',
        'name': 'Enterprise',
        'plan_type': 'enterprise',
        'price': Decimal('5999.00'),
        'max_users': None,
        'features': [
            'Unlimited users',
            'All Modules',
            'Custom Reports',
            'Dedicated Support',
            'Custom Integrations',
            'SLA Guarantee',
        ],
        'modules': [
            'sales', 'purchase', 'inventory', 'accounting',
            'reports', 'pos', 'hr', 'construction',
        ],
    },
}

PLAN_TYPE_TO_CODE = {
    'free': 'starter',
    'basic': 'starter',
    'premium': 'business',
    'enterprise': 'enterprise',
}


def get_plan(plan_code: str) -> dict:
    plan = SUBSCRIPTION_PLANS.get(plan_code)
    if not plan:
        raise ValueError(f'Unknown plan: {plan_code}')
    return plan
