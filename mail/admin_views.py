from django.contrib import messages
from django.shortcuts import redirect

from core_backend.admin_utils import admin_render
from mail.models import EmailQueue, SmtpSettings
from mail import services


def mail_dashboard(request):
    if not request.user.is_superuser:
        messages.error(request, 'Superuser access required.')
        return redirect('admin:index')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'process_queue':
            result = services.process_email_queue()
            messages.success(request, f"Queue processed: {result}")
        elif action == 'pause_queue':
            EmailQueue.objects.filter(status='queued').update(status='paused')
            messages.warning(request, 'Email queue paused.')
        elif action == 'resume_queue':
            EmailQueue.objects.filter(status='paused').update(status='queued')
            messages.success(request, 'Email queue resumed.')

    stats = services.mail_dashboard_stats()
    smtp = SmtpSettings.get_solo()
    return admin_render(request, 'admin/mail/dashboard.html', {
        'title': 'Mail management',
        'stats': stats,
        'smtp_enabled': smtp.enabled,
        'queue_paused': EmailQueue.objects.filter(status='paused').exists(),
    })
