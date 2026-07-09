"""
Custom permissions for Inventory module RBAC.
"""
from rest_framework import permissions
from users.dynamic_permissions import _effective_role


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Authenticated users can read, create, update, and delete products.
    """
    
    def has_permission(self, request, view):
        # Allow all operations for authenticated users
        if request.user and request.user.is_authenticated:
            return True
        
        return False


class IsSupervisorOrAdmin(permissions.BasePermission):
    """
    Only SUPERVISOR or ADMIN users can create stock movements.
    All authenticated users can read.
    """
    
    def has_permission(self, request, view):
        # Allow read operations for all authenticated users
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Only SUPERVISOR or ADMIN can create stock movements
        if request.method == 'POST':
            if not (request.user and request.user.is_authenticated):
                return False
            tenant = getattr(request.user, 'tenant', None)
            role = _effective_role(request.user, tenant) if tenant else getattr(request.user, 'role', '')
            return role in ('supervisor', 'admin', 'super_admin')
        
        return False
