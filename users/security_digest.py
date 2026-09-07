"""Weekly security digest: summarizes each opted-in user's recent security-relevant activity."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import AuditLog
from .notification_utils import create_user_notification

logger = logging.getLogger(__name__)

DIGEST_DAYS = 7
SECURITY_ACTIONS = ('login', 'logout')
SECURITY_MODULES = ('settings', 'security')


def _digest_queryset(user, tenant, since):
    return (
        AuditLog.objects.filter(user=user, tenant=tenant, created_at__gte=since)
        .filter(Q(action__in=SECURITY_ACTIONS) | Q(module__in=SECURITY_MODULES))
        .order_by('-created_at')
    )


def build_digest_message(entries) -> str:
    lines = []
    for entry in entries[:15]:
        when = entry.created_at.strftime('%b %d, %I:%M %p')
        location = f' from {entry.ip_address}' if entry.ip_address else ''
        lines.append(f'- {when}: {entry.description}{location}')
    if len(entries) > 15:
        lines.append(f'…and {len(entries) - 15} more.')
    return '\n'.join(lines)


def send_weekly_security_digest() -> int:
    """Email + in-app notify every user opted into security log exports. Returns count sent."""
    from .notification_models import NotificationPreferences

    since = timezone.now() - timedelta(days=DIGEST_DAYS)
    sent = 0

    for prefs in NotificationPreferences.objects.filter(security_log_exports=True).select_related('user'):
        user = prefs.user
        if not user.is_active:
            continue
        tenant = user.get_tenant()
        if not tenant:
            continue

        entries = list(_digest_queryset(user, tenant, since))
        if not entries:
            continue

        message = build_digest_message(entries)
        title = f'Your weekly security summary ({len(entries)} event{"s" if len(entries) != 1 else ""})'

        create_user_notification(
            user=user,
            tenant=tenant,
            title=title,
            message=message,
            notification_type='system_message',
            level='info',
            reference_type='security_digest',
            action_url='/settings/security',
            data={'event_count': len(entries), 'period_days': DIGEST_DAYS},
        )

        if user.email:
            try:
                from mail.services import dispatch_business_alert_email

                dispatch_business_alert_email(
                    user,
                    subject=title,
                    message=message,
                    action_url='/settings/security',
                )
            except Exception:
                logger.exception('Failed to send weekly security digest email to user %s', user.id)

        sent += 1

    return sent
