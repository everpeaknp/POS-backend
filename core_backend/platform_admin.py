"""
Platform admin configuration for KHATA.

Django admin is the internal control plane for KHATA operators (superusers),
not the customer-facing product. Business data is managed via the Next.js app + APIs.
"""

from django.contrib import admin
from django.contrib import messages

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


def _install_dashboard_index():
    """
    Make /admin/ itself render the analytics dashboard (KPIs, charts, quick
    actions) instead of the plain Django app-list index.

    admin/index.html (in core_backend/templates/, see TEMPLATES[0]['DIRS'])
    extends the default index and injects the dashboard body above the
    standard app-list/recent-actions, so this just needs to supply the
    `stats` context the template expects and to handle the "process mail
    queue" quick action posted from that page.
    """
    from core_backend.platform_analytics import platform_dashboard_stats
    from mail import services as mail_services

    original_index = admin.site.index

    def index(request, extra_context=None):
        if request.method == 'POST' and request.POST.get('action') == 'process_mail_queue':
            result = mail_services.process_email_queue()
            messages.success(request, f'Mail queue processed: {result}')

        stats = platform_dashboard_stats()
        extra_context = {
            **(extra_context or {}),
            'stats': stats,
            'charts': stats['charts'],
        }
        return original_index(request, extra_context)

    admin.site.index = index


def setup_platform_admin():
    """Apply platform admin restrictions after all apps are loaded."""
    _unregister_business_models()
    _restrict_admin_access()
    _install_dashboard_index()
