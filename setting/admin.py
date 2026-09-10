from django import forms
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.widgets import (
    UnfoldAdminPasswordWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextInputWidget,
)

from setting.models import DefaultAppearanceSettings, EsewaSettings, GoogleOAuthSettings, SiteSettings


# Presets mirrored from frontend/app/settings/appearance/page.tsx so the
# platform admin picks defaults from the same palette users see themselves.
ACCENT_COLOR_CHOICES = [
    ("", "— Field default —"),
    ("#3B82F6", "Blue"),
    ("#6366F1", "Indigo"),
    ("#8B5CF6", "Violet"),
    ("#A855F7", "Purple"),
    ("#F43F5E", "Rose"),
    ("#EC4899", "Pink"),
    ("#F97316", "Orange"),
    ("#F59E0B", "Amber"),
    ("#22C55E", "Green"),
    ("#10B981", "Emerald"),
    ("#06B6D4", "Cyan"),
]

SIDEBAR_NAVBAR_COLOR_CHOICES = [
    ("", "— Field default —"),
    ("#1E2A3B", "Navy"),
    ("#1F2937", "Charcoal"),
    ("#0F172A", "Midnight"),
    ("#334155", "Slate"),
    ("#312E81", "Indigo"),
    ("#4C1D4C", "Plum"),
    ("#1B4332", "Forest"),
    ("#4C0519", "Wine"),
    ("#3B2F2F", "Espresso"),
    ("#111111", "Black"),
    ("#FFFFFF", "White"),
]

BORDER_RADIUS_CHOICES = [
    ("", "— Field default —"),
    ("0rem", "Sharp"),
    ("0.375rem", "Small"),
    ("0.625rem", "Default"),
    ("1rem", "Large"),
    ("1.5rem", "Full"),
]


class ColorSwatchSelect(UnfoldAdminSelectWidget):
    """A <select> with a live color-swatch preview next to it.

    Extends Unfold's own UnfoldAdminSelectWidget (not plain forms.Select)
    so the <select> itself gets Unfold's Tailwind classes and styled
    template — a bare forms.Select renders Django's unstyled default
    template, which is why this looked like plain unstyled text before.
    """

    def render(self, name, value, attrs=None, renderer=None):
        attrs = dict(attrs or {})
        widget_id = attrs.get("id", f"id_{name}")
        swatch_id = f"{widget_id}_swatch"
        attrs["onchange"] = (
            f"document.getElementById('{swatch_id}').style.background="
            f"this.value || 'transparent';"
        )
        select_html = super().render(name, value, attrs, renderer)
        preview = value or "transparent"
        swatch = (
            f'<span id="{swatch_id}" style="display:inline-block;width:28px;height:28px;'
            f'border-radius:6px;border:1px solid rgba(0,0,0,.25);background:{preview};'
            f'vertical-align:middle;margin-right:10px;flex-shrink:0;"></span>'
        )
        return mark_safe(
            f'<div style="display:flex;align-items:center;">{swatch}{select_html}</div>'
        )


class RadiusPreviewSelect(UnfoldAdminSelectWidget):
    """A <select> with a live corner-radius preview box next to it."""

    def render(self, name, value, attrs=None, renderer=None):
        attrs = dict(attrs or {})
        widget_id = attrs.get("id", f"id_{name}")
        preview_id = f"{widget_id}_preview"
        attrs["onchange"] = (
            f"document.getElementById('{preview_id}').style.borderRadius="
            f"this.value || '0.625rem';"
        )
        select_html = super().render(name, value, attrs, renderer)
        preview = value or "0.625rem"
        box = (
            f'<span id="{preview_id}" style="display:inline-block;width:28px;height:28px;'
            f'background:#8B5CF6;border-radius:{preview};'
            f'vertical-align:middle;margin-right:10px;flex-shrink:0;"></span>'
        )
        return mark_safe(
            f'<div style="display:flex;align-items:center;">{box}{select_html}</div>'
        )


class DefaultAppearanceSettingsForm(forms.ModelForm):
    accent_color = forms.ChoiceField(
        choices=ACCENT_COLOR_CHOICES, required=False, widget=ColorSwatchSelect
    )
    sidebar_color = forms.ChoiceField(
        choices=SIDEBAR_NAVBAR_COLOR_CHOICES, required=False, widget=ColorSwatchSelect
    )
    navbar_color = forms.ChoiceField(
        choices=SIDEBAR_NAVBAR_COLOR_CHOICES, required=False, widget=ColorSwatchSelect
    )
    border_radius = forms.ChoiceField(
        choices=BORDER_RADIUS_CHOICES, required=False, widget=RadiusPreviewSelect
    )

    class Meta:
        model = DefaultAppearanceSettings
        fields = "__all__"


@admin.register(DefaultAppearanceSettings)
class DefaultAppearanceSettingsAdmin(UnfoldModelAdmin):
    """
    Singleton settings controlling the default theme applied to newly
    registered users on /settings/appearance. Only one row exists.

    Uses unfold.admin.ModelAdmin (not vanilla admin.ModelAdmin) so plain
    choice fields (theme, navbar_position) get Unfold's styled select
    widget automatically — vanilla ModelAdmin leaves Select fields as
    Django's bare, unstyled <select>, which is why this page's dropdowns
    rendered as plain text with no visible input box.
    """
    list_display = ['theme', 'accent_color', 'sidebar_color', 'navbar_color', 'border_radius', 'navbar_position']
    form = DefaultAppearanceSettingsForm
    fieldsets = (
        ('Theme', {
            'fields': ('theme', 'navbar_position'),
        }),
        ('Colors', {
            'fields': ('accent_color', 'sidebar_color', 'navbar_color'),
        }),
        ('Layout', {
            'fields': ('border_radius', 'compact_mode', 'smooth_animations', 'high_contrast'),
        }),
    )

    def has_add_permission(self, request):
        return not DefaultAppearanceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_obj = DefaultAppearanceSettings.get_solo()
        return HttpResponseRedirect(
            reverse('admin:setting_defaultappearancesettings_change', args=(settings_obj.pk,))
        )


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
class EsewaSettingsAdmin(UnfoldModelAdmin):
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
        badges = format_html_join(
            '',
            '<span style="display:inline-block;margin:0 6px 6px 0;padding:4px 10px;border-radius:9999px;'
            'font-size:12px;font-weight:600;color:#fff;background:{};">{}</span>',
            ((color, label) for label, color in checks),
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
            return format_html('<span class="text-base-400 dark:text-base-500">Not configured</span>')
        return format_html(
            '<code class="block p-3 rounded-default border border-base-200 bg-base-50 '
            'text-font-default-light dark:border-base-800 dark:bg-base-900 dark:text-font-default-dark '
            'text-xs break-all">{}</code>',
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
        widget=UnfoldAdminPasswordWidget(render_value=True, attrs={'style': 'width: 100%; max-width: 640px;'}),
        label='Client secret',
        help_text='Leave blank to keep the current secret.',
    )

    class Meta:
        model = GoogleOAuthSettings
        fields = '__all__'
        exclude = ['client_secret_encrypted']
        widgets = {
            'client_id': UnfoldAdminTextInputWidget(attrs={'style': 'width: 100%; max-width: 640px;'}),
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
class GoogleOAuthSettingsAdmin(UnfoldModelAdmin):
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
        badges = format_html_join(
            '',
            '<span style="display:inline-block;margin:0 6px 6px 0;padding:4px 10px;border-radius:9999px;'
            'font-size:12px;font-weight:600;color:#fff;background:{};">{}</span>',
            ((color, label) for label, color in checks),
        )
        return format_html('<div>{}</div>', badges)

    @admin.display(description='Google Cloud Console setup')
    def setup_notes(self, obj):
        from django.conf import settings as django_settings
        frontend = getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        return format_html(
            '<div class="p-3.5 rounded-default border border-base-200 bg-base-50 '
            'text-font-default-light dark:border-base-800 dark:bg-base-900 dark:text-font-default-dark '
            'text-[13px] leading-relaxed">'
            '<p class="m-0 mb-2"><strong>Authorized JavaScript origins</strong></p>'
            '<code class="block p-2 rounded-default border border-base-200 bg-white mb-3 '
            'dark:border-base-700 dark:bg-base-800">{}</code>'
            '<p class="m-0 mb-2">ID-token flow — redirect URIs are not required.</p>'
            '<p class="m-0">After saving, the Google button appears on login and signup when enabled.</p>'
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
class SiteSettingsAdmin(UnfoldModelAdmin):
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
        ('Cloudinary Storage (Optional)', {
            'fields': (
                'use_cloudinary',
                'cloudinary_cloud_name',
                'cloudinary_api_key',
                'cloudinary_api_secret',
            ),
            'description': 'Enable Cloudinary for cloud-based image storage with CDN delivery. If disabled, images are stored locally.',
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Logo preview')
    def logo_preview(self, obj):
        if obj and obj.logo:
            return format_html(
                '<img src="{}" alt="Logo" class="max-h-12 max-w-[200px] p-2 rounded-default '
                'border border-base-200 bg-white dark:border-base-700 dark:bg-base-800">',
                obj.logo.url,
            )
        return format_html('<span class="text-base-400 dark:text-base-500">No logo uploaded</span>')

    @admin.display(description='Favicon preview')
    def favicon_preview(self, obj):
        if obj and obj.favicon:
            return format_html(
                '<img src="{}" alt="Favicon" class="w-8 h-8 p-1 rounded-default '
                'border border-base-200 bg-white dark:border-base-700 dark:bg-base-800">',
                obj.favicon.url,
            )
        return format_html('<span class="text-base-400 dark:text-base-500">No favicon uploaded</span>')

    @admin.display(description='Open Graph preview')
    def og_image_preview(self, obj):
        if obj and obj.og_image:
            return format_html(
                '<img src="{}" alt="OG image" class="max-w-[280px] p-2 rounded-default '
                'border border-base-200 bg-white dark:border-base-700 dark:bg-base-800">',
                obj.og_image.url,
            )
        return format_html('<span class="text-base-400 dark:text-base-500">No OG image uploaded</span>')

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_obj = SiteSettings.get_solo()
        return HttpResponseRedirect(
            reverse('admin:setting_sitesettings_change', args=(settings_obj.pk,))
        )
