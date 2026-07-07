"""Subscription plan catalog for KHATA SaaS billing."""

from decimal import Decimal

DEFAULT_SUBSCRIPTION_PLANS = {
    'free': {
        'code': 'free',
        'name': 'Free',
        'plan_type': 'free',
        'price': Decimal('0.00'),
        'max_users': 1,
        'features': [
            '1 user',
            'Sales & Purchase',
            'Inventory',
            'Basic Reports',
            'Accounting',
        ],
        'modules': ['sales', 'purchase', 'inventory', 'reports', 'accounting'],
        'is_popular': False,
    },
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
            'Accounting',
        ],
        'modules': ['sales', 'purchase', 'inventory', 'reports', 'accounting'],
        'is_popular': False,
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
        'is_popular': True,
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
        'is_popular': False,
    },
}

# Backwards-compatible alias
SUBSCRIPTION_PLANS = DEFAULT_SUBSCRIPTION_PLANS

DEFAULT_PLAN_TYPE_TO_CODE = {
    'free': 'free',
    'basic': 'starter',
    'premium': 'business',
    'enterprise': 'enterprise',
}

PLAN_TYPE_TO_CODE = DEFAULT_PLAN_TYPE_TO_CODE


def _plan_model_to_dict(plan) -> dict:
    return {
        'code': plan.code,
        'name': plan.name,
        'plan_type': plan.plan_type,
        'price': plan.price,
        'max_users': plan.max_users,
        'features': plan.features or [],
        'modules': plan.modules or [],
        'is_popular': plan.is_popular,
    }


def _db_plans_exist() -> bool:
    from billing.models import SubscriptionPlan
    return SubscriptionPlan.objects.exists()


def list_active_plans() -> list[dict]:
    from billing.models import SubscriptionPlan

    if _db_plans_exist():
        return [
            _plan_model_to_dict(plan)
            for plan in SubscriptionPlan.objects.filter(is_active=True).order_by('sort_order', 'code')
        ]
    return list(DEFAULT_SUBSCRIPTION_PLANS.values())


def get_plan_codes(active_only: bool = True) -> list[str]:
    from billing.models import SubscriptionPlan

    if _db_plans_exist():
        qs = SubscriptionPlan.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
        return list(qs.order_by('sort_order', 'code').values_list('code', flat=True))
    if active_only:
        return list(DEFAULT_SUBSCRIPTION_PLANS.keys())
    return list(DEFAULT_SUBSCRIPTION_PLANS.keys())


def get_plan_type_to_code_map() -> dict[str, str]:
    from billing.models import SubscriptionPlan

    if _db_plans_exist():
        mapping: dict[str, str] = {}
        for plan in SubscriptionPlan.objects.filter(is_active=True).order_by('sort_order', 'code'):
            mapping[plan.plan_type] = plan.code
        return mapping or DEFAULT_PLAN_TYPE_TO_CODE
    return DEFAULT_PLAN_TYPE_TO_CODE


def get_plan(plan_code: str) -> dict:
    from billing.models import SubscriptionPlan

    if _db_plans_exist():
        plan = SubscriptionPlan.objects.filter(code=plan_code).first()
        if plan:
            return _plan_model_to_dict(plan)

    plan = DEFAULT_SUBSCRIPTION_PLANS.get(plan_code)
    if not plan:
        raise ValueError(f'Unknown plan: {plan_code}')
    return plan


def plan_available_for_checkout(plan_code: str) -> bool:
    from billing.models import SubscriptionPlan

    if _db_plans_exist():
        return SubscriptionPlan.objects.filter(code=plan_code, is_active=True).exists()
    return plan_code in DEFAULT_SUBSCRIPTION_PLANS
