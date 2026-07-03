from decimal import Decimal

from django.db import models
from django.utils import timezone

from utils.models import TenantModel


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


class BillingPayment(TenantModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

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

    class Meta:
        db_table = 'billing_payments'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.transaction_uuid} — {self.plan_code} — {self.status}'


class EsewaSettings(models.Model):
    """Singleton platform settings for eSewa subscription payments."""

    enabled = models.BooleanField(
        default=True,
        help_text='Enable eSewa payments for subscription billing',
    )
    use_sandbox = models.BooleanField(
        default=True,
        help_text='Use eSewa test/sandbox environment (disable for live payments)',
    )
    product_code = models.CharField(
        max_length=100,
        blank=True,
        help_text='Merchant product code from eSewa (e.g. EPAYTEST for sandbox)',
    )
    secret_key = models.CharField(
        max_length=255,
        blank=True,
        help_text='eSewa HMAC secret key — keep confidential',
    )
    frontend_url = models.URLField(
        blank=True,
        help_text='Customer app base URL (e.g. http://localhost:3000)',
    )
    success_url = models.URLField(
        blank=True,
        help_text='Where eSewa redirects after successful payment. Leave blank to auto-use {frontend}/dashboard/settings/billing/success',
    )
    failure_url = models.URLField(
        blank=True,
        help_text='Where eSewa redirects after failed/cancelled payment. Leave blank to auto-use {frontend}/dashboard/settings/billing/failure',
    )
    payment_url = models.URLField(
        blank=True,
        help_text='eSewa payment form POST URL. Leave blank for sandbox/production default.',
    )
    status_url = models.URLField(
        blank=True,
        help_text='eSewa transaction verification API URL. Leave blank for sandbox/production default.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_esewa_settings'
        verbose_name = 'eSewa integration'
        verbose_name_plural = 'eSewa integration'

    def __str__(self):
        mode = 'Sandbox' if self.use_sandbox else 'Production'
        state = 'Enabled' if self.enabled else 'Disabled'
        return f'eSewa — {state} ({mode})'

    def delete(self, *args, **kwargs):
        pass

    def _base_frontend_url(self) -> str:
        from django.conf import settings as django_settings
        return (self.frontend_url or getattr(django_settings, 'FRONTEND_URL', '')).rstrip('/')

    def resolved_success_url(self) -> str:
        return self.success_url or (
            f'{self._base_frontend_url()}/dashboard/settings/billing/success'
            if self._base_frontend_url() else ''
        )

    def resolved_failure_url(self) -> str:
        return self.failure_url or (
            f'{self._base_frontend_url()}/dashboard/settings/billing/failure'
            if self._base_frontend_url() else ''
        )

    def resolved_payment_url(self) -> str:
        from billing.esewa_config import ESEWA_PRODUCTION, ESEWA_SANDBOX
        if self.payment_url:
            return self.payment_url
        endpoints = ESEWA_SANDBOX if self.use_sandbox else ESEWA_PRODUCTION
        return endpoints['payment_url']

    def resolved_status_url(self) -> str:
        from billing.esewa_config import ESEWA_PRODUCTION, ESEWA_SANDBOX
        if self.status_url:
            return self.status_url
        endpoints = ESEWA_SANDBOX if self.use_sandbox else ESEWA_PRODUCTION
        return endpoints['status_url']

    def save(self, *args, **kwargs):
        self.pk = 1
        base = self._base_frontend_url()
        if base and not self.success_url:
            self.success_url = f'{base}/dashboard/settings/billing/success'
        if base and not self.failure_url:
            self.failure_url = f'{base}/dashboard/settings/billing/failure'
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        from django.conf import settings as django_settings

        frontend = getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        obj, _created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'enabled': True,
                'use_sandbox': True,
                'product_code': getattr(django_settings, 'ESEWA_PRODUCT_CODE', 'EPAYTEST'),
                'secret_key': getattr(django_settings, 'ESEWA_SECRET_KEY', ''),
                'frontend_url': frontend,
                'success_url': f'{frontend}/dashboard/settings/billing/success',
                'failure_url': f'{frontend}/dashboard/settings/billing/failure',
            },
        )
        return obj

