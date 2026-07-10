"""
Platform admin configuration for KHATA.

Django admin is the internal control plane for KHATA operators (superusers),
not the customer-facing product. Business data is managed via the Next.js app + APIs.
"""

from django.contrib import admin

# Apps whose models should not appear in platform admin
BUSINESS_APP_LABELS = frozenset({
    'inventory',
    'sales',
    'purchase',
    'accounting',
    'construction',
    'hr',
    'pos',
    'reports',
    'suppliers',
})

# Technical apps hidden from the sidebar
HIDDEN_APP_LABELS = frozenset({
    'token_blacklist',
})


def _unregister_business_models():
    """Remove tenant business models from Django admin."""
    for model in list(admin.site._registry):
        app_label = model._meta.app_label
        if app_label in BUSINESS_APP_LABELS or app_label in HIDDEN_APP_LABELS:
            admin.site.unregister(model)


def _restrict_admin_access():
    """Only KHATA platform superusers may use Django admin."""

    def has_permission(request):
        user = request.user
        return bool(user.is_active and user.is_superuser and user.is_staff)

    admin.site.has_permission = has_permission
    admin.site.site_header = 'KHATA Platform'
    admin.site.site_title = 'KHATA Platform Admin'
    admin.site.index_title = 'Platform operations'


def setup_platform_admin():
    """Apply platform admin restrictions after all apps are loaded."""
    _unregister_business_models()
    _restrict_admin_access()
