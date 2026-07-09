"""Billing business logic."""

import logging
import time
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from billing.esewa import (
    build_payment_form,
    check_transaction_status,
    decode_callback_data,
    new_transaction_uuid,
    verify_callback_signature,
)
from billing.models import BillingPayment, Subscription, UserSubscription
from billing.plans import get_plan, get_plan_type_to_code_map, list_active_plans
from billing.account_limits import (
    get_allowed_modules_for_plan,
    get_tenant_allowed_modules,
    get_user_account_plan_code,
    normalize_active_modules_for_plan,
)
from billing.esewa_config import get_esewa_config

logger = logging.getLogger(__name__)


def _format_amount_display(amount) -> str:
    value = Decimal(str(amount))
    if value == 0:
        return 'Free'
    return f'NPR {value:,.2f}'


def _format_period_end(subscription: Subscription) -> str:
    if subscription.current_period_end:
        return subscription.current_period_end.strftime('%B %d, %Y')
    return ''


def _account_label(user, tenant) -> str:
    if tenant:
        return tenant.name
    return user.get_full_name() or user.email or 'Your account'


def _notify_plan_activated(user, tenant, plan: dict, subscription) -> None:
    try:
        from mail.services import dispatch_billing_plan_activated_email

        dispatch_billing_plan_activated_email(
            user,
            organization_name=_account_label(user, tenant),
            plan_name=plan['name'],
            amount_display=_format_amount_display(plan['price']),
            period_end=_format_period_end(subscription),
        )
    except Exception:
        logger.exception('Failed to send plan activated email for user %s', user.pk)


def _notify_payment_success(user, tenant, plan: dict, payment: BillingPayment, subscription) -> None:
    try:
        from mail.services import dispatch_billing_payment_success_email

        dispatch_billing_payment_success_email(
            user,
            organization_name=_account_label(user, tenant),
            plan_name=plan['name'],
            amount_display=_format_amount_display(payment.amount),
            transaction_uuid=payment.transaction_uuid,
            payment_method=payment.payment_method,
            period_end=_format_period_end(subscription),
        )
    except Exception:
        logger.exception('Failed to send payment success email for %s', payment.transaction_uuid)


def _notify_payment_failed(user, tenant, plan: dict, payment: BillingPayment, failure_reason: str = '') -> None:
    try:
        from mail.services import dispatch_billing_payment_failed_email

        dispatch_billing_payment_failed_email(
            user,
            organization_name=_account_label(user, tenant),
            plan_name=plan['name'],
            amount_display=_format_amount_display(payment.amount),
            transaction_uuid=payment.transaction_uuid,
            failure_reason=failure_reason,
        )
    except Exception:
        logger.exception('Failed to send payment failed email for %s', payment.transaction_uuid)


def _mark_payment_failed(
    payment: BillingPayment,
    reason: str,
    callback_payload: dict | None = None,
) -> bool:
    """Mark payment failed; returns True if status changed from pending."""
    was_pending = payment.status == 'pending'
    payment.status = 'failed'
    payment.failure_reason = reason
    update_fields = ['status', 'failure_reason', 'updated_at']
    if callback_payload is not None:
        payment.callback_payload = callback_payload
        update_fields.append('callback_payload')
    payment.save(update_fields=update_fields)
    return was_pending


def _add_one_month(start: date) -> date:
    year = start.year + (1 if start.month == 12 else 0)
    month = 1 if start.month == 12 else start.month + 1
    day = min(start.day, monthrange(year, month)[1])
    return date(year, month, day)


def ensure_subscription(tenant) -> Subscription:
    plan_code = get_plan_type_to_code_map().get(tenant.plan_type, 'free')
    today = timezone.now().date()
    defaults = {
        'plan_code': plan_code,
        'status': 'trialing' if plan_code == 'free' else 'active',
        'current_period_start': today,
        'current_period_end': None if plan_code == 'free' else _add_one_month(today),
    }
    manager = Subscription._base_manager
    try:
        subscription, created = manager.get_or_create(tenant=tenant, defaults=defaults)
    except IntegrityError:
        subscription = manager.get(tenant=tenant)
        created = False
    if not created and subscription.plan_code != plan_code:
        subscription.plan_code = plan_code
        subscription.save(update_fields=['plan_code', 'updated_at'])
    return subscription


def serialize_plan(plan_code: str, current_plan_code: str | None = None) -> dict:
    plan = get_plan(plan_code)
    return {
        'code': plan['code'],
        'name': plan['name'],
        'price': float(plan['price']),
        'max_users': plan['max_users'],
        'max_orgs': plan.get('max_orgs'),
        'features': plan['features'],
        'is_current': plan_code == current_plan_code,
        'is_popular': bool(plan.get('is_popular')),
    }


def ensure_user_subscription(user) -> UserSubscription:
    today = timezone.now().date()
    defaults = {
        'plan_code': 'free',
        'status': 'trialing',
        'current_period_start': today,
        'current_period_end': None,
    }
    subscription, _ = UserSubscription.objects.get_or_create(user=user, defaults=defaults)
    return subscription


def activate_user_subscription(user, plan_code: str) -> UserSubscription:
    plan = get_plan(plan_code)
    today = timezone.now().date()
    subscription = ensure_user_subscription(user)
    subscription.plan_code = plan_code
    subscription.status = 'trialing' if plan_code == 'free' else 'active'
    subscription.current_period_start = today
    subscription.current_period_end = None if plan_code == 'free' else _add_one_month(today)
    subscription.save()
    return subscription


def apply_account_plan_to_owned_orgs(user, plan_code: str) -> None:
    """Sync paid modules to every organization this account owns."""
    from tenants.models import Tenant

    plan = get_plan(plan_code)
    today = timezone.now().date()
    for tenant in Tenant.objects.filter(created_by=user):
        subscription = ensure_subscription(tenant)
        subscription.plan_code = plan_code
        subscription.status = 'trialing' if plan_code == 'free' else 'active'
        subscription.current_period_start = today
        subscription.current_period_end = None if plan_code == 'free' else _add_one_month(today)
        subscription.save()

        tenant.plan_type = plan['plan_type']
        tenant.active_modules = normalize_active_modules_for_plan(
            plan_code,
            tenant.active_modules or list(plan.get('modules') or []),
        )
        tenant.is_active = True
        tenant.save(update_fields=['plan_type', 'active_modules', 'is_active', 'updated_at'])


def _serialize_user_subscription(subscription: UserSubscription) -> dict:
    plan = get_plan(subscription.plan_code)
    return {
        'plan_code': subscription.plan_code,
        'plan_name': plan['name'],
        'status': subscription.status,
        'is_active': subscription.is_active,
        'current_period_start': subscription.current_period_start,
        'current_period_end': subscription.current_period_end,
        'auto_renew': subscription.auto_renew,
        'monthly_price': float(plan['price']),
    }


def payment_period_end(payment: BillingPayment):
    if payment.status != 'completed' or not payment.completed_at:
        return None
    return _add_one_month(payment.completed_at.date())


def _serialize_payment_record(payment: BillingPayment) -> dict:
    period_end = payment_period_end(payment)
    payer = payment.initiated_by
    return {
        'id': payment.id,
        'transaction_uuid': payment.transaction_uuid,
        'plan_code': payment.plan_code,
        'amount': float(payment.amount),
        'status': payment.status,
        'payment_method': payment.payment_method,
        'completed_at': payment.completed_at,
        'created_at': payment.created_at,
        'period_end': period_end.isoformat() if period_end else None,
        'invoice_available': payment.status == 'completed',
        'account_name': payer.get_full_name() if payer else '',
        'account_email': payer.email if payer else '',
    }


def billing_overview(tenant, user) -> dict:
    user_subscription = ensure_user_subscription(user)
    current_plan_code = user_subscription.plan_code
    account_plan = get_plan(current_plan_code)

    payments = (
        BillingPayment.objects.filter(initiated_by=user)
        .order_by('-created_at')[:10]
    )

    return {
        'account': {
            'name': user.get_full_name() or user.username,
            'email': user.email,
        },
        'subscription': _serialize_user_subscription(user_subscription),
        'plans': [
            serialize_plan(plan['code'], current_plan_code)
            for plan in list_active_plans()
        ],
        'payments': [_serialize_payment_record(p) for p in payments],
        'esewa_enabled': get_esewa_config().enabled,
        'can_manage_billing': True,
        'can_upgrade_account': True,
        'billing_scope': 'account',
        'member_organization': None,
        'allowed_modules': get_allowed_modules_for_plan(current_plan_code),
    }


def _user_owns_any_organization(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    from tenants.models import Tenant

    return Tenant.objects.filter(created_by=user).exists()


def resolve_checkout_tenant(user, context_tenant=None):
    """Optional workspace to attach to a payment record (account billing is primary)."""
    from tenants.models import Tenant

    return Tenant.objects.filter(created_by=user).order_by('-id').first()


def _user_can_manage_billing(user, tenant) -> bool:
    if not user or not user.is_authenticated:
        return False
    if tenant.created_by_id == user.id:
        return True
    if getattr(user, 'role', None) == 'admin' and user.tenant_id == tenant.id:
        return True
    from tenants.membership_models import UserTenantMembership
    membership = UserTenantMembership.objects.filter(user=user, tenant=tenant).first()
    return bool(membership and membership.role == 'admin')


def initiate_checkout(tenant, user, plan_code: str) -> dict:
    plan = get_plan(plan_code)
    user_subscription = ensure_user_subscription(user)

    if user_subscription.plan_code == plan_code and user_subscription.is_active:
        raise ValueError('You are already on this plan')

    if plan['price'] == 0:
        return activate_plan_without_payment(tenant, user, plan_code)

    if not get_esewa_config().enabled:
        raise ValueError('eSewa payments are disabled. Enable them in Platform Admin → Settings → eSewa integration.')

    transaction_uuid = new_transaction_uuid(user.id)
    amount = Decimal(str(plan['price']))

    BillingPayment.objects.create(
        tenant=tenant,
        transaction_uuid=transaction_uuid,
        plan_code=plan_code,
        amount=amount,
        status='pending',
        initiated_by=user,
    )

    form = build_payment_form(amount, transaction_uuid, plan['name'])
    return form


@transaction.atomic
def activate_plan_without_payment(tenant, user, plan_code: str) -> dict:
    plan = get_plan(plan_code)
    if plan['price'] > 0:
        raise ValueError('This plan requires payment')

    user_subscription = activate_user_subscription(user, plan_code)
    apply_account_plan_to_owned_orgs(user, plan_code)

    billing_tenant = tenant or resolve_checkout_tenant(user)
    if billing_tenant:
        _notify_plan_activated(user, billing_tenant, plan, user_subscription)

    return {
        'activated': True,
        'message': f'Successfully switched to {plan["name"]}',
        'subscription': _serialize_user_subscription(user_subscription),
    }


def _completed_payment_response(user, payment: BillingPayment) -> dict:
    user_subscription = ensure_user_subscription(user)
    plan = get_plan(payment.plan_code)
    return {
        'status': 'completed',
        'message': f'Successfully subscribed to {plan["name"]}',
        'subscription': _serialize_user_subscription(user_subscription),
        'payment': {
            'transaction_uuid': payment.transaction_uuid,
            'amount': float(payment.amount),
            'plan_code': payment.plan_code,
        },
    }


def _already_processed_response(user) -> dict:
    user_subscription = ensure_user_subscription(user)
    return {
        'status': 'completed',
        'message': 'Payment already processed',
        'subscription': _serialize_user_subscription(user_subscription),
    }


@transaction.atomic
def _verify_and_activate_transaction(user, transaction_uuid: str, encoded_data: str | None = None) -> dict:
    try:
        payment = BillingPayment.objects.select_for_update().get(transaction_uuid=transaction_uuid)
    except BillingPayment.DoesNotExist:
        raise ValueError('Payment not found')

    if payment.initiated_by_id and payment.initiated_by_id != user.id:
        raise PermissionError('You can only verify your own payments')

    tenant = payment.tenant
    if payment.status == 'completed':
        return _already_processed_response(user)

    total_amount = f'{payment.amount:.2f}'
    status_payload = None
    callback_payload = {}

    if encoded_data:
        callback_payload = decode_callback_data(encoded_data)
        plan = get_plan(payment.plan_code)
        if not verify_callback_signature(callback_payload, get_esewa_config().secret_key):
            if _mark_payment_failed(payment, 'Invalid eSewa signature', callback_payload):
                _notify_payment_failed(user, tenant, plan, payment, 'Invalid eSewa signature')
            raise ValueError('Invalid payment signature')

        if callback_payload.get('transaction_uuid') != transaction_uuid:
            raise ValueError('Transaction UUID mismatch')

        total_amount = callback_payload.get('total_amount', total_amount)
        if callback_payload.get('status') not in ('COMPLETE', 'COMPLETED'):
            reason = f"Payment status: {callback_payload.get('status')}"
            if _mark_payment_failed(payment, reason, callback_payload):
                _notify_payment_failed(user, tenant, plan, payment, reason)
            raise ValueError('Payment was not completed')

    status_payload = check_transaction_status(transaction_uuid, total_amount)
    if status_payload.get('status') not in ('COMPLETE', 'COMPLETED'):
        plan = get_plan(payment.plan_code)
        payload = {'callback': callback_payload, 'status_api': status_payload}
        reason = f"eSewa status: {status_payload.get('status')}"
        if _mark_payment_failed(payment, reason, payload):
            _notify_payment_failed(user, tenant, plan, payment, reason)
        raise ValueError('Payment verification failed')

    payment.status = 'completed'
    payment.completed_at = timezone.now()
    payment.esewa_transaction_code = status_payload.get('ref_id') or callback_payload.get('transaction_code', '')
    payment.esewa_reference_id = status_payload.get('transaction_code', '')
    payment.callback_payload = {'callback': callback_payload, 'status_api': status_payload}
    payment.save()

    plan = get_plan(payment.plan_code)
    user_subscription = activate_user_subscription(user, payment.plan_code)
    apply_account_plan_to_owned_orgs(user, payment.plan_code)

    _notify_payment_success(user, tenant, plan, payment, user_subscription)

    return _completed_payment_response(user, payment)


def verify_and_activate(tenant, user, transaction_uuid: str, encoded_data: str | None = None) -> dict:
    payment = BillingPayment.objects.filter(transaction_uuid=transaction_uuid).first()
    if not payment:
        raise ValueError('Payment not found')
    if payment.initiated_by_id and payment.initiated_by_id != user.id:
        raise PermissionError('You can only verify your own payments')
    if payment.status == 'completed':
        return _already_processed_response(user)

    max_retries = 4
    for attempt in range(max_retries):
        try:
            return _verify_and_activate_transaction(user, transaction_uuid, encoded_data)
        except OperationalError as exc:
            if 'locked' not in str(exc).lower() or attempt >= max_retries - 1:
                raise
            time.sleep(0.15 * (attempt + 1))
            payment.refresh_from_db()
            if payment.status == 'completed':
                return _already_processed_response(user)


def _serialize_subscription(subscription: Subscription) -> dict:
    plan = get_plan(subscription.plan_code)
    return {
        'plan_code': subscription.plan_code,
        'plan_name': plan['name'],
        'status': subscription.status,
        'is_active': subscription.is_active,
        'current_period_start': subscription.current_period_start,
        'current_period_end': subscription.current_period_end,
        'monthly_price': float(plan['price']),
    }


def admin_reverify_payment(payment: BillingPayment) -> str:
    """Platform admin: re-check eSewa status for a pending/failed payment."""
    if payment.status == 'completed':
        return 'Payment already completed'

    total_amount = f'{payment.amount:.2f}'
    status_payload = check_transaction_status(payment.transaction_uuid, total_amount)
    status = status_payload.get('status', '')

    if status in ('COMPLETE', 'COMPLETED'):
        payment.status = 'completed'
        payment.completed_at = timezone.now()
        payment.esewa_reference_id = status_payload.get('transaction_code', '')
        payment.esewa_transaction_code = status_payload.get('ref_id', '')
        payment.callback_payload = {'status_api': status_payload, 'admin_reverify': True}
        payment.save()

        plan = get_plan(payment.plan_code)
        payer = payment.initiated_by
        if payer:
            activate_user_subscription(payer, payment.plan_code)
            apply_account_plan_to_owned_orgs(payer, payment.plan_code)
        elif payment.tenant_id:
            today = timezone.now().date()
            subscription = ensure_subscription(payment.tenant)
            subscription.plan_code = payment.plan_code
            subscription.status = 'active'
            subscription.current_period_start = today
            subscription.current_period_end = _add_one_month(today)
            subscription.save()

            payment.tenant.plan_type = plan['plan_type']
            payment.tenant.active_modules = normalize_active_modules_for_plan(
                payment.plan_code,
                payment.tenant.active_modules or list(plan.get('modules') or []),
            )
            payment.tenant.is_active = True
            payment.tenant.save(update_fields=['plan_type', 'active_modules', 'is_active', 'updated_at'])
        return f'Payment verified and plan activated ({plan["name"]})'

    payment.failure_reason = f'eSewa status: {status}'
    payment.callback_payload = {'status_api': status_payload, 'admin_reverify': True}
    if payment.status == 'pending':
        payment.status = 'failed'
    payment.save()
    return f'Verification failed — status: {status}'


def admin_extend_subscription(subscription: Subscription, days: int = 30) -> None:
    """Extend subscription period by N days."""
    today = timezone.now().date()
    base = subscription.current_period_end if subscription.current_period_end and subscription.current_period_end >= today else today
    subscription.current_period_end = base + timedelta(days=days)
    subscription.status = 'active'
    subscription.save(update_fields=['current_period_end', 'status', 'updated_at'])
