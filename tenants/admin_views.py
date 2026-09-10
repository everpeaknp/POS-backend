from core_backend.admin_utils import admin_render
from tenants.analytics import business_dashboard_stats


def business_analytics(request):
    """Business (workplace/tenant) dedicated analytics at /admin/tenants/business-analytics/."""
    stats = business_dashboard_stats()
    return admin_render(request, 'admin/tenants/business_analytics.html', {
        'title': 'Business analytics',
        'stats': stats,
        'charts': stats['charts'],
    })

