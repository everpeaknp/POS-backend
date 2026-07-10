"""Central helpers for tenant business notifications (in-app + email)."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Iterable, Optional

from django.utils import timezone

from .notification_models import Notification, NotificationPreferences
from .notification_utils import create_user_notification, get_or_create_notification_preferences

logger = logging.getLogger(__name__)

PREF_INVENTORY = 'email_inventory_alerts'
PREF_PAYMENT = 'email_payment_reminders'
PREF_ORDERS = 'email_order_updates'
PREF_TEAM = 'email_team_activity'


def iter_tenant_users(tenant):
    """Active users assigned to a tenant via membership or primary tenant."""
    from tenants.membership_models import UserTenantMembership
    from users.models import User

    inactive_member_ids = set(
        UserTenantMembership.objects.filter(tenant=tenant, is_active=False).values_list(
            'user_id', flat=True
        )
    )
    member_ids = set(
        UserTenantMembership.objects.filter(tenant=tenant, is_active=True).values_list(
            'user_id', flat=True
        )
    )
    primary_ids = set(
        User.objects.filter(tenant=tenant)
        .exclude(id__in=inactive_member_ids)
        .values_list('id', flat=True)
    )
    user_ids = member_ids | primary_ids
    return User.objects.filter(id__in=user_ids, is_active=True).distinct()


def iter_tenant_approvers(tenant):
    return [user for user in iter_tenant_users(tenant) if user.can_approve_purchases()]


def iter_tenant_finance_users(tenant):
    return [user for user in iter_tenant_users(tenant) if user.can_view_financials()]


def user_pref_enabled(user, pref_key: str) -> bool:
    prefs = get_or_create_notification_preferences(user)
    return bool(getattr(prefs, pref_key, True))


def has_recent_notification(
    *,
    user,
    tenant,
    reference_type: str,
    reference_id: Optional[int],
    notification_type: str,
    within_hours: int = 24,
) -> bool:
    cutoff = timezone.now() - timedelta(hours=within_hours)
    qs = Notification.objects.filter(
        user=user,
        tenant=tenant,
        reference_type=reference_type,
        notification_type=notification_type,
        created_at__gte=cutoff,
    )
    if reference_id is not None:
        qs = qs.filter(reference_id=reference_id)
    return qs.exists()


def _send_alert_email(user, *, subject: str, message: str, action_url: str = '') -> None:
    if not user.email:
        return
    try:
        from mail.services import dispatch_business_alert_email

        dispatch_business_alert_email(
            user,
            subject=subject,
            message=message,
            action_url=action_url,
        )
    except Exception:
        logger.exception('Failed to queue business alert email for user %s', user.id)


def notify_user(
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
    email_pref_key: Optional[str] = None,
    dedupe_hours: int = 24,
    skip_dedupe: bool = False,
) -> Optional[Notification]:
    if not skip_dedupe and has_recent_notification(
        user=user,
        tenant=tenant,
        reference_type=reference_type,
        reference_id=reference_id,
        notification_type=notification_type,
        within_hours=dedupe_hours,
    ):
        return None

    notification = create_user_notification(
        user=user,
        tenant=tenant,
        title=title,
        message=message,
        notification_type=notification_type,
        level=level,
        reference_type=reference_type,
        reference_id=reference_id,
        action_url=action_url,
        data=data,
    )

    if email_pref_key and user_pref_enabled(user, email_pref_key):
        _send_alert_email(user, subject=title, message=message, action_url=action_url)

    return notification


def notify_users(
    users: Iterable,
    *,
    tenant,
    title: str,
    message: str,
    notification_type: str = 'system_message',
    level: str = 'info',
    reference_type: str = '',
    reference_id: Optional[int] = None,
    action_url: str = '',
    data: Optional[dict] = None,
    email_pref_key: Optional[str] = None,
    exclude_user=None,
    dedupe_hours: int = 24,
) -> int:
    count = 0
    for user in users:
        if exclude_user and user.id == exclude_user.id:
            continue
        if notify_user(
            user=user,
            tenant=tenant,
            title=title,
            message=message,
            notification_type=notification_type,
            level=level,
            reference_type=reference_type,
            reference_id=reference_id,
            action_url=action_url,
            data=data,
            email_pref_key=email_pref_key,
            dedupe_hours=dedupe_hours,
        ):
            count += 1
    return count
