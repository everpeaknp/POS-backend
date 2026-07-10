from django.contrib import admin, messages
from django.utils.html import format_html

from billing.account_limits import count_tenant_members
from billing.models import Subscription
from billing.plans import get_plan_type_to_code_map, get_plan
from billing.services import ensure_subscription
from tenants.forms import TenantAdminForm
from .models import Tenant
from .invitation_models import OrganizationInvitation
from .membership_models import UserTenantMembership


class UserTenantMembershipInline(admin.TabularInline):
    model = UserTenantMembership
    extra = 0
    fields = ['user', 'role', 'joined_at']
    readonly_fields = ['joined_at']
    autocomplete_fields = ['user']


class SubscriptionInline(admin.StackedInline):
    model = Subscription
    extra = 0
    max_num = 1
    can_delete = False
    readonly_fields = ['plan_code', 'status', 'current_period_start', 'current_period_end', 'auto_renew']
    fields = ['plan_code', 'status', 'current_period_start', 'current_period_end', 'auto_renew']

    def get_queryset(self, request):
        return Subscription._base_manager.all()


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    form = TenantAdminForm
    list_display = [
        'name', 'slug', 'business_type', 'plan_type',
        'module_summary', 'is_active', 'member_count', 'created_at',
    ]
    list_filter = ['business_type', 'plan_type', 'is_active', 'created_from_registration']
    search_fields = ['name', 'slug', 'email', 'owner_name', 'workspace_name']
    readonly_fields = ['slug', 'created_at', 'updated_at', 'member_count', 'subscription_status']
    inlines = [UserTenantMembershipInline, SubscriptionInline]
    actions = ['sync_subscription', 'apply_plan_modules_from_catalog']

    fieldsets = (
        ('Organization', {
            'fields': ('name', 'slug', 'workspace_name', 'logo', 'business_type', 'created_by', 'is_active'),
        }),
        ('Contact & legal', {
            'fields': ('owner_name', 'email', 'phone', 'address', 'pan_vat_number', 'website'),
        }),
        ('Accounting', {
            'fields': ('accounting_start_date', 'vat_registered'),
        }),
        ('Subscription & modules', {
            'fields': (
                'plan_type', 'subscription_status', 'created_from_registration',
                'active_module_choices', 'active_modules',
            ),
            'description': 'Modules control what appears in the customer app (localhost:3000).',
        }),
        ('Stats', {
            'fields': ('member_count',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Modules')
    def module_summary(self, obj):
        mods = obj.active_modules or []
        if not mods:
            return '—'
        text = ', '.join(mods[:4])
        if len(mods) > 4:
            text += f' +{len(mods) - 4}'
        return text

    @admin.display(description='Billing subscription')
    def subscription_status(self, obj):
        if not obj.pk:
            return '—'
        sub = ensure_subscription(obj)
        warn = ''
        expected = get_plan_type_to_code_map().get(obj.plan_type, 'free')
        if sub.plan_code != expected:
            warn = format_html(' <span style="color:#dc2626;">(plan mismatch)</span>')
        return format_html(
            '{} — {} until {}{}',
            sub.plan_code,
            sub.status,
            sub.current_period_end or '—',
            warn,
        )

    @admin.action(description='Sync subscription from plan type')
    def sync_subscription(self, request, queryset):
        for tenant in queryset:
            ensure_subscription(tenant)
        self.message_user(request, f'Synced subscription for {queryset.count()} tenant(s).', messages.SUCCESS)

    @admin.action(description='Apply plan modules from catalog')
    def apply_plan_modules_from_catalog(self, request, queryset):
        updated = 0
        for tenant in queryset:
            code = get_plan_type_to_code_map().get(tenant.plan_type, 'free')
            try:
                plan = get_plan(code)
                tenant.active_modules = plan['modules']
                tenant.save(update_fields=['active_modules', 'updated_at'])
                ensure_subscription(tenant)
                updated += 1
            except ValueError as exc:
                self.message_user(request, f'{tenant.name}: {exc}', messages.ERROR)
        if updated:
            self.message_user(request, f'Applied catalog modules to {updated} tenant(s).', messages.SUCCESS)

    @admin.display(description='Members')
    def member_count(self, obj):
        total = count_tenant_members(obj)
        return format_html('<span title="Active members (deduplicated)">{}</span>', total)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        ensure_subscription(obj)


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(admin.ModelAdmin):
    list_display = [
        'recipient_display', 'tenant', 'role', 'status_display',
        'invited_by', 'created_at', 'expires_at', 'token',
    ]
    list_filter = ['status', 'role', 'created_at']
    search_fields = [
        'invited_user__email',
        'invited_user__username',
        'invited_email',
        'tenant__name',
        'token',
    ]
    readonly_fields = ['token', 'created_at', 'updated_at', 'responded_at', 'is_expired']
    autocomplete_fields = ['invited_user', 'invited_by', 'tenant']
    actions = ['resend_invitation_email', 'revoke_invitations']

    fieldsets = (
        ('Invitation', {
            'fields': ('tenant', 'invited_user', 'invited_email', 'invited_by', 'role', 'message', 'token'),
        }),
        ('Status', {
            'fields': ('status', 'expires_at', 'is_expired', 'responded_at'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Invitee')
    def recipient_display(self, obj):
        return obj.recipient_email or '—'

    @admin.display(description='Status', ordering='status')
    def status_display(self, obj):
        labels = {
            'pending': ('Pending', '#ca8a04'),
            'accepted': ('Accepted', '#16a34a'),
            'declined': ('Declined', '#6b7280'),
            'expired': ('Expired', '#dc2626'),
            'cancelled': ('Revoked', '#dc2626'),
        }
        label, color = labels.get(obj.status, (obj.status, '#6b7280'))
        return format_html('<span style="color:{};font-weight:600;">{}</span>', color, label)

    @admin.action(description='Resend invitation email')
    def resend_invitation_email(self, request, queryset):
        sent = 0
        for invitation in queryset:
            try:
                invitation.resend()
                sent += 1
            except Exception as exc:
                self.message_user(request, f'{invitation}: {exc}', messages.ERROR)
        if sent:
            self.message_user(request, f'Resent {sent} invitation email(s).', messages.SUCCESS)

    @admin.action(description='Revoke selected invitations')
    def revoke_invitations(self, request, queryset):
        revoked = 0
        for invitation in queryset.filter(status='pending'):
            try:
                invitation.revoke()
                revoked += 1
            except Exception as exc:
                self.message_user(request, str(exc), messages.ERROR)
        if revoked:
            self.message_user(request, f'Revoked {revoked} invitation(s).', messages.SUCCESS)


@admin.register(UserTenantMembership)
class UserTenantMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'tenant', 'role', 'is_active', 'joined_at']
    list_filter = ['role', 'is_active', 'joined_at', 'tenant']
    search_fields = ['user__email', 'user__username', 'tenant__name']
    readonly_fields = ['joined_at', 'updated_at']
    autocomplete_fields = ['user', 'tenant']

    fieldsets = (
        ('Membership', {
            'fields': ('user', 'tenant', 'role', 'is_active'),
        }),
        ('Timestamps', {
            'fields': ('joined_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
