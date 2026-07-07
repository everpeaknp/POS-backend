from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from utils.models import TenantModel


class UserSubscription(models.Model):
    """Account-level subscription for a Khata user (not tied to one organization)."""

    STATUS_CHOICES = [
        ('trialing', 'Trialing'),
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='account_subscription',
    )
    plan_code = models.CharField(max_length=32, default='free')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trialing')
    current_period_start = models.DateField(null=True, blank=True)
    current_period_end = models.DateField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_user_subscriptions'
        verbose_name = 'Account subscription'
        verbose_name_plural = 'Account subscriptions'

    def __str__(self):
        label = self.user.get_full_name() or self.user.email
        return f'{label} — {self.plan_code} ({self.status})'

    @property
    def is_active(self):
        if self.status not in ('active', 'trialing'):
            return False
        if self.current_period_end and self.current_period_end < timezone.now().date():
            return False
        return True


class Subscription(TenantModel):
    STATUS_CHOICES = [
        ('trialing', 'Trialing'),
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('cancelled', 'Cancelled'),
    ]

    plan_code = models.CharField(max_length=32, default='starter')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trialing')
    current_period_start = models.DateField(null=True, blank=True)
    current_period_end = models.DateField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)

    class Meta:
        db_table = 'billing_subscriptions'
        constraints = [
            models.UniqueConstraint(fields=['tenant'], name='unique_subscription_per_tenant'),
        ]

    def __str__(self):
        return f'{self.tenant.name} — {self.plan_code} ({self.status})'

    @property
    def is_active(self):
        if self.status not in ('active', 'trialing'):
            return False
        if self.current_period_end and self.current_period_end < timezone.now().date():
            return False
        return True


class BillingPayment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='billing_payments',
        help_text='Optional workspace linked to this payment record',
    )
    transaction_uuid = models.CharField(max_length=64, unique=True, db_index=True)
    plan_code = models.CharField(max_length=32)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, default='esewa')
    esewa_transaction_code = models.CharField(max_length=100, blank=True)
    esewa_reference_id = models.CharField(max_length=100, blank=True)
    initiated_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='billing_payments',
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    callback_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_payments'
        ordering = ['-created_at']

    def __str__(self):
        payer = self.initiated_by
        label = payer.get_full_name() if payer else (self.tenant.name if self.tenant_id else self.transaction_uuid)
        return f'{label} — {self.plan_code} — {self.status}'


class SubscriptionPlan(models.Model):
    """Platform subscription plan catalog shown at /settings/billing."""

    PLAN_TYPE_CHOICES = [
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('premium', 'Premium'),
        ('enterprise', 'Enterprise'),
    ]

    code = models.CharField(
        max_length=32,
        unique=True,
        help_text='Stable plan identifier used in checkout (e.g. starter, business)',
    )
    name = models.CharField(max_length=100)
    plan_type = models.CharField(
        max_length=20,
        choices=PLAN_TYPE_CHOICES,
        help_text='Maps to tenant.plan_type when a user subscribes',
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monthly price in NPR (0 = free)',
    )
    max_users = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Leave blank for unlimited users',
    )
    max_orgs = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Max organizations per account. Leave blank for unlimited.',
    )
    features = models.JSONField(
        default=list,
        blank=True,
        help_text='Bullet points shown on the billing page',
    )
    modules = models.JSONField(
        default=list,
        blank=True,
        help_text='Modules enabled for organizations on this plan',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Inactive plans are hidden from /settings/billing',
    )
    is_popular = models.BooleanField(
        default=False,
        help_text='Highlights this plan as "Most popular" in the customer app',
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_subscription_plans'
        ordering = ['sort_order', 'code']
        verbose_name = 'Subscription plan'
        verbose_name_plural = 'Subscription plans'

    def __str__(self):
        return f'{self.name} ({self.code})'

