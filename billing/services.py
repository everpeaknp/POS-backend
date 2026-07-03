"""Billing business logic."""

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from billing.esewa import (
    build_payment_form,
    check_transaction_status,
    decode_callback_data,
    new_transaction_uuid,
    verify_callback_signature,
)
from billing.models import BillingPayment, Subscription
from billing.plans import PLAN_TYPE_TO_CODE, SUBSCRIPTION_PLANS, get_plan
from billing.esewa_config import get_esewa_config


def _add_one_month(start: date) -> date:
    year = start.year + (1 if start.month == 12 else 0)
    month = 1 if start.month == 12 else start.month + 1
    day = min(start.day, monthrange(year, month)[1])
    return date(year, month, day)


def ensure_subscription(tenant) -> Subscription:
    plan_code = PLAN_TYPE_TO_CODE.get(tenant.plan_type, 'starter')
    subscription, created = Subscription.objects.get_or_create(
        tenant=tenant,
        defaults={
            'plan_code': plan_code,
            'status': 'trialing' if tenant.plan_type == 'free' else 'active',
            'current_period_start': timezone.now().date(),
            'current_period_end': _add_one_month(timezone.now().date()),
        },
    )
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
        'features': plan['features'],
        'is_current': plan_code == current_plan_code,
    }


def billing_overview(tenant, user) -> dict:
    subscription = ensure_subscription(tenant)
    current_plan_code = subscription.plan_code

    payments = BillingPayment.objects.filter(tenant=tenant).order_by('-created_at')[:10]
    return {
        'subscription': {
            'plan_code': subscription.plan_code,
            'plan_name': get_plan(subscription.plan_code)['name'],
            'status': subscription.status,
            'is_active': subscription.is_active,
            'current_period_start': subscription.current_period_start,
            'current_period_end': subscription.current_period_end,
            'auto_renew': subscription.auto_renew,
            'monthly_price': float(get_plan(subscription.plan_code)['price']),
        },
        'plans': [
            serialize_plan(code, current_plan_code)
            for code in SUBSCRIPTION_PLANS
        ],
        'payments': [
            {
                'id': p.id,
                'transaction_uuid': p.transaction_uuid,
                'plan_code': p.plan_code,
                'amount': float(p.amount),
                'status': p.status,
                'payment_method': p.payment_method,
                'completed_at': p.completed_at,
                'created_at': p.created_at,
            }
            for p in payments
        ],
        'esewa_enabled': get_esewa_config().enabled,
        'can_manage_billing': _user_can_manage_billing(user, tenant),
    }


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
    if not _user_can_manage_billing(user, tenant):
        raise PermissionError('Only organization admins can manage billing')

    if not get_esewa_config().enabled:
        raise ValueError('eSewa payments are disabled. Enable them in Platform Admin → Settings → eSewa integration.')

    plan = get_plan(plan_code)
    subscription = ensure_subscription(tenant)

    if subscription.plan_code == plan_code and subscription.is_active:
        raise ValueError('You are already on this plan')

    transaction_uuid = new_transaction_uuid(tenant.id)
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
def verify_and_activate(tenant, user, transaction_uuid: str, encoded_data: str | None = None) -> dict:
    if not _user_can_manage_billing(user, tenant):
        raise PermissionError('Only organization admins can manage billing')

    try:
        payment = BillingPayment.objects.select_for_update().get(
            tenant=tenant,
            transaction_uuid=transaction_uuid,
        )
    except BillingPayment.DoesNotExist:
        raise ValueError('Payment not found')

    if payment.status == 'completed':
        subscription = ensure_subscription(tenant)
        return {
            'status': 'completed',
            'message': 'Payment already processed',
            'subscription': _serialize_subscription(subscription),
        }

    total_amount = f'{payment.amount:.2f}'
    status_payload = None
    callback_payload = {}

    if encoded_data:
        callback_payload = decode_callback_data(encoded_data)
        if not verify_callback_signature(callback_payload, get_esewa_config().secret_key):
            payment.status = 'failed'
            payment.failure_reason = 'Invalid eSewa signature'
            payment.callback_payload = callback_payload
            payment.save()
            raise ValueError('Invalid payment signature')

        if callback_payload.get('transaction_uuid') != transaction_uuid:
            raise ValueError('Transaction UUID mismatch')

        total_amount = callback_payload.get('total_amount', total_amount)
        if callback_payload.get('status') not in ('COMPLETE', 'COMPLETED'):
            payment.status = 'failed'
            payment.failure_reason = f"Payment status: {callback_payload.get('status')}"
            payment.callback_payload = callback_payload
            payment.save()
            raise ValueError('Payment was not completed')

    status_payload = check_transaction_status(transaction_uuid, total_amount)
    if status_payload.get('status') not in ('COMPLETE', 'COMPLETED'):
        payment.status = 'failed'
        payment.failure_reason = f"eSewa status: {status_payload.get('status')}"
        payment.callback_payload = {'callback': callback_payload, 'status_api': status_payload}
        payment.save()
        raise ValueError('Payment verification failed')

    payment.status = 'completed'
    payment.completed_at = timezone.now()
    payment.esewa_transaction_code = status_payload.get('ref_id') or callback_payload.get('transaction_code', '')
    payment.esewa_reference_id = status_payload.get('transaction_code', '')
    payment.callback_payload = {'callback': callback_payload, 'status_api': status_payload}
    payment.save()

    plan = get_plan(payment.plan_code)
    today = timezone.now().date()
    subscription = ensure_subscription(tenant)
    subscription.plan_code = payment.plan_code
    subscription.status = 'active'
    subscription.current_period_start = today
    subscription.current_period_end = _add_one_month(today)
    subscription.save()

    tenant.plan_type = plan['plan_type']
    tenant.active_modules = plan['modules']
    tenant.is_active = True
    tenant.save(update_fields=['plan_type', 'active_modules', 'is_active', 'updated_at'])

    return {
        'status': 'completed',
        'message': f'Successfully subscribed to {plan["name"]}',
        'subscription': _serialize_subscription(subscription),
        'payment': {
            'transaction_uuid': payment.transaction_uuid,
            'amount': float(payment.amount),
            'plan_code': payment.plan_code,
        },
    }


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
        tenant = payment.tenant
        today = timezone.now().date()
        subscription = ensure_subscription(tenant)
        subscription.plan_code = payment.plan_code
        subscription.status = 'active'
        subscription.current_period_start = today
        subscription.current_period_end = _add_one_month(today)
        subscription.save()

        tenant.plan_type = plan['plan_type']
        tenant.active_modules = plan['modules']
        tenant.is_active = True
        tenant.save(update_fields=['plan_type', 'active_modules', 'is_active', 'updated_at'])
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
