"""Shared credit / AR helpers for the sales module."""

from decimal import Decimal

from django.db.models import F
from django.utils import timezone


def check_credit_available(customer, additional_amount: Decimal) -> None:
    """Raise ValueError if customer cannot take additional credit."""
    if customer.credit_limit <= 0:
        raise ValueError(
            'Credit limit is not set for this customer. Set a credit limit before credit sales.'
        )
    if customer.current_balance + additional_amount > customer.credit_limit:
        raise ValueError(
            f'Credit limit exceeded. Available credit: Rs. {customer.available_credit:,.2f}'
        )


def order_already_on_ledger(sales_order) -> bool:
    """True when a credit order was already finalized to the customer ledger."""
    if not sales_order:
        return False
    from .models import CustomerLedger

    return CustomerLedger.objects.filter(
        tenant=sales_order.tenant,
        customer=sales_order.customer_id,
        reference_type='SalesOrder',
        reference_id=sales_order.id,
    ).exists()


def ensure_credit_order_on_ledger(sales_order) -> None:
    """Post credit order to customer ledger if not already recorded."""
    if sales_order.payment_type != 'credit' or order_already_on_ledger(sales_order):
        return
    from django.db import transaction
    from .models import Customer, CustomerLedger

    check_credit_available(sales_order.customer, sales_order.total)
    with transaction.atomic():
        customer = Customer.objects.select_for_update().get(pk=sales_order.customer_id)
        new_balance = customer.current_balance + sales_order.total
        CustomerLedger.objects.create(
            tenant=sales_order.tenant,
            customer=customer,
            date=sales_order.date,
            transaction_type='sale',
            reference_type='SalesOrder',
            reference_number=sales_order.order_number,
            reference_id=sales_order.id,
            debit_amount=sales_order.total,
            credit_amount=Decimal('0.00'),
            running_balance=new_balance,
            description=f"Credit sale - Order {sales_order.order_number}",
        )
        customer.current_balance = new_balance
        customer.save(update_fields=['current_balance', 'updated_at'])


def mark_overdue_invoices(queryset):
    """Mark sent/partial invoices past due_date as Overdue."""
    today = timezone.now().date()
    overdue = queryset.filter(
        status__in=['Sent', 'Partially Paid'],
        due_date__lt=today,
    ).exclude(paid_amount__gte=F('amount'))
    overdue.update(status='Overdue')
    return overdue
