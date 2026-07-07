"""
Role Permission Models for Khata

This module defines the database models for storing role-based permissions.
Permissions are stored per tenant and can be customized for each role.
"""

from django.db import models
from utils.models import TenantModel


class RolePermission(TenantModel):
    """
    Stores permissions for each role within a tenant.
    Allows customization of role permissions per tenant.
    
    Each permission is stored as a boolean flag for a specific role, module, and action.
    """
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('supervisor', 'Supervisor'),
        ('accountant', 'Accountant'),
        ('cashier', 'Cashier'),
        ('viewer', 'Viewer'),
    ]
    
    MODULE_CHOICES = [
        ('dashboard', 'Dashboard'),
        ('sales', 'Sales'),
        ('purchase', 'Purchase'),
        ('inventory', 'Inventory'),
        ('accounting', 'Accounting'),
        ('construction', 'Construction'),
        ('hardware', 'Hardware'),
        ('reports', 'Reports'),
        ('settings', 'Settings'),
        ('hr', 'HR'),
        ('pos', 'POS'),
    ]
    
    ACTION_CHOICES = [
        ('view', 'View'),
        ('create', 'Create'),
        ('edit', 'Edit'),
        ('delete', 'Delete'),
        ('export', 'Export'),
        ('approve', 'Approve'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    module = models.CharField(max_length=50, choices=MODULE_CHOICES)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    allowed = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'role_permissions'
        unique_together = ['tenant', 'role', 'module', 'action']
        ordering = ['role', 'module', 'action']
        indexes = [
            models.Index(fields=['tenant', 'role']),
            models.Index(fields=['tenant', 'role', 'module']),
        ]
    
    def __str__(self):
        status = "✓" if self.allowed else "✗"
        return f"{status} {self.get_role_display()} - {self.get_module_display()} - {self.get_action_display()}"


def get_default_permissions():
    """
    Returns the default permission matrix for all roles.
    This is used to initialize permissions for new tenants.
    """
    return {
        'admin': {
            # Admin has all permissions
            'dashboard': ['view'],
            'sales': ['view', 'create', 'edit', 'delete', 'export'],
            'purchase': ['view', 'create', 'edit', 'delete', 'export', 'approve'],
            'inventory': ['view', 'create', 'edit', 'delete', 'export'],
            'accounting': ['view', 'create', 'edit', 'delete', 'export'],
            'construction': ['view', 'create', 'edit', 'delete', 'export'],
            'hardware': ['view', 'create', 'edit', 'delete', 'export'],
            'reports': ['view', 'export'],
            'settings': ['view', 'edit'],
            'hr': ['view', 'create', 'edit', 'delete'],
            'pos': ['view', 'create', 'edit', 'delete'],
        },
        'manager': {
            'dashboard': ['view'],
            'sales': ['view', 'create', 'edit', 'delete'],
            'purchase': ['view', 'create', 'edit', 'delete', 'approve'],
            'inventory': ['view', 'create', 'edit'],
            'construction': ['view', 'create', 'edit'],
            'hardware': ['view', 'create', 'edit'],
            'reports': ['view', 'export'],
            'settings': ['view', 'edit'],
            'hr': ['view', 'create', 'edit'],
            'pos': ['view', 'create', 'edit'],
        },
        'supervisor': {
            'dashboard': ['view'],
            'inventory': ['view', 'create', 'edit'],
            'construction': ['view', 'create', 'edit'],
            'hardware': ['view', 'create', 'edit'],
            'reports': ['view'],
        },
        'accountant': {
            'dashboard': ['view'],
            'accounting': ['view', 'create', 'edit', 'delete'],
            'sales': ['view'],
            'purchase': ['view'],
            'reports': ['view', 'export'],
        },
        'cashier': {
            'dashboard': ['view'],
            'sales': ['view', 'create'],
            'inventory': ['view'],
            'pos': ['view', 'create', 'edit', 'delete'],
            'reports': ['view'],
        },
        'viewer': {
            'dashboard': ['view'],
            'sales': ['view'],
            'purchase': ['view'],
            'inventory': ['view'],
            'accounting': ['view'],
            'construction': ['view'],
            'hardware': ['view'],
            'reports': ['view'],
            'settings': ['view'],
            'hr': ['view'],
        },
    }


def sync_tenant_permissions(tenant):
    """
    Ensure all default permissions exist for a tenant (backfill missing rows).
    Does not remove or downgrade custom permissions.
    """
    default_perms = get_default_permissions()
    created = 0
    for role, modules in default_perms.items():
        for module, actions in modules.items():
            for action in actions:
                _, was_created = RolePermission.objects.get_or_create(
                    tenant=tenant,
                    role=role,
                    module=module,
                    action=action,
                    defaults={'allowed': True},
                )
                if was_created:
                    created += 1
    return created


def initialize_tenant_permissions(tenant):
    """
    Initialize default permissions for a new tenant.
    This should be called when a new tenant is created.
    """
    default_perms = get_default_permissions()
    permissions_to_create = []
    
    for role, modules in default_perms.items():
        for module, actions in modules.items():
            for action in actions:
                permissions_to_create.append(
                    RolePermission(
                        tenant=tenant,
                        role=role,
                        module=module,
                        action=action,
                        allowed=True
                    )
                )
    
    # Bulk create all permissions
    RolePermission.objects.bulk_create(permissions_to_create, ignore_conflicts=True)
