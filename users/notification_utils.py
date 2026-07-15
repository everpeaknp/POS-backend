"""Helpers for user notifications and preference checks."""

from __future__ import annotations

from typing import Optional

from .notification_models import Notification, NotificationPreferences


def get_or_create_notification_preferences(user) -> NotificationPreferences:
    prefs, _ = NotificationPreferences.objects.get_or_create(user=user)
    return prefs


def preferences_payload(prefs: NotificationPreferences) -> dict:
    return {
        'email_order_updates': prefs.email_order_updates,
        'email_payment_reminders': prefs.email_payment_reminders,
        'email_inventory_alerts': prefs.email_inventory_alerts,
        'email_team_activity': prefs.email_team_activity,
        'push_desktop': prefs.push_desktop,
        'push_mobile': prefs.push_mobile,
        'push_sound': prefs.push_sound,
        'login_alerts': prefs.login_alerts,
        'security_log_exports': prefs.security_log_exports,
    }


def create_user_notification(
    *,
    user,
    tenant,
    title: str,
    message: str,
    notification_type: str = 'system_message',
    level: str = 'info',
    reference_type: str = '',
    reference_id: Optional[int] = None,
    action_url: str = '',
    data: Optional[dict] = None,
) -> Notification:
    return Notification.objects.create(
        tenant=tenant,
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        level=level,
        reference_type=reference_type or '',
        reference_id=reference_id,
        action_url=action_url or '',
        data=data or {},
    )


def notify_login_if_enabled(user, session) -> None:
    """Create an in-app login alert when the user opts in."""
    tenant = user.get_tenant()
    if not tenant:
        return

    prefs = get_or_create_notification_preferences(user)
    if not prefs.login_alerts:
        return

    create_user_notification(
        user=user,
        tenant=tenant,
        title='New sign-in detected',
        message=f'Signed in from {session.device} ({session.location}, {session.ip_address})',
        notification_type='system_message',
        level='warning',
        reference_type='user_session',
        reference_id=None,
        action_url='/settings/security',
        data={
            'session_id': str(session.id),
            'device': session.device,
            'location': session.location,
            'ip_address': session.ip_address,
        },
    )
