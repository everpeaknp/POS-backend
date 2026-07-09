"""
Role-Based Access Control (RBAC) Permissions for Khata

This module defines permission classes for different user roles:
- ADMIN: Full access to everything
- MANAGER: Access to assigned projects, can approve purchases, view financials
- SUPERVISOR: Data entry only (attendance, materials, stock)
- ACCOUNTANT: Financial data only
- VIEWER: Read-only access
"""

from rest_framework import permissions


class IsAuthenticated(permissions.BasePermission):
    """
    Base permission - user must be authenticated
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class IsAdmin(permissions.BasePermission):
    """
    Permission class for admin-only access
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.is_admin
        )


class IsAdminOrManager(permissions.BasePermission):
    """
    Permission class for admin or manager access
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role in ['admin', 'manager']
        )


class IsAdminOrAccountant(permissions.BasePermission):
    """
    Permission class for admin or accountant access (financial data)
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role in ['admin', 'accountant']
        )


class CanViewFinancials(permissions.BasePermission):
    """
    Permission class for viewing financial data
    Allowed: admin, manager, accountant
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.can_view_financials()
        )


class CanApprovePurchases(permissions.BasePermission):
    """
    Permission class for approving purchase requests
    Allowed: admin, manager
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.can_approve_purchases()
        )


class CanManageUsers(permissions.BasePermission):
    """
    Permission class for user management
    Allowed: admin only
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.can_manage_users()
        )


class CanViewTenantSettings(permissions.BasePermission):
    """View users, audit logs, and settings pages."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        from users.dynamic_permissions import has_permission

        return has_permission(request.user, 'settings', 'view')


class CanViewAuditLogs(permissions.BasePermission):
    """Audit log access via dynamic settings-view permission."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        from users.dynamic_permissions import has_permission

        return has_permission(request.user, 'settings', 'view')


class CanEditTenantSettings(permissions.BasePermission):
    """Tenant settings edit or HR invite/assign for user management."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        from users.dynamic_permissions import has_permission

        if has_permission(request.user, 'settings', 'edit'):
            return True
        # HR: Invite = add users; Assign = change roles / membership access
        action = getattr(view, 'action', None)
        if action == 'create':
            return has_permission(request.user, 'hr', 'invite')
        if action in ('update', 'partial_update'):
            return has_permission(request.user, 'hr', 'assign')
        if action == 'destroy':
            return has_permission(request.user, 'hr', 'invite')
        return False


class CanInviteUsers(permissions.BasePermission):
    """Permission to invite / add users to the organization."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        from users.dynamic_permissions import has_permission
        return (
            has_permission(request.user, 'settings', 'edit')
            or has_permission(request.user, 'hr', 'invite')
        )


class CanAssignUserRoles(permissions.BasePermission):
    """Permission to change user roles in the organization."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        from users.dynamic_permissions import has_permission
        return (
            has_permission(request.user, 'settings', 'edit')
            or has_permission(request.user, 'hr', 'assign')
        )


class CanConfigurePermissions(permissions.BasePermission):
    """Permission to open Manage Permissions and edit the role matrix."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        from users.dynamic_permissions import has_permission
        return (
            has_permission(request.user, 'settings', 'edit')
            or has_permission(request.user, 'hr', 'configure')
        )


class CanEditData(permissions.BasePermission):
    """
    Permission class for editing data (not just viewing)
    Allowed: everyone except viewer
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.can_edit_data()
        )


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Admin can do anything, others can only read
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Read permissions for authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only for admin
        return request.user.is_admin


class RoleBasedPermission(permissions.BasePermission):
    """
    Generic role-based permission class
    
    Usage in ViewSet:
        permission_classes = [RoleBasedPermission]
        required_roles = ['admin', 'manager']  # Define in view
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get required roles from view
        required_roles = getattr(view, 'required_roles', None)
        
        if not required_roles:
            # No specific roles required, just authenticated
            return True
        
        # Check if user's role is in required roles
        return request.user.role in required_roles


class ModuleAccessPermission(permissions.BasePermission):
    """
    Permission based on module access
    
    Usage in ViewSet:
        permission_classes = [ModuleAccessPermission]
        required_module = 'sales'  # Define in view
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get required module from view
        required_module = getattr(view, 'required_module', None)
        
        if not required_module:
            # No specific module required
            return True
        
        # Check if user has access to module
        return request.user.has_module_access(required_module)


class IsSiteManager(permissions.BasePermission):
    """
    Permission for managers to access only their assigned sites
    """
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admin has access to all sites
        if request.user.is_admin:
            return True
        
        # Manager can only access assigned sites
        if request.user.is_manager:
            # Check if obj is a Site or has a site attribute
            site = obj if hasattr(obj, 'assigned_managers') else getattr(obj, 'site', None)
            if site:
                return request.user in site.assigned_managers.all()
        
        return False


class ReadOnlyOrEditPermission(permissions.BasePermission):
    """
    Viewers can only read, others can edit based on their role
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Viewers can only read
        if request.user.is_viewer:
            return request.method in permissions.SAFE_METHODS
        
        # Others can read and write based on module access
        return True


# Convenience permission combinations
class SalesPermission(permissions.BasePermission):
    """Sales module access: admin, manager, accountant"""
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.has_module_access('sales')
        )


class PurchasePermission(permissions.BasePermission):
    """Purchase module access: admin, manager, accountant"""
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.has_module_access('purchase')
        )


class InventoryPermission(permissions.BasePermission):
    """Inventory module access: admin, manager, supervisor"""
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.has_module_access('inventory')
        )


class ConstructionPermission(permissions.BasePermission):
    """Construction module access: admin, manager, supervisor"""
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.has_module_access('construction')
        )


class AccountingPermission(permissions.BasePermission):
    """Accounting module access: admin, accountant"""
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.has_module_access('accounting')
        )


class ReportsPermission(permissions.BasePermission):
    """Reports module access: admin, manager, accountant"""
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.has_module_access('reports')
        )
