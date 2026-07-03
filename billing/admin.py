from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from billing.models import BillingPayment, EsewaSettings, Subscription
from billing import services as billing_services


class EsewaSettingsAdminForm(forms.ModelForm):
    class Meta:
        model = EsewaSettings
        fields = '__all__'
        widgets = {
            'secret_key': forms.PasswordInput(render_value=True, attrs={'class': 'vTextField', 'style': 'width: 100%; max-width: 640px;'}),
            'frontend_url': forms.URLInput(attrs={'style': 'width: 100%; max-width: 640px;'}),
            'success_url': forms.URLInput(attrs={'style': 'width: 100%; max-width: 640px;'}),
            'failure_url': forms.URLInput(attrs={'style': 'width: 100%; max-width: 640px;'}),
            'payment_url': forms.URLInput(attrs={'style': 'width: 100%; max-width: 640px;'}),
            'status_url': forms.URLInput(attrs={'style': 'width: 100%; max-width: 640px;'}),
        }


@admin.register(EsewaSettings)
class EsewaSettingsAdmin(admin.ModelAdmin):
    """Singleton admin for eSewa payment gateway configuration."""

    form = EsewaSettingsAdminForm

    readonly_fields = [
        'integration_summary',
        'preview_payment_url',
        'preview_status_url',
        'preview_success_url',
        'preview_failure_url',
        'updated_at',
    ]

    fieldsets = (
        ('Integration status', {
            'fields': ('integration_summary', 'enabled', 'use_sandbox', 'updated_at'),
            'description': (
                'Enable or disable eSewa for subscription billing. '
                'Use sandbox mode while testing with eSewa test credentials (EPAYTEST).'
            ),
        }),
        ('Merchant credentials', {
            'fields': ('product_code', 'secret_key'),
            'description': 'Product code and secret key from your eSewa merchant account.',
        }),
        ('eSewa gateway URLs', {
            'fields': (
                'preview_payment_url',
                'payment_url',
                'preview_status_url',
                'status_url',
            ),
            'description': (
                '<strong>Payment URL</strong> — eSewa form endpoint where customers are sent to pay.<br>'
                '<strong>Status URL</strong> — API used to verify a transaction after payment.<br>'
                'Leave override fields empty to use the default sandbox or production URLs.'
            ),
        }),
        ('Customer redirect URLs', {
            'fields': (
                'frontend_url',
                'preview_success_url',
                'success_url',
                'preview_failure_url',
                'failure_url',
            ),
            'description': (
                '<strong>Payment success URL</strong> — customer returns here after a successful eSewa payment.<br>'
                '<strong>Payment failed URL</strong> — customer returns here if payment is cancelled or fails.<br>'
                'Set the frontend base URL first; success/failure URLs auto-fill on save if left empty.'
            ),
        }),
    )

    @admin.display(description='Configuration health')
    def integration_summary(self, obj):
        if not obj:
            return '—'
        checks = []
        if obj.enabled:
            checks.append(('Enabled', '#16a34a'))
        else:
            checks.append(('Disabled', '#6b7280'))
        checks.append(('Sandbox' if obj.use_sandbox else 'Production', '#2563eb'))
        if obj.product_code:
            checks.append(('Product code set', '#16a34a'))
        else:
            checks.append(('Missing product code', '#dc2626'))
        if obj.secret_key:
            checks.append(('Secret key set', '#16a34a'))
        else:
            checks.append(('Missing secret key', '#dc2626'))
        badges = ''.join(
            format_html(
                '<span style="display:inline-block;margin:0 6px 6px 0;padding:4px 10px;border-radius:9999px;'
                'font-size:12px;font-weight:600;color:#fff;background:{};">{}</span>',
                color,
                label,
            )
            for label, color in checks
        )
        return format_html('<div>{}</div>', badges)

    @admin.display(description='Active payment URL (eSewa)')
    def preview_payment_url(self, obj):
        return self._url_preview(obj.resolved_payment_url() if obj else '')

    @admin.display(description='Active status URL (eSewa API)')
    def preview_status_url(self, obj):
        return self._url_preview(obj.resolved_status_url() if obj else '')

    @admin.display(description='Active payment success URL')
    def preview_success_url(self, obj):
        return self._url_preview(obj.resolved_success_url() if obj else '')

    @admin.display(description='Active payment failed URL')
    def preview_failure_url(self, obj):
        return self._url_preview(obj.resolved_failure_url() if obj else '')

    def _url_preview(self, url: str):
        if not url:
            return format_html('<span style="color:#9ca3af;">Not configured</span>')
        return format_html(
            '<code style="display:block;padding:8px 12px;background:#f3f4f6;border-radius:6px;'
            'font-size:12px;word-break:break-all;">{}</code>',
            url,
        )

    def has_add_permission(self, request):
        return not EsewaSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_obj = EsewaSettings.get_solo()
        return HttpResponseRedirect(
            reverse('admin:billing_esewasettings_change', args=(settings_obj.pk,))
        )


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'plan_code', 'status', 'current_period_end', 'auto_renew']
    list_filter = ['status', 'plan_code']
    search_fields = ['tenant__name']
    actions = ['extend_30_days', 'activate_subscription', 'cancel_subscription']

    @admin.action(description='Extend period by 30 days')
    def extend_30_days(self, request, queryset):
        for sub in queryset:
            billing_services.admin_extend_subscription(sub, days=30)
        self.message_user(request, f'Extended {queryset.count()} subscription(s) by 30 days.', messages.SUCCESS)

    @admin.action(description='Set status to active')
    def activate_subscription(self, request, queryset):
        queryset.update(status='active')
        self.message_user(request, f'Activated {queryset.count()} subscription(s).', messages.SUCCESS)

    @admin.action(description='Cancel subscription')
    def cancel_subscription(self, request, queryset):
        queryset.update(status='cancelled', auto_renew=False)
        self.message_user(request, f'Cancelled {queryset.count()} subscription(s).', messages.WARNING)


@admin.register(BillingPayment)
class BillingPaymentAdmin(admin.ModelAdmin):
    list_display = [
        'transaction_uuid', 'tenant', 'plan_code', 'amount',
        'status', 'payment_method', 'completed_at',
    ]
    list_filter = ['status', 'plan_code', 'payment_method']
    search_fields = ['transaction_uuid', 'tenant__name']
    readonly_fields = ['callback_payload', 'completed_at', 'created_at', 'updated_at']
    actions = ['reverify_esewa', 'mark_failed', 'mark_cancelled']

    @admin.action(description='Re-verify with eSewa')
    def reverify_esewa(self, request, queryset):
        for payment in queryset:
            try:
                msg = billing_services.admin_reverify_payment(payment)
                level = messages.SUCCESS if 'activated' in msg or 'completed' in msg.lower() else messages.WARNING
                self.message_user(request, f'{payment.transaction_uuid}: {msg}', level)
            except Exception as exc:
                self.message_user(request, f'{payment.transaction_uuid}: {exc}', messages.ERROR)

    @admin.action(description='Mark as failed')
    def mark_failed(self, request, queryset):
        updated = queryset.exclude(status='completed').update(
            status='failed', failure_reason='Marked failed by platform admin',
        )
        self.message_user(request, f'Marked {updated} payment(s) as failed.', messages.WARNING)

    @admin.action(description='Mark as cancelled')
    def mark_cancelled(self, request, queryset):
        updated = queryset.exclude(status='completed').update(status='cancelled')
        self.message_user(request, f'Cancelled {updated} payment(s).', messages.WARNING)
