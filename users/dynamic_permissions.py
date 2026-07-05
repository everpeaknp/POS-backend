"""
Dynamic Permission System for Khata

This module provides dynamic permission checking based on the RolePermission model.
Permissions are checked against the database for each request.
"""

from rest_framework import permissions
from .permission_models import RolePermission, sync_tenant_permissions
from tenants.utils import get_request_tenant
from tenants.membership_models import UserTenantMembership


def tenant_has_active_module(tenant, module):
    """Case-insensitive check whether a module is enabled for the tenant."""
    if not tenant or not module:
        return False
    normalized = str(module).lower()
    active_modules = tenant.active_modules or []
    return any(str(m).lower() == normalized for m in active_modules)


def _effective_role(user, tenant):
    role = user.role
    membership = UserTenantMembership.objects.filter(user=user, tenant=tenant).first()
    if membership:
        role = membership.role
    return role


class DynamicModulePermission(permissions.BasePermission):
    """
    Dynamic permission class that checks permissions from the database.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        tenant = get_request_tenant(request.user)
        if not tenant:
            return False

        module = getattr(view, 'permission_module', None)
        if not module:
            return True

        if not tenant_has_active_module(tenant, module):
            return False

        action_map = {
            'GET': 'view',
            'HEAD': 'view',
            'OPTIONS': 'view',
            'POST': 'create',
            'PUT': 'edit',
            'PATCH': 'edit',
            'DELETE': 'delete',
        }
        required_action = action_map.get(request.method, 'view')
        return self.check_permission(request.user, module, required_action)

    def check_permission(self, user, module, action):
        tenant = get_request_tenant(user)
        if not tenant:
            return False

        role = _effective_role(user, tenant)
        if role == 'admin' or getattr(user, 'is_superuser', False):
            return True

        try:
            permission = RolePermission.objects.get(
                tenant=tenant,
                role=role,
                module=module,
                action=action,
            )
            return permission.allowed
        except RolePermission.DoesNotExist:
            sync_tenant_permissions(tenant)
            try:
                permission = RolePermission.objects.get(
                    tenant=tenant,
                    role=role,
                    module=module,
                    action=action,
                )
                return permission.allowed
            except RolePermission.DoesNotExist:
                return False


class DynamicActionPermission(permissions.BasePermission):
    """Dynamic permission class for specific view actions."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        tenant = get_request_tenant(request.user)
        if not tenant:
            return False

        module = getattr(view, 'permission_module', None)
        action = getattr(view, 'permission_action', None)
        if not module or not action:
            return True

        if not tenant_has_active_module(tenant, module):
            return False

        role = _effective_role(request.user, tenant)
        if role == 'admin' or getattr(request.user, 'is_superuser', False):
            return True

        try:
            permission = RolePermission.objects.get(
                tenant=tenant,
                role=role,
                module=module,
                action=action,
            )
            return permission.allowed
        except RolePermission.DoesNotExist:
            sync_tenant_permissions(tenant)
            try:
                permission = RolePermission.objects.get(
                    tenant=tenant,
                    role=role,
                    module=module,
                    action=action,
                )
                return permission.allowed
            except RolePermission.DoesNotExist:
                return False


def has_permission(user, module, action):
    """Helper to check if a user has a specific permission."""
    if not user or not user.is_authenticated:
        return False

    tenant = get_request_tenant(user)
    if not tenant:
        return False

    if not tenant_has_active_module(tenant, module):
        return False

    role = _effective_role(user, tenant)
    if role == 'admin' or getattr(user, 'is_superuser', False):
        return True

    try:
        permission = RolePermission.objects.get(
            tenant=tenant,
            role=role,
            module=module,
            action=action,
        )
        return permission.allowed
    except RolePermission.DoesNotExist:
        sync_tenant_permissions(tenant)
        try:
            permission = RolePermission.objects.get(
                tenant=tenant,
                role=role,
                module=module,
                action=action,
            )
            return permission.allowed
        except RolePermission.DoesNotExist:
            return False


def get_user_permissions(user):
    """Get all allowed permissions for a user as module-action keys."""
    if not user or not user.is_authenticated:
        return {}

    tenant = get_request_tenant(user)
    if not tenant:
        return {}

    role = _effective_role(user, tenant)
    if role == 'admin' or getattr(user, 'is_superuser', False):
        sync_tenant_permissions(tenant)
        perms = RolePermission.objects.filter(tenant=tenant, role='admin', allowed=True)
    else:
        sync_tenant_permissions(tenant)
        perms = RolePermission.objects.filter(tenant=tenant, role=role, allowed=True)

    result = {}
    for perm in perms:
        result[f"{perm.module}-{perm.action}"] = True
    return result
