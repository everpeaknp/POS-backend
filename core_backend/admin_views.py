from django.contrib import messages
from django.shortcuts import redirect

from core_backend.admin_utils import admin_render
from core_backend.platform_analytics import platform_dashboard_stats
from mail import services as mail_services


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
