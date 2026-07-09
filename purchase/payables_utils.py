"""Shared payables helpers for the purchase module."""

from django.db.models import F
from django.utils import timezone


def mark_overdue_purchase_invoices(queryset):
    """Mark received/partial invoices past due_date as Overdue."""
    today = timezone.now().date()
    overdue = queryset.filter(
        status__in=['Received', 'Partially Paid'],
        due_date__lt=today,
    ).exclude(paid_amount__gte=F('amount'))
    overdue.update(status='Overdue')
    return overdue
