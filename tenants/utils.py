from tenants.membership_models import UserTenantMembership


def get_request_tenant(user):
    """Resolve the active tenant for an authenticated user.

    Honors membership.is_active so disabled org access never becomes request context.
    """
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return None

    return user.get_tenant()


def is_tenant_super_admin(user, tenant) -> bool:
    """True if the user created this business card (top-level Super Admin)."""
    if not user or not tenant:
        return False
    return bool(tenant.created_by_id and tenant.created_by_id == getattr(user, 'id', None))


def user_has_tenant_access(user, tenant):
    """Check whether the user may access data for the given tenant."""
    if not user or not tenant:
        return False

    # Super Admin (creator) always retains access to their own business card
    if is_tenant_super_admin(user, tenant):
        return True

    membership = UserTenantMembership.objects.filter(user=user, tenant=tenant).first()
    if membership is not None:
        return bool(membership.is_active)

    # Legacy: primary tenant with no membership row
    return user.tenant_id == tenant.id


def is_tenant_admin(user, tenant) -> bool:
    """True when the user is admin of the specific tenant (not global account role)."""
    if not user or not tenant:
        return False
    if is_tenant_super_admin(user, tenant):
        return True
    membership = UserTenantMembership.objects.filter(
        user=user,
        tenant=tenant,
        is_active=True,
    ).first()
    return membership is not None and membership.role == 'admin'
