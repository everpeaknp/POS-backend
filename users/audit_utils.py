"""Write audit log entries for settings and security-sensitive actions."""
from __future__ import annotations


def _client_ip(request) -> str | None:
    if not request:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def audit_log(
    request,
    action: str,
    module: str,
    description: str,
    *,
    metadata=None,
    tenant=None,
    user=None,
):
    from tenants.utils import get_request_tenant
    from users.models import AuditLog

    resolved_tenant = tenant
    if resolved_tenant is None and request is not None and getattr(request, 'user', None):
        resolved_tenant = get_request_tenant(request.user)
    if not resolved_tenant:
        return None

    actor = user
    if actor is None and request is not None and getattr(request.user, 'is_authenticated', False):
        if request.user.is_authenticated:
            actor = request.user

    return AuditLog.objects.create(
        user=actor,
        tenant=resolved_tenant,
        action=action,
        module=module,
        description=description,
        ip_address=_client_ip(request),
        user_agent=(request.META.get('HTTP_USER_AGENT', '')[:500] if request else ''),
        metadata=metadata or {},
    )
