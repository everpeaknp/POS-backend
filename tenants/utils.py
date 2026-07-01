from tenants.membership_models import UserTenantMembership


def get_request_tenant(user):
    """Resolve the active tenant for an authenticated user."""
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return None

    if user.tenant_id:
        return user.tenant

    return user.get_tenant()


def user_has_tenant_access(user, tenant):
    """Check whether the user may access data for the given tenant."""
    if not user or not tenant:
        return False

    if user.tenant_id == tenant.id:
        return True

    if tenant.created_by_id == user.id:
        return True

    return UserTenantMembership.objects.filter(user=user, tenant=tenant).exists()
