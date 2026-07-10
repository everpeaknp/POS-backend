from django.contrib import messages
from django.shortcuts import redirect

from core_backend.admin_utils import admin_render
from core_backend.platform_analytics import platform_dashboard_stats
from mail import services as mail_services
from setting.models import EsewaSettings, GoogleOAuthSettings


def platform_dashboard(request):
    if not request.user.is_superuser:
        messages.error(request, 'Superuser access required.')
        return redirect('admin:index')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'process_mail_queue':
            result = mail_services.process_email_queue()
            messages.success(request, f'Mail queue processed: {result}')

    stats = platform_dashboard_stats()
    return admin_render(request, 'admin/platform/dashboard.html', {
        'title': 'Platform Analytics',
        'subtitle': 'Organizations, billing, users, and email delivery',
        'stats': stats,
        'charts': stats['charts'],
    })


def legacy_esewa_settings_change(request, object_id=None):
    """Redirect old /admin/billing/esewasettings/... URLs to setting app."""
    settings_obj = EsewaSettings.get_solo()
    return redirect('admin:setting_esewasettings_change', settings_obj.pk)


def legacy_google_oauth_settings_change(request, object_id=None):
    """Redirect old /admin/billing/googleoauthsettings/... URLs to setting app."""
    settings_obj = GoogleOAuthSettings.get_solo()
    return redirect('admin:setting_googleoauthsettings_change', settings_obj.pk)
