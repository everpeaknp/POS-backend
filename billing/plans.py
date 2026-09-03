"""Subscription plan catalog for KHATA SaaS billing."""

from decimal import Decimal

DEFAULT_SUBSCRIPTION_PLANS = {
    'free': {
        'code': 'free',
        'name': 'Free',
        'plan_type': 'free',
        'price': Decimal('0.00'),
        'max_users': None,  # Unlimited users
        'max_orgs': None,   # Unlimited organizations
        'features': [
            'Unlimited users',
            'Unlimited organizations',
            'All Modules',
            'Personal Finance',
            'Sales & Purchase',
            'Inventory',
            'Accounting',
            'Reports & Analytics',
            'POS (Point of Sale)',
            'HR Management',
            'Construction Management',
            'Hardware Management',
        ],
        'modules': [
            'personal_finance', 'sales', 'purchase', 'inventory', 'accounting',
            'reports', 'pos', 'hr', 'construction', 'hardware',
        ],
        'is_popular': False,
    },
    'starter': {
        'code': 'starter',
        'name': 'Starter',
        'plan_type': 'basic',
        'price': Decimal('999.00'),
        'max_users': 10,
        'max_orgs': 5,
        'features': [
            'Up to 10 users',
            'Up to 5 organizations',
            'Personal Finance',
            'Sales & Purchase',
            'Basic Reports',
            'Email Support',
            'Accounting',
        ],
        'modules': ['personal_finance', 'sales', 'purchase', 'inventory', 'reports', 'accounting'],
        'is_popular': False,
    },
    'business': {
        'code': 'business',
        'name': 'Business',
        'plan_type': 'premium',
        'price': Decimal('2499.00'),
        'max_users': 50,
        'max_orgs': 10,
        'features': [
            'Up to 50 users',
            'Up to 10 organizations',
            'All Modules',
            'Advanced Reports',
            'Priority Support',
            'API Access',
        ],
        'modules': [
            'personal_finance', 'sales', 'purchase', 'inventory', 'accounting',
            'reports', 'pos', 'hr', 'construction', 'hardware',
        ],
        'is_popular': True,
    },
}

# Backwards-compatible alias
SUBSCRIPTION_PLANS = DEFAULT_SUBSCRIPTION_PLANS

DEFAULT_PLAN_TYPE_TO_CODE = {
    'free': 'free',
}

PLAN_TYPE_TO_CODE = DEFAULT_PLAN_TYPE_TO_CODE


def _plan_model_to_dict(plan) -> dict:
    return {
        'code': plan.code,
        'name': plan.name,
        'plan_type': plan.plan_type,
        'price': plan.price,
        'max_users': plan.max_users,
        'max_orgs': plan.max_orgs,
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
        # Keep defaults for plan types missing from partial DB catalogs.
        return {**DEFAULT_PLAN_TYPE_TO_CODE, **mapping}
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
