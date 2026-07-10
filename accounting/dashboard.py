"""Accounting dashboard aggregates for the overview page."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounting.constants import POSTED_GL_STATUSES
from accounting.fiscal_utils import bs_fiscal_label, bs_fiscal_year_ad_range, current_bs_fiscal_start_year
from accounting.reports import build_account_distribution, build_income_expense_breakdown, build_simple_cash_flow
from accounting.models import Account, JournalEntry, JournalLine, BankTransaction
from accounting.utils import calculate_vat_for_period
from purchase.models import PurchaseInvoice
from sales.models import Customer, Invoice


def _month_range(year: int, month: int) -> tuple[date, date]:
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def _sum_account_balances(tenant, *, sub_types=None, account_type=None, codes=None) -> Decimal:
    qs = Account.objects.filter(tenant=tenant, status='active')
    if sub_types:
        qs = qs.filter(sub_type__in=sub_types)
    if account_type:
        qs = qs.filter(type=account_type)
    if codes:
        qs = qs.filter(code__in=codes)
    return qs.aggregate(total=Coalesce(Sum('balance'), Value(Decimal('0.00'))))['total']


def _period_pl(tenant, from_date: date, to_date: date) -> dict:
    income = Decimal('0.00')
    expenses = Decimal('0.00')
    cogs = Decimal('0.00')

    accounts = Account.objects.filter(tenant=tenant, status='active', type__in=['Income', 'Expense'])
    for account in accounts:
        lines = JournalLine.objects.filter(
            tenant=tenant,
            account=account,
            journal_entry__status__in=POSTED_GL_STATUSES,
            journal_entry__date__gte=from_date,
            journal_entry__date__lte=to_date,
        )
        agg = lines.aggregate(d=Sum('debit'), c=Sum('credit'))
        debit_sum = agg['d'] or Decimal('0.00')
        credit_sum = agg['c'] or Decimal('0.00')

        if account.type == 'Income':
            income += credit_sum - debit_sum
        else:
            amount = debit_sum - credit_sum
            expenses += amount
            if account.sub_type == 'COGS':
                cogs += amount

    return {
        'income': float(income),
        'expenses': float(expenses),
        'cogs': float(cogs),
        'gross_profit': float(income - cogs),
        'net_profit': float(income - expenses),
    }


def _monthly_trend(tenant, months: int = 6) -> list[dict]:
    today = timezone.now().date()
    points = []
    cursor = date(today.year, today.month, 1)

    for _ in range(months):
        from_d, to_d = _month_range(cursor.year, cursor.month)
        pl = _period_pl(tenant, from_d, to_d)
        points.append({
            'month': cursor.strftime('%b %Y'),
            'from_date': from_d.isoformat(),
            'to_date': to_d.isoformat(),
            'income': pl['income'],
            'expenses': pl['expenses'],
            'net_profit': pl['net_profit'],
        })
        if cursor.month == 1:
            cursor = date(cursor.year - 1, 12, 1)
        else:
            cursor = date(cursor.year, cursor.month - 1, 1)

    points.reverse()
    return points


def _upcoming_payables(tenant, *, days: int = 7) -> list[dict]:
    today = timezone.now().date()
    cutoff = today + timedelta(days=days)
    items = []

    for inv in Invoice.objects.filter(
        tenant=tenant,
        status__in=['Sent', 'Partially Paid', 'Overdue'],
        due_date__gte=today,
        due_date__lte=cutoff,
    ).select_related('customer')[:10]:
        balance = inv.amount - inv.paid_amount
        if balance > 0:
            items.append({
                'kind': 'receivable',
                'reference': inv.invoice_number,
                'party': inv.customer.name,
                'due_date': inv.due_date.isoformat(),
                'amount': float(balance),
            })

    for inv in PurchaseInvoice.objects.filter(
        tenant=tenant,
        status__in=['Received', 'Partially Paid', 'Overdue'],
        due_date__gte=today,
        due_date__lte=cutoff,
    ).select_related('supplier')[:10]:
        balance = inv.amount - inv.paid_amount
        if balance > 0:
            items.append({
                'kind': 'payable',
                'reference': inv.invoice_number,
                'party': inv.supplier.name,
                'due_date': inv.due_date.isoformat(),
                'amount': float(balance),
            })

    return sorted(items, key=lambda x: x['due_date'])


def build_accounting_dashboard(tenant, *, from_date=None, to_date=None, bs_fiscal_start_year=None) -> dict:
    today = timezone.now().date()

    if bs_fiscal_start_year:
        fy_start, fy_end = bs_fiscal_year_ad_range(int(bs_fiscal_start_year))
        fiscal_label = bs_fiscal_label(int(bs_fiscal_start_year))
    else:
        bs_year = current_bs_fiscal_start_year()
        fy_start, fy_end = bs_fiscal_year_ad_range(bs_year)
        fiscal_label = bs_fiscal_label(bs_year)
        bs_fiscal_start_year = bs_year

    if from_date and to_date:
        period_from = from_date if isinstance(from_date, date) else date.fromisoformat(str(from_date))
        period_to = to_date if isinstance(to_date, date) else date.fromisoformat(str(to_date))
    else:
        period_from, period_to = _month_range(today.year, today.month)

    month_pl = _period_pl(tenant, period_from, period_to)
    today_pl = _period_pl(tenant, today, today)
    fiscal_pl = _period_pl(tenant, fy_start, min(today, fy_end))
    vat = calculate_vat_for_period(tenant, fy_start, min(today, fy_end))

    cash_on_hand = _sum_account_balances(tenant, codes=['1000'])
    petty_cash = _sum_account_balances(tenant, codes=['1005'])
    bank_balance = _sum_account_balances(tenant, sub_types=['Bank'])

    recent_journals = list(
        JournalEntry.objects.filter(tenant=tenant)
        .order_by('-date', '-id')[:8]
        .values('id', 'entry_number', 'date', 'description', 'type', 'status', 'total_debit')
    )

    recent_payments = list(
        JournalEntry.objects.filter(
            tenant=tenant,
            type__in=['Payment', 'Receipt'],
            status__in=POSTED_GL_STATUSES,
        )
        .order_by('-date', '-id')[:8]
        .values('id', 'entry_number', 'date', 'description', 'type', 'total_debit', 'reference')
    )

    total_assets = _sum_account_balances(tenant, account_type='Assets')
    total_liabilities = _sum_account_balances(tenant, account_type='Liabilities')
    current_assets = _sum_account_balances(
        tenant, account_type='Assets', sub_types=['Cash', 'Bank', 'Receivable', 'Current Asset']
    )
    current_liabilities = _sum_account_balances(
        tenant, account_type='Liabilities', sub_types=['Payable', 'Current Liability', 'Tax']
    )
    total_equity = _sum_account_balances(tenant, account_type='Equity')
    working_capital = current_assets - current_liabilities
    breakdown = build_income_expense_breakdown(tenant, period_from, period_to)
    cash_flow = build_simple_cash_flow(tenant, period_from, period_to)

    recent_bank = list(
        BankTransaction.objects.filter(tenant=tenant)
        .select_related('bank_account')
        .order_by('-date', '-id')[:8]
        .values(
            'id', 'date', 'reference', 'description', 'type',
            'debit', 'credit', 'balance', 'bank_account__bank_name',
        )
    )

    return {
        'period': {'from_date': period_from.isoformat(), 'to_date': period_to.isoformat()},
        'fiscal_year': {
            'bs_start_year': bs_fiscal_start_year,
            'label': fiscal_label,
            'from_date': fy_start.isoformat(),
            'to_date': fy_end.isoformat(),
        },
        'cash_in_hand': float(cash_on_hand),
        'petty_cash': float(petty_cash),
        'bank_balance': float(bank_balance),
        'cash_and_bank': float(cash_on_hand + petty_cash + bank_balance),
        'today_income': today_pl['income'],
        'today_expenses': today_pl['expenses'],
        'monthly_income': month_pl['income'],
        'monthly_expenses': month_pl['expenses'],
        'monthly_gross_profit': month_pl['gross_profit'],
        'monthly_net_profit': month_pl['net_profit'],
        'fiscal_revenue': fiscal_pl['income'],
        'fiscal_expenses': fiscal_pl['expenses'],
        'fiscal_gross_profit': fiscal_pl['gross_profit'],
        'fiscal_net_profit': fiscal_pl['net_profit'],
        'total_assets': float(total_assets),
        'total_liabilities': float(total_liabilities),
        'total_equity': float(total_equity),
        'working_capital': float(working_capital),
        'outstanding_taxes': float(max(vat['net_payable'], Decimal('0'))),
        'accounts_receivable_gl': float(_sum_account_balances(tenant, sub_types=['Receivable'])),
        'accounts_payable_gl': float(
            _sum_account_balances(tenant, sub_types=['Payable'], account_type='Liabilities')
        ),
        'customer_outstanding': float(
            Customer.objects.filter(tenant=tenant).aggregate(
                total=Coalesce(Sum('current_balance'), Value(Decimal('0.00')))
            )['total']
        ),
        'supplier_outstanding': float(
            PurchaseInvoice.objects.filter(
                tenant=tenant,
                status__in=['Received', 'Partially Paid', 'Overdue'],
            ).aggregate(
                total=Coalesce(
                    Sum(F('amount') - F('paid_amount'), output_field=DecimalField()),
                    Value(Decimal('0.00')),
                )
            )['total']
        ),
        'vat_collected': float(vat['output_tax']),
        'vat_paid': float(vat['input_tax']),
        'vat_payable': float(vat['net_payable']),
        'vat_payable_gl': float(
            _sum_account_balances(tenant, sub_types=['Tax'], account_type='Liabilities')
        ),
        'recent_journal_entries': recent_journals,
        'recent_payments': recent_payments,
        'recent_bank_transactions': recent_bank,
        'monthly_trend': _monthly_trend(tenant, 6),
        'asset_distribution': build_account_distribution(tenant, 'Assets'),
        'liability_distribution': build_account_distribution(tenant, 'Liabilities'),
        'income_breakdown': breakdown['income'][:10],
        'expense_breakdown': breakdown['expenses'][:10],
        'cash_flow_summary': cash_flow,
        'financial_ratios': {
            'current_ratio': float(current_assets / current_liabilities) if current_liabilities > 0 else None,
            'net_margin_pct': (
                (month_pl['net_profit'] / month_pl['income'] * 100) if month_pl['income'] else 0
            ),
            'debt_to_equity': float(total_liabilities / total_equity) if total_equity > 0 else None,
            'working_capital': float(working_capital),
        },
        'upcoming_payments': _upcoming_payables(tenant, days=7),
    }
