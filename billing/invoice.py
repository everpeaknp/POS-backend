"""Subscription payment invoice HTML for customer download."""

from django.template.loader import render_to_string
from django.utils import timezone

from billing.models import BillingPayment
from billing.plans import get_plan
from billing.services import _add_one_month, _user_can_manage_billing
from setting.models import SiteSettings


def payment_period_end(payment: BillingPayment):
    if payment.status != 'completed' or not payment.completed_at:
        return None
    return _add_one_month(payment.completed_at.date())


def user_can_view_payment(user, payment: BillingPayment) -> bool:
    if not user or not user.is_authenticated:
        return False
    if payment.initiated_by_id == user.id:
        return True
    if payment.tenant_id and payment.tenant.created_by_id == user.id:
        return True
    if payment.tenant_id and _user_can_manage_billing(user, payment.tenant):
        return True
    return False


def build_invoice_context(payment: BillingPayment, user) -> dict:
    plan = get_plan(payment.plan_code)
    site = SiteSettings.get_solo()
    paid_at = payment.completed_at or payment.created_at
    period_start = paid_at.date() if paid_at else None
    period_end = payment_period_end(payment)
    account_name = user.get_full_name() or user.username

    return {
        'site_name': site.site_name or 'KHATA',
        'invoice_number': f'SUB-{payment.transaction_uuid[:12].upper()}',
        'transaction_uuid': payment.transaction_uuid,
        'account_name': account_name,
        'plan_name': plan['name'],
        'plan_code': payment.plan_code,
        'amount': payment.amount,
        'amount_display': f'NPR {payment.amount:,.2f}',
        'payment_method': payment.payment_method,
        'esewa_reference': payment.esewa_transaction_code or payment.esewa_reference_id or '',
        'status': payment.status,
        'paid_at': paid_at,
        'period_start': period_start,
        'period_end': period_end,
        'billed_to_name': account_name,
        'billed_to_email': user.email,
        'generated_at': timezone.now(),
    }


def render_invoice_html(payment: BillingPayment, user) -> str:
    context = build_invoice_context(payment, user)
    return render_to_string('billing/subscription_invoice.html', context)
