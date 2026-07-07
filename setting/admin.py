from django import forms
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from setting.models import EsewaSettings, GoogleOAuthSettings, SiteSettings


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
            reverse('admin:setting_esewasettings_change', args=(settings_obj.pk,))
        )


class GoogleOAuthSettingsAdminForm(forms.ModelForm):
    client_secret = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True, attrs={'class': 'vTextField', 'style': 'width: 100%; max-width: 640px;'}),
        label='Client secret',
        help_text='Leave blank to keep the current secret.',
    )

    class Meta:
        model = GoogleOAuthSettings
        fields = '__all__'
        exclude = ['client_secret_encrypted']
        widgets = {
            'client_id': forms.TextInput(attrs={'style': 'width: 100%; max-width: 640px;'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['client_secret'].initial = self.instance.get_client_secret()

    def save(self, commit=True):
        instance = super().save(commit=False)
        raw_secret = self.cleaned_data.get('client_secret')
        if raw_secret:
            instance.set_client_secret(raw_secret)
        if commit:
            instance.save()
        return instance


@admin.register(GoogleOAuthSettings)
class GoogleOAuthSettingsAdmin(admin.ModelAdmin):
    """Singleton admin for Google OAuth on login and signup."""

    form = GoogleOAuthSettingsAdminForm

    readonly_fields = ['integration_summary', 'setup_notes', 'updated_at']

    fieldsets = (
        ('Integration status', {
            'fields': ('integration_summary', 'enabled', 'updated_at'),
            'description': 'Configure Google sign-in for /auth/login and /auth/signup.',
        }),
        ('Google OAuth credentials', {
            'fields': ('client_id', 'client_secret'),
            'description': (
                'Create credentials at console.cloud.google.com — OAuth 2.0 Client ID, Web application type.'
            ),
        }),
        ('Setup guide', {
            'fields': ('setup_notes',),
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
        if obj.client_id:
            checks.append(('Client ID set', '#16a34a'))
        else:
            checks.append(('Missing client ID', '#dc2626'))
        if obj.client_secret_encrypted:
            checks.append(('Client secret set', '#16a34a'))
        else:
            checks.append(('Client secret optional', '#6b7280'))
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

    @admin.display(description='Google Cloud Console setup')
    def setup_notes(self, obj):
        from django.conf import settings as django_settings
        frontend = getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        return format_html(
            '<div style="padding:12px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;'
            'font-size:13px;line-height:1.7;color:#334155;">'
            '<p style="margin:0 0 8px;"><strong>Authorized JavaScript origins</strong></p>'
            '<code style="display:block;padding:8px;background:#fff;border-radius:6px;margin-bottom:12px;">{}</code>'
            '<p style="margin:0 0 8px;">ID-token flow — redirect URIs are not required.</p>'
            '<p style="margin:0;">After saving, the Google button appears on login and signup when enabled.</p>'
            '</div>',
            frontend,
        )

    def has_add_permission(self, request):
        return not GoogleOAuthSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_obj = GoogleOAuthSettings.get_solo()
        return HttpResponseRedirect(
            reverse('admin:setting_googleoauthsettings_change', args=(settings_obj.pk,))
        )


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Singleton admin for site identity, branding, and SEO."""

    readonly_fields = [
        'logo_preview',
        'favicon_preview',
        'og_image_preview',
        'updated_at',
    ]

    fieldsets = (
        ('Site identity', {
            'fields': ('site_name', 'tagline', 'updated_at'),
            'description': 'Customer-facing product name and short tagline.',
        }),
        ('Branding assets', {
            'fields': (
                'logo_preview',
                'logo',
                'favicon_preview',
                'favicon',
                'og_image_preview',
                'og_image',
            ),
            'description': 'Upload logo and favicon used on login, signup, and shared links.',
        }),
        ('SEO defaults', {
            'fields': (
                'seo_title',
                'meta_description',
                'meta_keywords',
                'allow_search_indexing',
            ),
            'description': 'Default metadata for public pages and search engines.',
        }),
    )

    @admin.display(description='Logo preview')
    def logo_preview(self, obj):
        if obj and obj.logo:
            return format_html(
                '<img src="{}" alt="Logo" style="max-height:48px;max-width:200px;border:1px solid #e5e7eb;'
                'border-radius:8px;padding:8px;background:#fff;">',
                obj.logo.url,
            )
        return format_html('<span style="color:#9ca3af;">No logo uploaded</span>')

    @admin.display(description='Favicon preview')
    def favicon_preview(self, obj):
        if obj and obj.favicon:
            return format_html(
                '<img src="{}" alt="Favicon" style="width:32px;height:32px;border:1px solid #e5e7eb;'
                'border-radius:6px;padding:4px;background:#fff;">',
                obj.favicon.url,
            )
        return format_html('<span style="color:#9ca3af;">No favicon uploaded</span>')

    @admin.display(description='Open Graph preview')
    def og_image_preview(self, obj):
        if obj and obj.og_image:
            return format_html(
                '<img src="{}" alt="OG image" style="max-width:280px;border:1px solid #e5e7eb;'
                'border-radius:8px;background:#fff;">',
                obj.og_image.url,
            )
        return format_html('<span style="color:#9ca3af;">No OG image uploaded</span>')

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_obj = SiteSettings.get_solo()
        return HttpResponseRedirect(
            reverse('admin:setting_sitesettings_change', args=(settings_obj.pk,))
        )
