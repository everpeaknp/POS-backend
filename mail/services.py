"""Email sending, templating, queue, and campaign services."""

import logging
import re
import uuid
from datetime import timedelta

from django.conf import settings as django_settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template import Context, Template
from django.template.loader import render_to_string
from django.utils import timezone

from mail.models import EmailBranding, EmailLog, EmailQueue, EmailTemplate, MarketingCampaign, SmtpSettings

logger = logging.getLogger(__name__)

VARIABLE_PATTERN = re.compile(r'\{\{\s*(\w+)\s*\}\}')


def get_frontend_url() -> str:
    return getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')


def get_branding_context() -> dict:
    branding = EmailBranding.get_solo()
    return {
        'branding': branding,
        'company_name': branding.company_name,
        'dashboard_url': f'{get_frontend_url()}/dashboard',
        'unsubscribe_link': branding.unsubscribe_url or f'{get_frontend_url()}/dashboard/settings/profile',
    }


def render_template_string(template_str: str, context: dict) -> str:
    if not template_str:
        return ''
    return Template(template_str).render(Context(context))


def get_template(slug: str) -> EmailTemplate | None:
    return EmailTemplate.objects.filter(slug=slug, is_active=True).first()


def build_message_context(user=None, extra: dict | None = None) -> dict:
    ctx = get_branding_context()
    if user:
        ctx.update({
            'first_name': user.first_name or user.username,
            'last_name': user.last_name or '',
            'email': user.email,
            'full_name': user.get_full_name() or user.username,
        })
    if extra:
        ctx.update(extra)
    return ctx


def build_preview_context() -> dict:
    """Sample context for admin email template previews."""
    branding = EmailBranding.get_solo()
    frontend = get_frontend_url()
    return build_message_context(extra={
        'first_name': 'Alex',
        'last_name': 'Johnson',
        'email': 'alex@example.com',
        'full_name': 'Alex Johnson',
        'verification_link': f'{frontend}/auth/verify?token=preview',
        'invitation_link': f'{frontend}/invite/preview',
        'company_name': branding.company_name,
        'organization_name': 'Everacy Pvt. Ltd.',
        'inviter_name': 'Jane Admin',
        'role': 'Manager',
        'custom_message': 'Welcome to the team!',
        'expires_at': 'August 7, 2026',
        'plan_name': 'Business',
        'amount_display': 'NPR 2,999',
        'period_end': 'August 7, 2026',
        'billing_url': f'{frontend}/settings/billing',
        'transaction_uuid': 'TXN-2026-000123',
        'payment_method': 'eSewa',
        'failure_reason': 'Insufficient balance',
    })


def render_email_preview(subject: str, html_body: str) -> tuple[str, str]:
    ctx = build_preview_context()
    rendered_subject = render_template_string(subject or '', ctx)
    rendered_html = render_template_string(html_body or '', ctx)
    return rendered_subject, prepare_html_for_email(rendered_html)


def _wrap_email_document(html: str) -> str:
    if not html:
        return html
    lower = html.lower()
    if '<html' in lower:
        return html
    return (
        '<!DOCTYPE html>'
        '<html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '</head><body>'
        f'{html}'
        '</body></html>'
    )


def prepare_html_for_email(html: str) -> str:
    """Inline CSS so Gmail and other clients render template styles."""
    if not html:
        return html
    wrapped = _wrap_email_document(html)
    try:
        from premailer import transform
        return transform(
            wrapped,
            keep_style_tags=False,
            remove_classes=False,
            strip_important=False,
            disable_validation=True,
        )
    except Exception:
        return wrapped


def get_smtp_connection():
    smtp = SmtpSettings.get_solo()
    if not smtp.enabled or not smtp.host:
        return None
    use_ssl = smtp.encryption == 'ssl'
    use_tls = smtp.encryption == 'starttls'
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=smtp.host,
        port=smtp.port,
        username=smtp.username or None,
        password=smtp.get_password() or None,
        use_tls=use_tls,
        use_ssl=use_ssl,
        timeout=smtp.connection_timeout,
        fail_silently=False,
    )


def get_mail_connection():
    """Admin SMTP when configured; otherwise Django EMAIL_BACKEND (e.g. console in dev)."""
    connection = get_smtp_connection()
    if connection is not None:
        return connection
    if getattr(django_settings, 'DEBUG', False):
        return get_connection()
    return None


def create_email_log(to_email, subject, *, template_slug='', category='', user=None, invitation_id=None, campaign=None):
    tracking_id = uuid.uuid4()
    log = EmailLog.objects.create(
        tracking_id=tracking_id,
        to_email=to_email,
        subject=subject,
        template_slug=template_slug,
        category=category,
        status='queued',
        recipient_user=user,
        invitation_id=invitation_id,
        campaign=campaign,
    )
    return log


def tracking_pixel_url(log: EmailLog) -> str:
    base = getattr(django_settings, 'BACKEND_PUBLIC_URL', 'http://127.0.0.1:8000').rstrip('/')
    return f'{base}/api/mail/track/{log.tracking_id}/open/'


def inject_tracking_pixel(html_body: str, log: EmailLog) -> str:
    pixel_url = tracking_pixel_url(log)
    if pixel_url in html_body:
        return html_body
    pixel = f'<img src="{pixel_url}" width="1" height="1" alt="" style="display:none">'
    lower = html_body.lower()
    if '</body>' in lower:
        idx = lower.rfind('</body>')
        return html_body[:idx] + pixel + html_body[idx:]
    return f'{html_body}{pixel}'


def send_email_now(to_email, subject, html_body, text_body='', *, log: EmailLog | None = None):
    smtp = SmtpSettings.get_solo()
    if smtp.enabled and smtp.sender_email:
        from_email = (
            f'{smtp.sender_name} <{smtp.sender_email}>'
            if smtp.sender_name
            else smtp.sender_email
        )
        reply_to = [smtp.reply_to_email] if smtp.reply_to_email else None
    else:
        from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@khata.app')
        reply_to = None

    html_body = prepare_html_for_email(html_body)

    if smtp.default_signature and smtp.default_signature not in html_body:
        html_body = f'{html_body}<br><br><p style="color:#6b7280;font-size:13px;">{smtp.default_signature}</p>'

    connection = get_mail_connection()
    if connection is None:
        raise ValueError('SMTP is disabled or not configured')

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body or strip_html(html_body),
        from_email=from_email,
        to=[to_email],
        reply_to=reply_to,
        connection=connection,
    )
    msg.attach_alternative(html_body, 'text/html')
    msg.send()

    if log:
        log.status = 'sent'
        log.metadata['sent_at'] = timezone.now().isoformat()
        log.save(update_fields=['status', 'metadata'])


def strip_html(html: str) -> str:
    return re.sub(r'<[^>]+>', '', html).strip()


def queue_or_send(
    to_email,
    subject,
    html_body,
    text_body='',
    *,
    template=None,
    user=None,
    campaign=None,
    metadata=None,
    skip_queue: bool = False,
):
    smtp = SmtpSettings.get_solo()
    log = create_email_log(
        to_email,
        subject,
        template_slug=template.slug if template else '',
        category=template.category if template else 'transactional',
        user=user,
        campaign=campaign,
    )
    html_body = inject_tracking_pixel(html_body, log)
    meta = {**(metadata or {}), 'log_id': str(log.tracking_id), 'html_body': html_body}
    log.metadata = meta
    log.save(update_fields=['metadata'])

    if smtp.queue_enabled and not skip_queue:
        EmailQueue.objects.create(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            template=template,
            campaign=campaign,
            recipient_user=user,
            metadata=meta,
        )
        return log

    send_email_now(to_email, subject, html_body, text_body, log=log)
    log.status = 'delivered'
    log.save(update_fields=['status'])
    return log


def render_system_email(slug: str, context: dict) -> tuple[str, str, str]:
    template = get_template(slug)
    if template:
        subject = render_template_string(template.subject, context)
        html_body = render_template_string(template.html_body, context)
        text_body = render_template_string(template.text_body, context) if template.text_body else ''
        return subject, html_body, text_body

    file_map = {
        'invitation': 'mail/emails/invitation.html',
        'welcome': 'mail/emails/welcome.html',
        'verification': 'mail/emails/verification.html',
        'acceptance': 'mail/emails/acceptance.html',
        'billing-plan-activated': 'mail/emails/billing_plan_activated.html',
        'billing-payment-success': 'mail/emails/billing_payment_success.html',
        'billing-payment-failed': 'mail/emails/billing_payment_failed.html',
    }
    path = file_map.get(slug, 'mail/emails/welcome.html')
    subject_defaults = {
        'invitation': 'You\'re invited to join {{ company_name }} on KHATA',
        'welcome': 'Welcome to KHATA, {{ first_name }}!',
        'verification': 'Verify your KHATA email',
        'acceptance': 'You joined {{ company_name }} on KHATA',
        'billing-plan-activated': '{{ organization_name }} is now on the {{ plan_name }} plan',
        'billing-payment-success': 'Payment received for {{ plan_name }} — {{ organization_name }}',
        'billing-payment-failed': 'Payment could not be completed for {{ plan_name }}',
    }
    subject = render_template_string(subject_defaults.get(slug, 'KHATA Notification'), context)
    html_body = render_to_string(path, {**context, 'subject': subject})
    return subject, html_body, strip_html(html_body)


def dispatch_invitation_email(invitation):
    email = invitation.recipient_email
    if not email:
        raise ValueError('Invitation has no recipient email address')

    user = invitation.invited_user
    frontend = get_frontend_url()
    invite_link = f'{frontend}/invite/{invitation.token}'

    if user:
        first_name = (user.first_name or '').strip() or email.split('@')[0]
    else:
        first_name = email.split('@')[0]

    ctx = build_message_context(user, {
        'first_name': first_name,
        'email': email,
        'company_name': invitation.tenant.name,
        'inviter_name': invitation.invited_by.get_full_name() if invitation.invited_by else 'A team member',
        'role': invitation.get_role_display(),
        'custom_message': invitation.message,
        'expires_at': invitation.expires_at.strftime('%B %d, %Y'),
        'invitation_link': invite_link,
    })
    subject, html, text = render_system_email('invitation', ctx)
    log = queue_or_send(
        email,
        subject,
        html,
        text,
        template=get_template('invitation'),
        user=user,
        metadata={'invitation_id': invitation.pk},
        skip_queue=True,
    )
    if log:
        log.invitation_id = invitation.pk
        log.save(update_fields=['invitation_id'])
    logger.info('Invitation email sent to %s for invitation %s', email, invitation.pk)
    return log


def dispatch_welcome_email(user):
    branding = EmailBranding.get_solo()
    if not branding.marketing_emails_enabled:
        return None
    ctx = build_message_context(user)
    subject, html, text = render_system_email('welcome', ctx)
    return queue_or_send(user.email, subject, html, text, template=get_template('welcome'), user=user, skip_queue=True)


def dispatch_verification_email(user, verification_link: str):
    ctx = build_message_context(user, {'verification_link': verification_link})
    subject, html, text = render_system_email('verification', ctx)
    return queue_or_send(user.email, subject, html, text, template=get_template('verification'), user=user, skip_queue=True)


def dispatch_acceptance_email(invitation):
    user = invitation.invited_user
    ctx = build_message_context(user, {
        'company_name': invitation.tenant.name,
        'role': invitation.get_role_display(),
    })
    subject, html, text = render_system_email('acceptance', ctx)
    return queue_or_send(user.email, subject, html, text, template=get_template('acceptance'), user=user, skip_queue=True)


def _billing_settings_url() -> str:
    return f'{get_frontend_url()}/settings/billing'


def dispatch_billing_plan_activated_email(
    user,
    *,
    organization_name: str,
    plan_name: str,
    amount_display: str,
    period_end: str = '',
):
    ctx = build_message_context(user, {
        'organization_name': organization_name,
        'plan_name': plan_name,
        'amount_display': amount_display,
        'period_end': period_end,
        'billing_url': _billing_settings_url(),
    })
    subject, html, text = render_system_email('billing-plan-activated', ctx)
    return queue_or_send(
        user.email, subject, html, text,
        template=get_template('billing-plan-activated'),
        user=user,
        metadata={'billing_event': 'plan_activated', 'plan_name': plan_name},
        skip_queue=True,
    )


def dispatch_billing_payment_success_email(
    user,
    *,
    organization_name: str,
    plan_name: str,
    amount_display: str,
    transaction_uuid: str,
    payment_method: str = 'eSewa',
    period_end: str = '',
):
    ctx = build_message_context(user, {
        'organization_name': organization_name,
        'plan_name': plan_name,
        'amount_display': amount_display,
        'transaction_uuid': transaction_uuid,
        'payment_method': payment_method,
        'period_end': period_end,
        'billing_url': _billing_settings_url(),
    })
    subject, html, text = render_system_email('billing-payment-success', ctx)
    return queue_or_send(
        user.email, subject, html, text,
        template=get_template('billing-payment-success'),
        user=user,
        metadata={'billing_event': 'payment_success', 'transaction_uuid': transaction_uuid},
        skip_queue=True,
    )


def dispatch_billing_payment_failed_email(
    user,
    *,
    organization_name: str,
    plan_name: str,
    amount_display: str,
    transaction_uuid: str,
    failure_reason: str = '',
):
    ctx = build_message_context(user, {
        'organization_name': organization_name,
        'plan_name': plan_name,
        'amount_display': amount_display,
        'transaction_uuid': transaction_uuid,
        'failure_reason': failure_reason,
        'billing_url': _billing_settings_url(),
    })
    subject, html, text = render_system_email('billing-payment-failed', ctx)
    return queue_or_send(
        user.email, subject, html, text,
        template=get_template('billing-payment-failed'),
        user=user,
        metadata={'billing_event': 'payment_failed', 'transaction_uuid': transaction_uuid},
        skip_queue=True,
    )


def test_smtp_connection() -> tuple[bool, str]:
    try:
        connection = get_smtp_connection()
        if not connection:
            return False, 'SMTP is disabled or host is not configured'
        connection.open()
        connection.close()
        return True, 'SMTP connection successful'
    except Exception as exc:
        return False, str(exc)


def send_test_email(to_email: str) -> tuple[bool, str]:
    try:
        ctx = get_branding_context()
        ctx['first_name'] = 'Admin'
        subject, html, text = render_system_email('welcome', ctx)
        subject = f'[KHATA Test] {subject}'
        send_email_now(to_email, subject, html, text)
        return True, f'Test email sent to {to_email}'
    except Exception as exc:
        return False, str(exc)


def send_all_test_emails(to_email: str) -> tuple[list[str], list[str]]:
    """Send every active email template with sample preview data."""
    ctx = build_preview_context()
    sent, failed = [], []

    for template in EmailTemplate.objects.filter(is_active=True).order_by('category', 'slug'):
        try:
            subject = render_template_string(template.subject, ctx)
            html_body = render_template_string(template.html_body, ctx)
            text_body = render_template_string(template.text_body, ctx) if template.text_body else ''
            subject = f'[KHATA Test: {template.slug}] {subject}'
            send_email_now(to_email, subject, html_body, text_body)
            sent.append(template.slug)
        except Exception as exc:
            failed.append(f'{template.slug}: {exc}')

    return sent, failed


def process_email_queue(limit: int = 50) -> dict:
    smtp = SmtpSettings.get_solo()
    if not smtp.enabled:
        return {'processed': 0, 'message': 'SMTP disabled'}

    rate_limit = max(smtp.rate_limit_per_minute, 1)
    queued = EmailQueue.objects.filter(
        status='queued',
        scheduled_for__lte=timezone.now(),
    ).order_by('priority', 'scheduled_for')[:min(limit, rate_limit)]

    sent, failed = 0, 0
    for item in queued:
        item.status = 'sending'
        item.save(update_fields=['status'])
        log = None
        tracking_id = item.metadata.get('log_id')
        if tracking_id:
            log = EmailLog.objects.filter(tracking_id=tracking_id).first()

        try:
            send_email_now(item.to_email, item.subject, item.html_body, item.text_body, log=log)
            item.status = 'sent'
            item.sent_at = timezone.now()
            item.save()
            if log:
                log.status = 'delivered'
                log.save(update_fields=['status'])
            sent += 1
        except Exception as exc:
            item.retry_count += 1
            item.last_error = str(exc)
            if smtp.retry_failed and item.retry_count < item.max_retries:
                item.status = 'queued'
                item.scheduled_for = timezone.now() + timedelta(minutes=2 ** item.retry_count)
            else:
                item.status = 'failed'
                if log:
                    log.status = 'failed'
                    log.error_message = str(exc)
                    log.save(update_fields=['status', 'error_message'])
            item.save()
            failed += 1

    process_scheduled_campaigns()
    return {'processed': sent + failed, 'sent': sent, 'failed': failed}


def resolve_campaign_recipients(campaign: MarketingCampaign):
    from django.contrib.auth import get_user_model
    from tenants.membership_models import UserTenantMembership

    User = get_user_model()
    if campaign.segment == 'custom':
        emails = [e.strip() for e in campaign.custom_recipients.split(',') if e.strip()]
        return list(User.objects.filter(email__in=emails))

    if campaign.segment == 'tenant_admins':
        admin_ids = UserTenantMembership.objects.filter(role='admin').values_list('user_id', flat=True)
        return list(User.objects.filter(id__in=admin_ids, is_active=True))

    if campaign.segment == 'tenant_managers':
        ids = UserTenantMembership.objects.filter(role='manager').values_list('user_id', flat=True)
        return list(User.objects.filter(id__in=ids, is_active=True))

    return list(User.objects.filter(is_active=True))


def process_scheduled_campaigns():
    due = MarketingCampaign.objects.filter(
        status='scheduled',
        scheduled_at__lte=timezone.now(),
    )
    launched = 0
    for campaign in due:
        try:
            launch_campaign(campaign)
            launched += 1
        except Exception as exc:
            campaign.stats = {**(campaign.stats or {}), 'error': str(exc)}
            campaign.status = 'draft'
            campaign.save(update_fields=['status', 'stats', 'updated_at'])
    return launched


def campaign_analytics(campaign: MarketingCampaign) -> dict:
    from django.db.models import Count

    logs = EmailLog.objects.filter(campaign=campaign)
    by_status = {row['status']: row['count'] for row in logs.values('status').annotate(count=Count('id'))}
    return {
        'campaign': campaign.name,
        'status': campaign.status,
        'recipients': campaign.stats.get('recipients', 0),
        'delivered': by_status.get('delivered', 0) + by_status.get('sent', 0),
        'opened': by_status.get('opened', 0),
        'clicked': by_status.get('clicked', 0),
        'failed': by_status.get('failed', 0),
        'bounced': by_status.get('bounced', 0),
        'unsubscribed': by_status.get('unsubscribed', 0),
        'spam': by_status.get('spam', 0),
        'by_status': by_status,
    }


def launch_campaign(campaign: MarketingCampaign):
    branding = EmailBranding.get_solo()
    if not branding.marketing_emails_enabled:
        raise ValueError('Marketing emails are disabled globally')

    campaign.status = 'sending'
    campaign.save(update_fields=['status', 'updated_at'])

    recipients = resolve_campaign_recipients(campaign)
    sent = 0
    for user in recipients:
        ctx = build_message_context(user)
        subject = campaign.subject_override or render_template_string(campaign.template.subject, ctx)
        html = render_template_string(campaign.template.html_body, ctx)
        text = render_template_string(campaign.template.text_body, ctx) if campaign.template.text_body else ''
        queue_or_send(user.email, subject, html, text, template=campaign.template, user=user, campaign=campaign)
        sent += 1

    campaign.status = 'sent'
    campaign.sent_at = timezone.now()
    campaign.stats = {'recipients': sent, 'sent': sent}
    campaign.save(update_fields=['status', 'sent_at', 'stats', 'updated_at'])
    return sent


def mail_dashboard_stats() -> dict:
    from django.db.models import Count

    logs = EmailLog.objects.all()
    queue = EmailQueue.objects.filter(status='queued').count()
    stats = logs.values('status').annotate(count=Count('id'))
    by_status = {row['status']: row['count'] for row in stats}
    return {
        'total_sent': by_status.get('sent', 0) + by_status.get('delivered', 0),
        'failed': by_status.get('failed', 0) + by_status.get('bounced', 0),
        'opened': by_status.get('opened', 0),
        'clicked': by_status.get('clicked', 0),
        'queued': queue,
        'by_status': by_status,
        'recent': list(
            EmailLog.objects.order_by('-created_at')[:20].values(
                'to_email', 'subject', 'status', 'created_at', 'template_slug'
            )
        ),
    }
