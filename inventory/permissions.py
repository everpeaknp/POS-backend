"""
Custom permissions for Inventory module RBAC.
"""
from rest_framework import permissions


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
            return (
                request.user and 
                request.user.is_authenticated and 
                request.user.role in ['supervisor', 'admin']
            )
        
        return False
