"""
Dynamic Permission System for Khata

This module provides dynamic permission checking based on the RolePermission model.
Permissions are checked against the database for each request.
"""

from rest_framework import permissions
from .permission_models import RolePermission


class DynamicModulePermission(permissions.BasePermission):
    """
    Dynamic permission class that checks permissions from the database.
    
    Usage in ViewSet:
        permission_classes = [DynamicModulePermission]
        permission_module = 'sales'  # Define the module name
    
    This will automatically check:
    - GET/HEAD/OPTIONS requests: requires 'view' permission
    - POST requests: requires 'create' permission
    - PUT/PATCH requests: requires 'edit' permission
    - DELETE requests: requires 'delete' permission
    """
    
    def has_permission(self, request, view):
        # User must be authenticated
        if not request.user or not request.user.is_authenticated:
            return False
        
        # User must have a tenant
        if not request.user.tenant:
            return False
        
        # Get the module name from the view
        module = getattr(view, 'permission_module', None)
        if not module:
            # If no module specified, allow access (backward compatibility)
            return True
        
        # Check if tenant has this module activated
        if module not in request.user.tenant.active_modules:
            return False
        
        # Determine required action based on HTTP method
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
        
        # Check permission in database
        return self.check_permission(request.user, module, required_action)
    
    def check_permission(self, user, module, action):
        """
        Check if user has permission for the given module and action.
        """
        try:
            permission = RolePermission.objects.get(
                tenant=user.tenant,
                role=user.role,
                module=module,
                action=action
            )
            return permission.allowed
        except RolePermission.DoesNotExist:
            # If permission doesn't exist, deny access
            return False


class DynamicActionPermission(permissions.BasePermission):
    """
    Dynamic permission class for specific actions.
    
    Usage in ViewSet action:
        @action(detail=False, methods=['post'])
        @permission_classes([DynamicActionPermission])
        def export(self, request):
            # This will check for 'export' permission
            pass
    
    Set permission_module and permission_action in the view:
        permission_module = 'sales'
        permission_action = 'export'
    """
    
    def has_permission(self, request, view):
        # User must be authenticated
        if not request.user or not request.user.is_authenticated:
            return False
        
        # User must have a tenant
        if not request.user.tenant:
            return False
        
        # Get module and action from view
        module = getattr(view, 'permission_module', None)
        action = getattr(view, 'permission_action', None)
        
        if not module or not action:
            # If not specified, allow access (backward compatibility)
            return True
        
        # Check if tenant has this module activated
        if module not in request.user.tenant.active_modules:
            return False
        
        # Check permission in database
        try:
            permission = RolePermission.objects.get(
                tenant=request.user.tenant,
                role=request.user.role,
                module=module,
                action=action
            )
            return permission.allowed
        except RolePermission.DoesNotExist:
            return False


def has_permission(user, module, action):
    """
    Helper function to check if a user has a specific permission.
    Can be used in views, serializers, or anywhere else.
    
    Args:
        user: User instance
        module: Module name (e.g., 'sales', 'purchase')
        action: Action name (e.g., 'view', 'create', 'edit', 'delete')
    
    Returns:
        bool: True if user has permission, False otherwise
    """
    if not user or not user.is_authenticated:
        return False
    
    if not user.tenant:
        return False
    
    # Check if tenant has this module activated
    if module not in user.tenant.active_modules:
        return False
    
    try:
        permission = RolePermission.objects.get(
            tenant=user.tenant,
            role=user.role,
            module=module,
            action=action
        )
        return permission.allowed
    except RolePermission.DoesNotExist:
        return False


def get_user_permissions(user):
    """
    Get all permissions for a user as a dictionary.
    
    Returns:
        dict: Dictionary with module-action keys and boolean values
        Example: {'sales-view': True, 'sales-create': False, ...}
    """
    if not user or not user.is_authenticated or not user.tenant:
        return {}
    
    permissions = RolePermission.objects.filter(
        tenant=user.tenant,
        role=user.role,
        allowed=True
    )
    
    result = {}
    for perm in permissions:
        key = f"{perm.module}-{perm.action}"
        result[key] = True
    
    return result
