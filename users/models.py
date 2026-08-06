from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey


class User(AbstractUser):
    """
    Custom User model with tenant association and role-based access control.
    
    Roles:
    - ADMIN: Full access to all modules, can manage users and view all financial data
    - MANAGER: Access to assigned projects, can approve purchases, view project financials
    - SUPERVISOR: Day-to-day data entry (attendance, materials, stock), no financial access
    - ACCOUNTANT: View and manage financial data only, no inventory/operations access
    - VIEWER: Read-only access for external stakeholders
    """
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('supervisor', 'Supervisor'),
        ('accountant', 'Accountant'),
        ('cashier', 'Cashier'),
        ('viewer', 'Viewer'),
    ]
    
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.SET_NULL,
        related_name='users',
        null=True,
        blank=True
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='viewer')
    phone = models.CharField(max_length=20, blank=True)
    google_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    
    # For managers - assigned sites/projects
    assigned_sites = models.ManyToManyField(
        'construction.Site',
        related_name='assigned_managers',
        blank=True,
        help_text='Sites/projects this manager has access to'
    )
    
    class Meta:
        db_table = 'users'
        ordering = ['-date_joined']
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    @property
    def is_admin(self):
        """Check if user is admin"""
        return self.role == 'admin'
    
    @property
    def is_manager(self):
        """Check if user is manager"""
        return self.role == 'manager'
    
    @property
    def is_supervisor(self):
        """Check if user is supervisor"""
        return self.role == 'supervisor'
    
    @property
    def is_accountant(self):
        """Check if user is accountant"""
        return self.role == 'accountant'
    
    @property
    def is_cashier(self):
        """Check if user is cashier"""
        return self.role == 'cashier'
    
    @property
    def is_viewer(self):
        """Check if user is viewer"""
        return self.role == 'viewer'
    
    def get_tenant(self):
        """
        Get the user's tenant - either direct assignment or via membership.
        Only active memberships count; disabled org access must not resolve a tenant.
        """
        from tenants.membership_models import UserTenantMembership

        # Direct tenant assignment — only if membership is still enabled (or user is creator)
        if self.tenant_id:
            membership = UserTenantMembership.objects.filter(
                user=self, tenant_id=self.tenant_id
            ).first()
            if membership is None or membership.is_active:
                return self.tenant
            if self.tenant.created_by_id == self.id:
                return self.tenant
            # Stale primary tenant after org access was disabled
            return None

        membership = (
            UserTenantMembership.objects.filter(user=self, is_active=True)
            .select_related('tenant')
            .first()
        )
        if membership:
            return membership.tenant

        return None
    
    def has_module_access(self, module):
        """
        Check if user has access to a specific module
        
        Args:
            module: One of 'sales', 'purchase', 'inventory', 'construction', 
                   'accounting', 'reports', 'pos', 'hr', 'hardware', 'settings', 'dashboard'
        """
        from users.dynamic_permissions import tenant_has_active_module

        tenant = self.get_tenant()
        if not tenant:
            return False

        normalized = (module or '').lower()
        if not tenant_has_active_module(tenant, normalized):
            return False
        
        # Admin has access to everything (if tenant has the module)
        if self.is_admin:
            return True
        
        # Module-specific access rules based on role
        access_matrix = {
            'dashboard': ['admin', 'manager', 'supervisor', 'accountant', 'cashier', 'viewer'],
            'sales': ['admin', 'manager', 'accountant', 'cashier'],
            'purchase': ['admin', 'manager', 'accountant'],
            'inventory': ['admin', 'manager', 'supervisor', 'cashier'],
            'construction': ['admin', 'manager', 'supervisor'],
            'accounting': ['admin', 'accountant'],
            'hardware': ['admin', 'manager', 'supervisor'],
            'reports': ['admin', 'manager', 'accountant', 'cashier'],
            'settings': ['admin', 'manager'],
            'pos': ['admin', 'manager', 'supervisor', 'cashier'],
            'hr': ['admin', 'manager'],
        }

        return self.role in access_matrix.get(normalized, [])
    
    def can_approve_purchases(self):
        """Check if user can approve purchase requests"""
        return self.role in ['admin', 'manager']
    
    def can_manage_users(self):
        """Check if user can add/remove users and assign roles"""
        return self.is_admin
    
    def can_view_financials(self):
        """Check if user can view financial data"""
        return self.role in ['admin', 'manager', 'accountant']
    
    def can_edit_data(self):
        """Check if user can edit data (not just view)"""
        return self.role != 'viewer'



class AuditLog(models.Model):
    """
    Audit log for tracking user actions across the system
    """
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('view', 'View'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('export', 'Export'),
        ('import', 'Import'),
    ]
    
    # Who performed the action
    user = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs'
    )
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='audit_logs'
    )
    
    # What action was performed
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    module = models.CharField(max_length=50, help_text="Module name (sales, inventory, etc.)")
    
    # What object was affected (generic relation)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Details
    description = models.TextField(help_text="Human-readable description of the action")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Additional data (JSON)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['tenant', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action']),
            models.Index(fields=['module']),
        ]
    
    def __str__(self):
        username = self.user.username if self.user else "Unknown"
        return f"{username} - {self.action} - {self.module} - {self.created_at}"


# Import notification models
from users.notification_models import Notification
from users.appearance_models import AppearancePreferences
from users.session_models import UserSession

__all__ = ['User', 'Notification', 'AppearancePreferences', 'UserSession']
