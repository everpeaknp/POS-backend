"""
Organization Invitation System
Allows inviting registered users or email addresses that have not signed up yet.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import uuid


class OrganizationInvitation(models.Model):
    """Invitation to join an organization."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='invitations',
    )
    invited_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_invitations',
        null=True,
        blank=True,
        help_text='User being invited (null until they register)',
    )
    invited_email = models.EmailField(
        blank=True,
        default='',
        db_index=True,
        help_text='Email address invited (supports users who have not signed up yet)',
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_invitations',
        help_text='User who sent the invitation',
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
        default='viewer',
        help_text='Role to assign when invitation is accepted',
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    message = models.TextField(blank=True, help_text='Optional message from inviter')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(help_text='Invitation expiry date')
    responded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When user accepted/declined',
    )

    class Meta:
        db_table = 'organization_invitations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['invited_user', 'status']),
            models.Index(fields=['invited_email', 'status']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        target = self.invited_email or (self.invited_user.email if self.invited_user_id else 'unknown')
        return f"{target} invited to {self.tenant.name} as {self.role}"

    def save(self, *args, **kwargs):
        if self.invited_email:
            self.invited_email = self.invited_email.strip().lower()
        elif self.invited_user_id and self.invited_user and self.invited_user.email:
            self.invited_email = self.invited_user.email.strip().lower()

        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at and self.status == 'pending'

    @property
    def recipient_email(self):
        if self.invited_email:
            return self.invited_email
        if self.invited_user_id and self.invited_user:
            return self.invited_user.email
        return ''

    def _assert_can_accept_seat(self):
        """Ensure accepting would not exceed plan seats (pending invite already counted)."""
        from billing.account_limits import count_tenant_members, get_tenant_plan_code
        from billing.plans import get_plan

        plan = get_plan(get_tenant_plan_code(self.tenant))
        max_users = plan.get('max_users')
        if max_users is None:
            return

        # This pending invite already reserved a seat; convert to member only if
        # current membership count is still under the plan max.
        if count_tenant_members(self.tenant) >= max_users:
            raise ValueError(
                f'This organization has reached its {plan["name"]} plan user limit. '
                'Ask an admin to upgrade or free a seat.'
            )

    def accept(self, user=None):
        """Accept the invitation and add the user to the organization."""
        if self.status != 'pending':
            raise ValueError('Only pending invitations can be accepted')

        if self.is_expired:
            self.status = 'expired'
            self.save(update_fields=['status'])
            raise ValueError('This invitation has expired')

        accepting_user = user or self.invited_user
        if not accepting_user:
            raise ValueError('Create an account with the invited email before accepting')

        email = (accepting_user.email or '').strip().lower()
        invited = (self.invited_email or '').strip().lower()
        if invited and email != invited:
            raise ValueError('This invitation was sent to a different email address')

        self._assert_can_accept_seat()

        from .membership_models import UserTenantMembership

        if self.invited_user_id != accepting_user.id:
            self.invited_user = accepting_user

        existing_membership = UserTenantMembership.objects.filter(
            user=accepting_user,
            tenant=self.tenant,
        ).first()

        if existing_membership:
            existing_membership.role = self.role
            existing_membership.save(update_fields=['role', 'updated_at'])
        else:
            UserTenantMembership.objects.create(
                user=accepting_user,
                tenant=self.tenant,
                role=self.role,
            )

        if not accepting_user.tenant_id:
            accepting_user.tenant = self.tenant
            accepting_user.role = self.role
            accepting_user.save(update_fields=['tenant', 'role'])
        elif accepting_user.tenant_id == self.tenant_id:
            accepting_user.role = self.role
            accepting_user.save(update_fields=['role'])

        self.status = 'accepted'
        self.responded_at = timezone.now()
        self.save(update_fields=['invited_user', 'status', 'responded_at', 'updated_at', 'invited_email'])

        try:
            from mail.services import dispatch_acceptance_email
            dispatch_acceptance_email(self)
        except Exception:
            pass

        return True

    def decline(self, user=None):
        if self.status != 'pending':
            raise ValueError('Only pending invitations can be declined')

        declining_user = user or self.invited_user
        if declining_user and self.invited_user_id is None:
            self.invited_user = declining_user

        self.status = 'declined'
        self.responded_at = timezone.now()
        self.save(update_fields=['invited_user', 'status', 'responded_at', 'updated_at'])
        return True

    def cancel(self):
        if self.status != 'pending':
            raise ValueError('Only pending invitations can be cancelled')
        self.status = 'cancelled'
        self.save(update_fields=['status', 'updated_at'])
        return True

    def revoke(self):
        return self.cancel()

    def resend(self):
        if self.status != 'pending':
            raise ValueError('Only pending invitations can be resent')
        if self.is_expired:
            raise ValueError('Cannot resend an expired invitation')
        from mail.services import dispatch_invitation_email
        return dispatch_invitation_email(self)


def claim_pending_invitations_for_user(user):
    """Attach any email-only pending invites to a newly registered user."""
    email = (user.email or '').strip().lower()
    if not email:
        return 0

    pending = OrganizationInvitation.objects.filter(
        invited_email=email,
        status='pending',
        invited_user__isnull=True,
    )
    return pending.update(invited_user=user)
