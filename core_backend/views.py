from django.conf import settings
from django.shortcuts import render

# Mirrors the actual `path('api/<prefix>/', include(...))` entries in
# core_backend.urls — kept as a plain list (not introspected from
# urlpatterns) so the labels stay human-readable, but every prefix here
# must correspond to a real include() there.
API_MODULES = [
    ('Authentication & Users', 'api/auth/'),
    ('Tenants', 'api/tenants/'),
    ('Billing', 'api/billing/'),
    ('Settings', 'api/setting/'),
    ('Mail', 'api/mail/'),
    ('Inventory', 'api/inventory/'),
    ('Sales', 'api/sales/'),
    ('Purchase', 'api/purchase/'),
    ('Accounting', 'api/accounting/'),
    ('Construction', 'api/construction/'),
    ('Hardware', 'api/hardware/'),
    ('Reports', 'api/reports/'),
    ('HR', 'api/hr/'),
    ('POS', 'api/pos/'),
    ('Personal Finance', 'api/finance/'),
    ('Helpdesk', 'api/helpdesk/'),
]


def root(request):
    """
    Backend/API landing page at `/`. Purely informational — no database,
    cache, or other expensive calls, since this is the server's root and
    may be hit by uptime checks/crawlers.
    """
    spectacular = getattr(settings, 'SPECTACULAR_SETTINGS', {})
    context = {
        'api_title': spectacular.get('TITLE', 'API'),
        'api_version': spectacular.get('VERSION', ''),
        'api_base_url': request.build_absolute_uri('/api/'),
        'modules': API_MODULES,
    }
    return render(request, 'root.html', context)
