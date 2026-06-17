"""
User-Tenant Membership Model
Allows users to be members of multiple organizations
"""
from django.db import models
from django.conf import settings


class UserTenantMembership(models.Model):
    """
    Represents a user's membership in a tenant/organization
    Allows users to be members of multiple organizations
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tenant_memberships'
    )
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='user_memberships'
    )
    role = models.CharField(
        max_length=20,
        choices=[
            ('admin', 'Admin'),
            ('manager', 'Manager'),
            ('supervisor', 'Supervisor'),
            ('accountant', 'Accountant'),
            ('cashier', 'Cashier'),
            ('viewer', 'Viewer'),
        ],
        default='viewer'
    )
    
    # Timestamps
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_tenant_memberships'
        unique_together = [['user', 'tenant']]
        ordering = ['-joined_at']
        indexes = [
            models.Index(fields=['user', 'tenant']),
            models.Index(fields=['tenant']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.tenant.name} ({self.role})"
