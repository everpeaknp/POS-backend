"""
Organization Invitation System
Allows users to invite other registered users to join their organization
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class OrganizationInvitation(models.Model):
    """
    Invitation to join an organization
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Invitation details
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='invitations'
    )
    invited_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_invitations',
        help_text="User being invited"
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_invitations',
        help_text="User who sent the invitation"
    )
    
    # Role assignment
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
        default='viewer',
        help_text="Role to assign when invitation is accepted"
    )
    
    # Status and timestamps
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    message = models.TextField(
        blank=True,
        help_text="Optional message from inviter"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(
        help_text="Invitation expiry date"
    )
    responded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When user accepted/declined"
    )
    
    class Meta:
        db_table = 'organization_invitations'
        ordering = ['-created_at']
        # Removed unique_together constraint to allow multiple invitations with different statuses
        # The validation is now handled in the serializer to prevent duplicate pending invitations
        indexes = [
            models.Index(fields=['invited_user', 'status']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.invited_user.email} invited to {self.tenant.name} as {self.role}"
    
    def save(self, *args, **kwargs):
        # Set expiry date if not set (7 days from now)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)
    
    @property
    def is_expired(self):
        """Check if invitation has expired"""
        return timezone.now() > self.expires_at and self.status == 'pending'
    
    def accept(self):
        """Accept the invitation and add user to organization"""
        if self.status != 'pending':
            raise ValueError("Only pending invitations can be accepted")
        
        if self.is_expired:
            self.status = 'expired'
            self.save()
            raise ValueError("This invitation has expired")
        
        # Import here to avoid circular import
        from .membership_models import UserTenantMembership
        
        # Check if user is already a member of this tenant
        existing_membership = UserTenantMembership.objects.filter(
            user=self.invited_user,
            tenant=self.tenant
        ).first()
        
        if existing_membership:
            # Update the role if membership already exists
            existing_membership.role = self.role
            existing_membership.save()
        else:
            # Create new membership
            UserTenantMembership.objects.create(
                user=self.invited_user,
                tenant=self.tenant,
                role=self.role
            )
        
        # If user doesn't have a primary tenant, set this as their primary tenant
        if not self.invited_user.tenant:
            self.invited_user.tenant = self.tenant
            self.invited_user.role = self.role
            self.invited_user.save()
        
        # Update invitation status
        self.status = 'accepted'
        self.responded_at = timezone.now()
        self.save()
        
        return True
    
    def decline(self):
        """Decline the invitation"""
        if self.status != 'pending':
            raise ValueError("Only pending invitations can be declined")
        
        self.status = 'declined'
        self.responded_at = timezone.now()
        self.save()
        
        return True
    
    def cancel(self):
        """Cancel the invitation (by inviter)"""
        if self.status != 'pending':
            raise ValueError("Only pending invitations can be cancelled")
        
        self.status = 'cancelled'
        self.save()
        
        return True
