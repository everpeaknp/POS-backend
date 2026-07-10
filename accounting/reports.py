"""Enterprise accounting reports — aging, registers, distributions."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from datetime import date

from accounting.constants import POSTED_GL_STATUSES
from accounting.models import Account, BankTransaction, JournalEntry, JournalLine
from accounting.utils import get_vat_payable_account
from purchase.models import PurchaseInvoice
from sales.models import Invoice


def _aging_buckets(invoices, *, party_field: str, party_name_field: str) -> list[dict]:
    today = timezone.now().date()
    buckets = {'current': Decimal('0'), 'days_30_60': Decimal('0'), 'days_60_90': Decimal('0'), 'days_90_plus': Decimal('0')}
    rows = []

    for inv in invoices:
        balance = inv.amount - inv.paid_amount
        if balance <= 0:
            continue
        days_overdue = (today - inv.due_date).days
        if days_overdue <= 30:
            buckets['current'] += balance
            bucket = 'current'
        elif days_overdue <= 60:
            buckets['days_30_60'] += balance
            bucket = 'days_30_60'
        elif days_overdue <= 90:
            buckets['days_60_90'] += balance
            bucket = 'days_60_90'
        else:
            buckets['days_90_plus'] += balance
            bucket = 'days_90_plus'

        party = getattr(inv, party_field)
        rows.append({
            'invoice_id': inv.id,
            'invoice_number': inv.invoice_number,
            'party_id': party.id,
            'party_name': getattr(party, party_name_field),
            'date': inv.date.isoformat(),
            'due_date': inv.due_date.isoformat(),
            'amount': float(inv.amount),
            'balance': float(balance),
            'days_overdue': max(0, days_overdue),
            'bucket': bucket,
        })

    return rows, {k: float(v) for k, v in buckets.items()}


def build_receivable_aging(tenant) -> dict:
    invoices = Invoice.objects.filter(
        tenant=tenant,
        status__in=['Sent', 'Partially Paid', 'Overdue'],
    ).select_related('customer').order_by('due_date')

    rows, buckets = _aging_buckets(invoices, party_field='customer', party_name_field='name')
    total = sum(r['balance'] for r in rows)

    by_customer: dict[int, dict] = {}
    for row in rows:
        cid = row['party_id']
        if cid not in by_customer:
            by_customer[cid] = {
                'customer_id': cid,
                'customer_name': row['party_name'],
                'total': 0.0,
                'invoices': [],
            }
        by_customer[cid]['total'] += row['balance']
        by_customer[cid]['invoices'].append(row)

    return {
        'as_of_date': timezone.now().date().isoformat(),
        'total_outstanding': total,
        **buckets,
        'customers': sorted(by_customer.values(), key=lambda x: -x['total']),
        'invoices': rows,
    }


def build_payable_aging(tenant) -> dict:
    invoices = PurchaseInvoice.objects.filter(
        tenant=tenant,
        status__in=['Received', 'Partially Paid', 'Overdue'],
    ).select_related('supplier').order_by('due_date')

    rows, buckets = _aging_buckets(invoices, party_field='supplier', party_name_field='name')
    total = sum(r['balance'] for r in rows)

    by_supplier: dict[int, dict] = {}
    for row in rows:
        sid = row['party_id']
        if sid not in by_supplier:
            by_supplier[sid] = {
                'supplier_id': sid,
                'supplier_name': row['party_name'],
                'total': 0.0,
                'invoices': [],
            }
        by_supplier[sid]['total'] += row['balance']
        by_supplier[sid]['invoices'].append(row)

    return {
        'as_of_date': timezone.now().date().isoformat(),
        'total_outstanding': total,
        **buckets,
        'suppliers': sorted(by_supplier.values(), key=lambda x: -x['total']),
        'invoices': rows,
    }


def build_journal_register(tenant, from_date: date, to_date: date) -> dict:
    entries = (
        JournalEntry.objects.filter(
            tenant=tenant,
            date__gte=from_date,
            date__lte=to_date,
            status__in=POSTED_GL_STATUSES,
        )
        .prefetch_related('lines__account')
        .order_by('date', 'entry_number')
    )

    rows = []
    for entry in entries:
        for line in entry.lines.all():
            rows.append({
                'entry_id': entry.id,
                'entry_number': entry.entry_number,
                'date': entry.date.isoformat(),
                'type': entry.type,
                'reference': entry.reference or '',
                'description': line.description or entry.description,
                'account_code': line.account.code,
                'account_name': line.account.name,
                'debit': float(line.debit),
                'credit': float(line.credit),
                'status': entry.status,
            })

    return {
        'from_date': from_date.isoformat(),
        'to_date': to_date.isoformat(),
        'entry_count': entries.count(),
        'lines': rows,
    }


def build_vat_sales_register(tenant, from_date: date, to_date: date) -> dict:
    vat_account = get_vat_payable_account(tenant)
    lines = JournalLine.objects.filter(
        tenant=tenant,
        account=vat_account,
        credit__gt=0,
        journal_entry__status__in=POSTED_GL_STATUSES,
        journal_entry__type='Sales',
        journal_entry__date__gte=from_date,
        journal_entry__date__lte=to_date,
    ).select_related('journal_entry').order_by('journal_entry__date')

    rows = []
    total_vat = Decimal('0')
    for line in lines:
        total_vat += line.credit
        je = line.journal_entry
        rows.append({
            'date': je.date.isoformat(),
            'reference': je.reference or je.entry_number,
            'entry_number': je.entry_number,
            'description': je.description,
            'taxable_estimate': float(je.total_debit - line.credit),
            'vat_amount': float(line.credit),
        })

    return {
        'from_date': from_date.isoformat(),
        'to_date': to_date.isoformat(),
        'total_vat': float(total_vat),
        'rows': rows,
    }


def build_vat_purchase_register(tenant, from_date: date, to_date: date) -> dict:
    vat_account = get_vat_payable_account(tenant)
    lines = JournalLine.objects.filter(
        tenant=tenant,
        account=vat_account,
        debit__gt=0,
        journal_entry__status__in=POSTED_GL_STATUSES,
        journal_entry__type='Purchase',
        journal_entry__date__gte=from_date,
        journal_entry__date__lte=to_date,
    ).select_related('journal_entry').order_by('journal_entry__date')

    rows = []
    total_vat = Decimal('0')
    for line in lines:
        total_vat += line.debit
        je = line.journal_entry
        rows.append({
            'date': je.date.isoformat(),
            'reference': je.reference or je.entry_number,
            'entry_number': je.entry_number,
            'description': je.description,
            'taxable_estimate': float(je.total_credit - line.debit),
            'vat_amount': float(line.debit),
        })

    return {
        'from_date': from_date.isoformat(),
        'to_date': to_date.isoformat(),
        'total_vat': float(total_vat),
        'rows': rows,
    }


def build_account_distribution(tenant, account_type: str) -> list[dict]:
    accounts = Account.objects.filter(tenant=tenant, status='active', type=account_type).exclude(balance=0)
    grouped: dict[str, Decimal] = {}
    for account in accounts:
        key = account.sub_type or 'Other'
        grouped[key] = grouped.get(key, Decimal('0')) + abs(account.balance)

    return [{'name': k, 'value': float(v)} for k, v in sorted(grouped.items(), key=lambda x: -x[1])]


def build_income_expense_breakdown(tenant, from_date: date, to_date: date) -> dict:
    income = []
    expenses = []

    for account in Account.objects.filter(tenant=tenant, status='active', type='Income'):
        amount = _account_period_balance(account, tenant, from_date, to_date, is_income=True)
        if amount:
            income.append({'code': account.code, 'name': account.name, 'amount': float(amount)})

    for account in Account.objects.filter(tenant=tenant, status='active', type='Expense'):
        amount = _account_period_balance(account, tenant, from_date, to_date, is_income=False)
        if amount:
            expenses.append({'code': account.code, 'name': account.name, 'amount': float(amount)})

    return {
        'income': sorted(income, key=lambda x: -x['amount']),
        'expenses': sorted(expenses, key=lambda x: -x['amount']),
    }


def _account_period_balance(account, tenant, from_date, to_date, *, is_income: bool) -> Decimal:
    lines = JournalLine.objects.filter(
        tenant=tenant,
        account=account,
        journal_entry__status__in=POSTED_GL_STATUSES,
        journal_entry__date__gte=from_date,
        journal_entry__date__lte=to_date,
    )
    agg = lines.aggregate(d=Sum('debit'), c=Sum('credit'))
    debit_sum = agg['d'] or Decimal('0')
    credit_sum = agg['c'] or Decimal('0')
    if is_income:
        return credit_sum - debit_sum
    return debit_sum - credit_sum


def build_simple_cash_flow(tenant, from_date: date, to_date: date) -> dict:
    """Operating cash flow proxy from receipt/payment journal types."""
    receipts = JournalEntry.objects.filter(
        tenant=tenant,
        type='Receipt',
        status__in=POSTED_GL_STATUSES,
        date__gte=from_date,
        date__lte=to_date,
    ).aggregate(t=Coalesce(Sum('total_debit'), Value(Decimal('0'))))['t']

    payments = JournalEntry.objects.filter(
        tenant=tenant,
        type='Payment',
        status__in=POSTED_GL_STATUSES,
        date__gte=from_date,
        date__lte=to_date,
    ).aggregate(t=Coalesce(Sum('total_credit'), Value(Decimal('0'))))['t']

    return {
        'from_date': from_date.isoformat(),
        'to_date': to_date.isoformat(),
        'cash_inflows': float(receipts),
        'cash_outflows': float(payments),
        'net_cash_flow': float(receipts - payments),
    }
