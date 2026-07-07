"""Account- and plan-level limits for organizations and modules."""

from rest_framework import serializers

from billing.plans import get_plan
from core_backend.platform_constants import AVAILABLE_MODULES

CORE_MODULES = frozenset({'accounting', 'settings', 'dashboard'})

PLAN_RANK = {
    'free': 0,
    'starter': 1,
    'business': 2,
    'enterprise': 3,
}

ALL_MODULE_IDS = frozenset(module for module, _ in AVAILABLE_MODULES)


def get_allowed_modules_for_plan(plan_code: str) -> list[str]:
    """Modules a tenant on this plan may enable (includes core modules)."""
    if plan_code == 'enterprise':
        return sorted(ALL_MODULE_IDS)

    plan = get_plan(plan_code)
    allowed = set(plan.get('modules') or [])
    allowed |= CORE_MODULES
    return sorted(allowed)


def get_tenant_plan_code(tenant) -> str:
    from billing.services import ensure_subscription

    subscription = ensure_subscription(tenant)
    return subscription.plan_code


def get_user_account_plan_code(user) -> str:
    """Account subscription tier for this user."""
    from billing.models import UserSubscription

    try:
        return UserSubscription.objects.get(user=user).plan_code
    except UserSubscription.DoesNotExist:
        return 'free'


def count_orgs_created_by_user(user) -> int:
    from tenants.models import Tenant

    return Tenant.objects.filter(created_by=user).count()


def user_can_create_org(user) -> bool:
    plan = get_plan(get_user_account_plan_code(user))
    max_orgs = plan.get('max_orgs')
    if max_orgs is None:
        return True
    return count_orgs_created_by_user(user) < max_orgs


def get_user_account_limits(user) -> dict:
    account_plan_code = get_user_account_plan_code(user)
    account_plan = get_plan(account_plan_code)
    orgs_created = count_orgs_created_by_user(user)
    max_orgs = account_plan.get('max_orgs')
    new_org_plan_code = 'free'
    new_org_plan = get_plan(new_org_plan_code)

    return {
        'account_plan_code': account_plan_code,
        'account_plan_name': account_plan['name'],
        'max_orgs': max_orgs,
        'orgs_created': orgs_created,
        'can_create_org': user_can_create_org(user),
        'new_org_plan_code': new_org_plan_code,
        'new_org_plan_name': new_org_plan['name'],
        'new_org_allowed_modules': get_allowed_modules_for_plan(new_org_plan_code),
        'max_users': new_org_plan.get('max_users'),
    }


def normalize_active_modules_for_plan(plan_code: str, modules: list[str] | None) -> list[str]:
    allowed = set(get_allowed_modules_for_plan(plan_code))
    normalized: list[str] = []
    seen: set[str] = set()

    for module in modules or []:
        key = str(module).strip().lower()
        if not key or key in seen:
            continue
        if key in allowed:
            normalized.append(key)
            seen.add(key)

    for core in CORE_MODULES:
        if core not in seen:
            normalized.append(core)
            seen.add(core)

    return normalized


def assert_user_can_create_org(user) -> None:
    if user_can_create_org(user):
        return

    plan = get_plan(get_user_account_plan_code(user))
    max_orgs = plan.get('max_orgs')
    raise serializers.ValidationError({
        'detail': (
            f'Your {plan["name"]} plan allows up to {max_orgs} '
            f'organization{"s" if max_orgs != 1 else ""}. '
            'Upgrade a workspace to create more organizations.'
        ),
    })


def assert_modules_allowed_for_plan(plan_code: str, modules: list[str]) -> None:
    allowed = set(get_allowed_modules_for_plan(plan_code))
    invalid = sorted({str(m).lower() for m in modules} - allowed)
    if not invalid:
        return

    plan = get_plan(plan_code)
    raise serializers.ValidationError({
        'active_modules': (
            f'The {plan["name"]} plan does not include: {", ".join(invalid)}. '
            'Upgrade your subscription to enable more modules.'
        ),
    })


def assert_tenant_can_enable_module(tenant, module_name: str) -> None:
    if module_name in CORE_MODULES:
        return

    plan_code = get_tenant_plan_code(tenant)
    allowed = set(get_allowed_modules_for_plan(plan_code))
    if module_name in allowed:
        return

    plan = get_plan(plan_code)
    raise ValueError(
        f'The {plan["name"]} plan does not include {module_name}. '
        'Upgrade your subscription to enable this module.'
    )


def get_tenant_allowed_modules(tenant) -> list[str]:
    return get_allowed_modules_for_plan(get_tenant_plan_code(tenant))


def count_tenant_members(tenant) -> int:
    """Distinct users assigned to a tenant via membership or primary tenant."""
    from tenants.membership_models import UserTenantMembership
    from users.models import User

    member_ids = set(
        UserTenantMembership.objects.filter(tenant=tenant).values_list('user_id', flat=True)
    )
    primary_ids = set(User.objects.filter(tenant=tenant).values_list('id', flat=True))
    return len(member_ids | primary_ids)


def count_pending_tenant_invitations(tenant) -> int:
    from tenants.invitation_models import OrganizationInvitation

    return OrganizationInvitation.objects.filter(tenant=tenant, status='pending').count()


def get_tenant_user_limits(tenant) -> dict:
    """Seat usage for the workspace based on its subscription plan."""
    plan_code = get_tenant_plan_code(tenant)
    plan = get_plan(plan_code)
    max_users = plan.get('max_users')
    current_users = count_tenant_members(tenant)
    pending_invites = count_pending_tenant_invitations(tenant)
    seats_used = current_users + pending_invites
    can_invite = max_users is None or seats_used < max_users

    return {
        'plan_code': plan_code,
        'plan_name': plan['name'],
        'max_users': max_users,
        'current_users': current_users,
        'pending_invites': pending_invites,
        'seats_used': seats_used,
        'can_invite': can_invite,
    }


def assert_tenant_can_add_user(tenant, additional_seats: int = 1) -> None:
    """Raise ValidationError when inviting would exceed the plan user limit."""
    limits = get_tenant_user_limits(tenant)
    max_users = limits['max_users']
    if max_users is None:
        return

    seats_after = limits['seats_used'] + additional_seats
    if seats_after <= max_users:
        return

    plan_name = limits['plan_name']
    current_users = limits['current_users']
    pending_invites = limits['pending_invites']
    detail = (
        f'Your {plan_name} plan allows up to {max_users} user'
        f'{"s" if max_users != 1 else ""}. '
        f'You have {current_users} member{"s" if current_users != 1 else ""}'
    )
    if pending_invites:
        detail += (
            f' and {pending_invites} pending invitation'
            f'{"s" if pending_invites != 1 else ""}'
        )
    detail += '. Upgrade your plan to add more users.'

    raise serializers.ValidationError({'detail': detail})
