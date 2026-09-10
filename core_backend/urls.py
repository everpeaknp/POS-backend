"""
URL configuration for core_backend project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from mail.admin_views import mail_dashboard
from core_backend.admin_views import (
    legacy_esewa_settings_change,
    legacy_google_oauth_settings_change,
    platform_dashboard,
)
from core_backend.views import root
from setting.admin_views import setting_hub
from tenants.admin_views import business_analytics

urlpatterns = [
    # Backend/API landing page — this project's actual user-facing
    # frontend is the separate Next.js app; this root just orients anyone
    # (or any uptime check) who hits the Django server directly.
    path('', root, name='root'),

    # Admin — custom dashboards must use admin_view for full Unfold shell (sidebar)
    path('admin/platform/', admin.site.admin_view(platform_dashboard), name='admin_platform_dashboard'),
    path('admin/mail/dashboard/', admin.site.admin_view(mail_dashboard), name='admin_mail_dashboard'),
    path('admin/setting/', admin.site.admin_view(setting_hub), name='admin_setting_hub'),
    path(
        'admin/tenants/business-analytics/',
        admin.site.admin_view(business_analytics),
        name='admin_tenants_business_analytics',
    ),
    path(
        'admin/billing/googleoauthsettings/<path:object_id>/change/',
        admin.site.admin_view(legacy_google_oauth_settings_change),
        name='admin_billing_googleoauthsettings_legacy',
    ),
    path(
        'admin/billing/esewasettings/<path:object_id>/change/',
        admin.site.admin_view(legacy_esewa_settings_change),
        name='admin_billing_esewasettings_legacy',
    ),
    path('admin/', admin.site.urls),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # API Endpoints
    path('api/auth/', include('users.urls')),
    path('api/tenants/', include('tenants.urls')),
    path('api/billing/', include('billing.urls')),
    path('api/setting/', include('setting.urls')),
    path('api/mail/', include('mail.urls')),
    path('api/inventory/', include('inventory.urls')),
    path('api/sales/', include('sales.urls')),
    path('api/purchase/', include('purchase.urls')),
    path('api/accounting/', include('accounting.urls')),
    path('api/construction/', include('construction.urls')),
    path('api/hardware/', include('hardware.urls')),
    path('api/reports/', include('reports.urls')),
    path('api/hr/', include('hr.urls')),
    path('api/pos/', include('pos.urls')),
    path('api/finance/', include('finance.urls')),  # Personal Finance
    path('api/helpdesk/', include('helpdesk.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
