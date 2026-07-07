from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from core_backend.platform_constants import AVAILABLE_MODULES
from billing.models import BillingPayment, Subscription, SubscriptionPlan
from billing import services as billing_services


class SubscriptionPlanAdminForm(forms.ModelForm):
    features_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 8, 'style': 'width: 100%; max-width: 640px;'}),
        label='Features',
        help_text='One feature per line. Shown on /settings/billing.',
    )
    module_choices = forms.MultipleChoiceField(
        choices=AVAILABLE_MODULES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Included modules',
        help_text='Modules enabled when a customer subscribes to this plan.',
    )

    class Meta:
        model = SubscriptionPlan
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['features_text'].initial = '\n'.join(self.instance.features or [])
            self.fields['module_choices'].initial = self.instance.modules or []
        self.fields['features'].widget = forms.HiddenInput()
        self.fields['features'].required = False
        self.fields['modules'].widget = forms.HiddenInput()
        self.fields['modules'].required = False

    def clean(self):
        cleaned = super().clean()
        features_text = cleaned.get('features_text') or ''
        cleaned['features'] = [line.strip() for line in features_text.splitlines() if line.strip()]
        cleaned['modules'] = list(cleaned.get('module_choices') or [])
        return cleaned

    def save(self, commit=True):
        self.instance.features = self.cleaned_data.get('features') or []
        self.instance.modules = self.cleaned_data.get('modules') or []
        return super().save(commit=commit)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    form = SubscriptionPlanAdminForm
    list_display = [
        'name', 'code', 'price', 'max_users_display', 'max_orgs_display',
        'plan_type', 'is_active', 'is_popular', 'sort_order',
    ]
    list_editable = ['is_active', 'is_popular', 'sort_order', 'price']
    list_filter = ['is_active', 'plan_type', 'is_popular']
    search_fields = ['name', 'code']
    ordering = ['sort_order', 'code']
    readonly_fields = ['created_at', 'updated_at', 'customer_preview']

    fieldsets = (
        ('Plan identity', {
            'fields': ('name', 'code', 'plan_type', 'sort_order', 'customer_preview'),
            'description': 'Plans listed here appear on the customer billing page at /settings/billing.',
        }),
        ('Pricing & limits', {
            'fields': ('price', 'max_users', 'max_orgs'),
        }),
        ('Customer-facing content', {
            'fields': ('features_text', 'features', 'module_choices', 'modules'),
        }),
        ('Visibility', {
            'fields': ('is_active', 'is_popular'),
            'description': 'Inactive plans are hidden from checkout. Mark one plan as popular to highlight it.',
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Monthly price')
    def price_display(self, obj):
        if obj.price == 0:
            return 'Free'
        return f'NPR {obj.price:,.2f}'

    @admin.display(description='Users')
    def max_users_display(self, obj):
        return obj.max_users if obj.max_users is not None else 'Unlimited'

    @admin.display(description='Organizations')
    def max_orgs_display(self, obj):
        return obj.max_orgs if obj.max_orgs is not None else 'Unlimited'

    @admin.display(description='Customer app preview')
    def customer_preview(self, obj):
        if not obj or not obj.pk:
            return 'Save the plan to preview how it appears to customers.'
        state = 'Visible on billing page' if obj.is_active else 'Hidden (inactive)'
        popular = ' · Most popular' if obj.is_popular else ''
        modules = ', '.join(obj.modules or []) or '—'
        return format_html(
            '<div style="padding:12px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;'
            'font-size:13px;line-height:1.6;">'
            '<strong>{}</strong> — NPR {}/month<br>'
            '<span style="color:#64748b;">{}</span><br>'
            '<span style="color:#64748b;">Modules: {}</span>'
            '</div>',
            obj.name,
            '0' if obj.price == 0 else f'{obj.price:,.2f}',
            f'{state}{popular}',
            modules,
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