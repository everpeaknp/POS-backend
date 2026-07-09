"""Reports helpers — dashboard financials, tax, GL reports, inventory snapshots."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounting.models import Account, JournalLine, TaxRule, VATReturn
from accounting.utils import calculate_vat_for_period
from construction.models import Attendance, MaterialConsumption, Site
from inventory.models import Product, Stock
from purchase.models import PurchaseInvoice, Supplier
from sales.models import Customer, Invoice, SalesOrder


def tenant_has_module(tenant, module_name: str) -> bool:
    if not tenant:
        return False
    return module_name in (tenant.active_modules or [])


def parse_report_dates(from_date_str, to_date_str, *, default_month: bool = True):
    today = timezone.now().date()
    if from_date_str:
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
    elif default_month:
        from_date = today.replace(day=1)
    else:
        from_date = today.replace(month=7, day=1) if today.month >= 7 else today.replace(
            year=today.year - 1, month=7, day=1
        )

    if to_date_str:
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
    else:
        to_date = today

    if from_date > to_date:
        from_date, to_date = to_date, from_date
    return from_date, to_date


def _month_end(day: date) -> date:
    last = monthrange(day.year, day.month)[1]
    return day.replace(day=last)


def _iter_months(from_date: date, to_date: date):
    current = from_date.replace(day=1)
    while current <= to_date:
        end = min(_month_end(current), to_date)
        start = max(current, from_date)
        yield start, end
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1, day=1)
        else:
            current = current.replace(month=current.month + 1, day=1)


def build_dashboard_financials(tenant, from_date: date, to_date: date, *, include_construction: bool):
    total_receivables = Customer.objects.filter(tenant=tenant).aggregate(
        total=Coalesce(Sum('current_balance'), Value(Decimal('0.00')))
    )['total']

    total_payables = Supplier.objects.filter(tenant=tenant).aggregate(
        total=Coalesce(Sum('current_balance'), Value(Decimal('0.00')))
    )['total']

    invoice_qs = Invoice.objects.filter(
        tenant=tenant,
        date__gte=from_date,
        date__lte=to_date,
    ).exclude(status='Draft')

    invoice_revenue = invoice_qs.aggregate(
        total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
    )['total']

    sales_revenue = SalesOrder.objects.filter(
        tenant=tenant,
        status='Delivered',
        date__gte=from_date,
        date__lte=to_date,
        invoices__isnull=True,
    ).aggregate(total=Coalesce(Sum('total'), Value(Decimal('0.00'))))['total']

    total_revenue = invoice_revenue + sales_revenue

    purchase_expenses = PurchaseInvoice.objects.filter(
        tenant=tenant,
        date__gte=from_date,
        date__lte=to_date,
    ).aggregate(total=Coalesce(Sum('amount'), Value(Decimal('0.00'))))['total']

    material_expenses = Decimal('0.00')
    labor_expenses = Decimal('0.00')
    if include_construction:
        material_expenses = MaterialConsumption.objects.filter(
            tenant=tenant,
            created_at__date__gte=from_date,
            created_at__date__lte=to_date,
        ).aggregate(
            total=Coalesce(
                Sum(F('quantity') * F('unit_cost'), output_field=DecimalField()),
                Value(Decimal('0.00')),
            )
        )['total']
        labor_expenses = Attendance.objects.filter(
            tenant=tenant,
            date__gte=from_date,
            date__lte=to_date,
        ).aggregate(total=Coalesce(Sum('wage_amount'), Value(Decimal('0.00'))))['total']

    total_expenses = purchase_expenses + material_expenses + labor_expenses
    net_profit = total_revenue - total_expenses
    profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')

    return {
        'total_receivables': float(total_receivables),
        'total_payables': float(total_payables),
        'total_revenue': float(total_revenue),
        'total_expenses': float(total_expenses),
        'net_profit': float(net_profit),
        'profit_margin_percentage': float(round(profit_margin, 2)),
        'period': {
            'from_date': from_date.isoformat(),
            'to_date': to_date.isoformat(),
        },
        'breakdown': {
            'sales_revenue': float(sales_revenue),
            'invoice_revenue': float(invoice_revenue),
            'purchase_expenses': float(purchase_expenses),
            'material_expenses': float(material_expenses),
            'labor_expenses': float(labor_expenses),
        },
    }


def build_low_stock_items(tenant, *, limit: int | None = None):
    products = Product.objects.filter(tenant=tenant).annotate(
        total_stock=Coalesce(Sum('stocks__quantity'), Value(Decimal('0.00')))
    ).filter(total_stock__lt=F('reorder_level')).order_by('total_stock')

    if limit is not None:
        products = products[:limit]

    items = []
    for product in products:
        stock_deficit = product.reorder_level - product.total_stock
        urgency = 'critical' if product.total_stock < (product.reorder_level * Decimal('0.5')) else 'low'
        warehouses = Stock.objects.filter(tenant=tenant, product=product).values(
            'warehouse__name'
        ).annotate(quantity=Sum('quantity'))
        items.append({
            'product_id': str(product.id),
            'product_name': product.name,
            'sku': product.sku,
            'current_stock': float(product.total_stock),
            'reorder_level': float(product.reorder_level),
            'unit': product.unit.name if product.unit else 'unit',
            'stock_deficit': float(stock_deficit),
            'urgency': urgency,
            'warehouses': list(warehouses),
        })
    return items


def build_construction_budget_alerts(tenant):
    sites = Site.objects.filter(tenant=tenant, status='active')
    budget_alert_sites = []

    for site in sites:
        material_cost = MaterialConsumption.objects.filter(tenant=tenant, site=site).aggregate(
            total=Coalesce(
                Sum(F('quantity') * F('unit_cost'), output_field=DecimalField()),
                Value(Decimal('0.00')),
            )
        )['total']
        labor_cost = Attendance.objects.filter(tenant=tenant, site=site).aggregate(
            total=Coalesce(Sum('wage_amount'), Value(Decimal('0.00')))
        )['total']
        other_expenses = site.daily_logs.aggregate(
            total=Coalesce(Sum('other_expenses'), Value(Decimal('0.00')))
        )['total']
        equipment_cost = site.equipment_usage_logs.aggregate(
            total=Coalesce(Sum('cost'), Value(Decimal('0.00')))
        )['total']

        actual_spend = material_cost + labor_cost + equipment_cost + other_expenses
        budget_utilization = (
            (actual_spend / site.allocated_budget * 100) if site.allocated_budget > 0 else Decimal('0.00')
        )

        if budget_utilization <= 80:
            continue

        remaining_budget = site.allocated_budget - actual_spend
        if budget_utilization > 100:
            alert_level = 'critical'
        elif budget_utilization > 95:
            alert_level = 'high'
        else:
            alert_level = 'warning'

        budget_alert_sites.append({
            'site_id': str(site.id),
            'site_name': site.name,
            'location': site.location,
            'status': site.status,
            'allocated_budget': float(site.allocated_budget),
            'actual_spend': float(actual_spend),
            'budget_utilization_percentage': float(round(budget_utilization, 2)),
            'remaining_budget': float(remaining_budget),
            'alert_level': alert_level,
            'breakdown': {
                'material_cost': float(material_cost),
                'labor_cost': float(labor_cost),
                'equipment_cost': float(equipment_cost),
                'other_expenses': float(other_expenses),
            },
        })

    critical_sites = sum(1 for site in budget_alert_sites if site['alert_level'] == 'critical')
    return {
        'budget_alert_sites': budget_alert_sites,
        'critical_sites': critical_sites,
        'total_active_sites': sites.count(),
    }


def _vat_monthly_row(tenant, month_start: date, month_end: date, filed_periods: set):
    vat = calculate_vat_for_period(tenant, month_start, month_end)
    output_vat = vat['output_tax']
    input_vat = vat['input_tax']

    sales_ex_vat = (
        output_vat / Decimal('0.13') if output_vat > 0 else Decimal('0.00')
    )
    purchase_qs = PurchaseInvoice.objects.filter(
        tenant=tenant,
        date__gte=month_start,
        date__lte=month_end,
    )
    purchases_ex_vat = (
        input_vat / Decimal('0.13') if input_vat > 0 else (
            purchase_qs.aggregate(
                total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
            )['total'] or Decimal('0')
        )
    )

    label = month_start.strftime('%b %Y')
    period_key = f'{month_start.isoformat()}_{month_end.isoformat()}'
    status = 'filed' if period_key in filed_periods else 'unfiled'

    return {
        'month': label,
        'sales_ex_vat': float(sales_ex_vat),
        'output_vat': float(vat['output_tax']),
        'purchases_ex_vat': float(purchases_ex_vat),
        'input_vat': float(vat['input_tax']),
        'net_vat': float(vat['net_payable']),
        'status': status,
    }


def build_tax_reports(tenant, from_date: date, to_date: date):
    period_vat = calculate_vat_for_period(tenant, from_date, to_date)

    filed_returns = VATReturn.objects.filter(
        tenant=tenant,
        status__in=['filed', 'paid'],
        from_date__gte=from_date,
        to_date__lte=to_date,
    )
    filed_periods = {
        f'{vr.from_date.isoformat()}_{vr.to_date.isoformat()}' for vr in filed_returns
    }
    returns_filed = filed_returns.count()

    monthly = [_vat_monthly_row(tenant, start, end, filed_periods) for start, end in _iter_months(from_date, to_date)]

    tds_rules = {
        rule.account_id: rule
        for rule in TaxRule.objects.filter(tenant=tenant, type='TDS', status='active').select_related('account')
    }
    tds_account_ids = list(tds_rules.keys())
    if not tds_account_ids:
        default_tds = Account._base_manager.filter(tenant=tenant, code='2300').first()
        if default_tds:
            tds_account_ids = [default_tds.id]

    tds_lines = JournalLine.objects.filter(
        tenant=tenant,
        account_id__in=tds_account_ids,
        journal_entry__status='posted',
        journal_entry__date__gte=from_date,
        journal_entry__date__lte=to_date,
        credit__gt=0,
    ).select_related('journal_entry')

    tds_details = []
    on_services = Decimal('0.00')
    on_rent = Decimal('0.00')
    on_goods = Decimal('0.00')
    total_deducted = Decimal('0.00')

    entries_seen = {}
    for line in tds_lines:
        entry = line.journal_entry
        if entry.id in entries_seen:
            continue
        entries_seen[entry.id] = True
        amount = line.credit
        total_deducted += amount

        rule = tds_rules.get(line.account_id)
        rate = float(rule.rate) if rule else 0.0
        type_label = (rule.name if rule else 'TDS').lower()
        if 'rent' in type_label:
            category = 'Rent'
            on_rent += amount
        elif 'goods' in type_label or 'purchase' in type_label:
            category = 'Goods'
            on_goods += amount
        else:
            category = 'Services'
            on_services += amount

        gross = float(amount / Decimal(str(rate / 100))) if rate > 0 else float(amount * 10)
        tds_details.append({
            'supplier': entry.description or entry.reference or 'Supplier',
            'pan': '',
            'type': category,
            'gross': gross,
            'rate': rate,
            'tds': float(amount),
            'date': entry.date.isoformat(),
            'submitted': True,
        })

    income_employees = []
    try:
        from hr.models import Employee, Payroll

        payroll_qs = Payroll.objects.filter(
            tenant=tenant,
            status__in=['processed', 'paid'],
        ).select_related('employee')

        employee_totals: dict[int, dict] = {}
        for row in payroll_qs:
            if row.year < from_date.year or (row.year == from_date.year and _month_index(row.month) < from_date.month):
                continue
            if row.year > to_date.year or (row.year == to_date.year and _month_index(row.month) > to_date.month):
                continue
            bucket = employee_totals.setdefault(
                row.employee_id,
                {'employee': row.employee, 'gross': Decimal('0'), 'deductions': Decimal('0')},
            )
            bucket['gross'] += row.gross_salary
            bucket['deductions'] += row.deductions

        for bucket in employee_totals.values():
            emp = bucket['employee']
            gross_ytd = bucket['gross']
            tax_deducted = bucket['deductions']
            taxable = max(Decimal('0'), gross_ytd - Decimal('50000'))
            tax_amount = _estimate_income_tax(taxable)
            income_employees.append({
                'employee': emp.name,
                'pan': getattr(emp, 'pan', '') or '',
                'gross_salary_ytd': float(gross_ytd),
                'taxable_income': float(taxable),
                'tax_slab': 'Nepal progressive (estimated)',
                'tax_amount': float(tax_amount),
                'tax_deducted': float(tax_deducted),
                'balance': float(tax_amount - tax_deducted),
            })
    except Exception:
        income_employees = []

    return {
        'period': {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat()},
        'vat': {
            'output_vat': float(period_vat['output_tax']),
            'input_vat': float(period_vat['input_tax']),
            'net_payable': float(period_vat['net_payable']),
            'returns_filed': returns_filed,
            'monthly': monthly,
        },
        'tds': {
            'total_deducted': float(total_deducted),
            'on_services': float(on_services),
            'on_rent': float(on_rent),
            'on_goods': float(on_goods),
            'details': tds_details,
        },
        'income_tax': {'employees': income_employees},
    }


def _month_index(month_label: str) -> int:
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
    }
    return months.get(month_label.lower(), 1)


def _estimate_income_tax(taxable: Decimal) -> Decimal:
    """Simplified Nepal-style progressive estimate for reporting."""
    annual = taxable
    tax = Decimal('0')
    brackets = [
        (Decimal('500000'), Decimal('0.01')),
        (Decimal('700000'), Decimal('0.10')),
        (Decimal('1000000'), Decimal('0.20')),
        (Decimal('2000000'), Decimal('0.30')),
        (None, Decimal('0.36')),
    ]
    remaining = annual
    for cap, rate in brackets:
        if remaining <= 0:
            break
        if cap is None:
            tax += remaining * rate
            break
        slice_amount = min(remaining, cap)
        tax += slice_amount * rate
        remaining -= slice_amount
    return tax.quantize(Decimal('0.01'))


def _lines_for_account(tenant, account, *, from_date=None, to_date=None, as_of_date=None):
    lines = JournalLine.objects.filter(
        tenant=tenant,
        account=account,
        journal_entry__status='posted',
    )
    if from_date and to_date:
        lines = lines.filter(journal_entry__date__gte=from_date, journal_entry__date__lte=to_date)
    elif as_of_date:
        lines = lines.filter(journal_entry__date__lte=as_of_date)
    return lines


def _account_net_balance(account, debit_sum: Decimal, credit_sum: Decimal) -> Decimal:
    if account.type in ['Assets', 'Expense']:
        return debit_sum - credit_sum
    return credit_sum - debit_sum


def build_financial_reports(tenant, from_date: date, to_date: date, as_of_date: date) -> dict:
    income_accounts = Account.objects.filter(tenant=tenant, type='Income', status='active')
    expense_accounts = Account.objects.filter(tenant=tenant, type='Expense', status='active')

    pnl_income = []
    pnl_expenses = []
    total_income = Decimal('0.00')
    total_expenses = Decimal('0.00')

    for account in income_accounts:
        aggregates = _lines_for_account(tenant, account, from_date=from_date, to_date=to_date).aggregate(
            debit=Coalesce(Sum('debit'), Value(Decimal('0.00'))),
            credit=Coalesce(Sum('credit'), Value(Decimal('0.00'))),
        )
        balance = aggregates['credit'] - aggregates['debit']
        if balance != 0:
            total_income += balance
            pnl_income.append({'account': account.name, 'type': 'Income', 'amount': float(balance)})

    for account in expense_accounts:
        aggregates = _lines_for_account(tenant, account, from_date=from_date, to_date=to_date).aggregate(
            debit=Coalesce(Sum('debit'), Value(Decimal('0.00'))),
            credit=Coalesce(Sum('credit'), Value(Decimal('0.00'))),
        )
        balance = aggregates['debit'] - aggregates['credit']
        if balance != 0:
            total_expenses += balance
            pnl_expenses.append({'account': account.name, 'type': 'Expense', 'amount': float(balance)})

    net_profit = total_income - total_expenses

    assets = []
    liabilities = []
    equity = []
    total_assets = Decimal('0.00')
    total_liabilities = Decimal('0.00')
    total_equity = Decimal('0.00')

    for account in Account.objects.filter(tenant=tenant, type='Assets', status='active'):
        aggregates = _lines_for_account(tenant, account, as_of_date=as_of_date).aggregate(
            debit=Coalesce(Sum('debit'), Value(Decimal('0.00'))),
            credit=Coalesce(Sum('credit'), Value(Decimal('0.00'))),
        )
        balance = _account_net_balance(account, aggregates['debit'], aggregates['credit'])
        if balance != 0:
            total_assets += balance
            assets.append({'account': account.name, 'amount': float(balance)})

    for account in Account.objects.filter(tenant=tenant, type='Liabilities', status='active'):
        aggregates = _lines_for_account(tenant, account, as_of_date=as_of_date).aggregate(
            debit=Coalesce(Sum('debit'), Value(Decimal('0.00'))),
            credit=Coalesce(Sum('credit'), Value(Decimal('0.00'))),
        )
        balance = _account_net_balance(account, aggregates['debit'], aggregates['credit'])
        if balance != 0:
            total_liabilities += balance
            liabilities.append({'account': account.name, 'amount': float(balance)})

    for account in Account.objects.filter(tenant=tenant, type='Equity', status='active'):
        aggregates = _lines_for_account(tenant, account, as_of_date=as_of_date).aggregate(
            debit=Coalesce(Sum('debit'), Value(Decimal('0.00'))),
            credit=Coalesce(Sum('credit'), Value(Decimal('0.00'))),
        )
        balance = _account_net_balance(account, aggregates['debit'], aggregates['credit'])
        if balance != 0:
            total_equity += balance
            equity.append({'account': account.name, 'amount': float(balance)})

    net_income = Decimal('0.00')
    for account in Account.objects.filter(tenant=tenant, status='active', type__in=['Income', 'Expense']):
        aggregates = _lines_for_account(tenant, account, as_of_date=as_of_date).aggregate(
            debit=Coalesce(Sum('debit'), Value(Decimal('0.00'))),
            credit=Coalesce(Sum('credit'), Value(Decimal('0.00'))),
        )
        if account.type == 'Income':
            net_income += aggregates['credit'] - aggregates['debit']
        else:
            net_income -= aggregates['debit'] - aggregates['credit']

    if net_income != 0:
        equity.append({'account': 'Current Year Earnings', 'amount': float(net_income)})
        total_equity += net_income

    trial_accounts = []
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')
    for account in Account.objects.filter(tenant=tenant, status='active').order_by('type', 'code'):
        aggregates = _lines_for_account(tenant, account, as_of_date=as_of_date).aggregate(
            debit=Coalesce(Sum('debit'), Value(Decimal('0.00'))),
            credit=Coalesce(Sum('credit'), Value(Decimal('0.00'))),
        )
        net = aggregates['debit'] - aggregates['credit']
        if net == 0:
            continue

        is_debit_type = account.type in ['Assets', 'Expense']
        if is_debit_type:
            debit_balance, credit_balance = (net, Decimal('0')) if net > 0 else (Decimal('0'), abs(net))
        elif net < 0:
            debit_balance, credit_balance = Decimal('0'), abs(net)
        else:
            debit_balance, credit_balance = net, Decimal('0')

        total_debit += debit_balance
        total_credit += credit_balance
        trial_accounts.append({
            'account': account.name,
            'debit': float(debit_balance),
            'credit': float(credit_balance),
        })

    cash_q = Q(sub_type__icontains='Cash') | Q(sub_type__icontains='Bank') | Q(code__startswith='10')
    cash_accounts = Account.objects.filter(tenant=tenant, status='active', type='Assets').filter(cash_q)

    opening_cash = Decimal('0.00')
    closing_cash = Decimal('0.00')
    for account in cash_accounts:
        opening_agg = _lines_for_account(tenant, account, as_of_date=from_date - timedelta(days=1)).aggregate(
            debit=Coalesce(Sum('debit'), Value(Decimal('0.00'))),
            credit=Coalesce(Sum('credit'), Value(Decimal('0.00'))),
        )
        opening_cash += opening_agg['debit'] - opening_agg['credit']

        closing_agg = _lines_for_account(tenant, account, as_of_date=to_date).aggregate(
            debit=Coalesce(Sum('debit'), Value(Decimal('0.00'))),
            credit=Coalesce(Sum('credit'), Value(Decimal('0.00'))),
        )
        closing_cash += closing_agg['debit'] - closing_agg['credit']

    fixed_asset_ids = list(
        Account.objects.filter(tenant=tenant, status='active', type='Assets').filter(
            Q(sub_type__icontains='Fixed') | Q(sub_type__icontains='Equipment') | Q(code__startswith='15')
        ).values_list('id', flat=True)
    )
    investing_cash = Decimal('0.00')
    if fixed_asset_ids:
        investing_cash = JournalLine.objects.filter(
            tenant=tenant,
            account_id__in=fixed_asset_ids,
            journal_entry__status='posted',
            journal_entry__date__gte=from_date,
            journal_entry__date__lte=to_date,
            debit__gt=0,
        ).aggregate(total=Coalesce(Sum('debit'), Value(Decimal('0.00'))))['total']
        investing_cash = -investing_cash

    financing_ids = list(
        Account.objects.filter(tenant=tenant, status='active').filter(
            Q(type='Equity') | Q(type='Liabilities', sub_type__icontains='Loan')
        ).values_list('id', flat=True)
    )
    financing_cash = Decimal('0.00')
    if financing_ids:
        financing_agg = JournalLine.objects.filter(
            tenant=tenant,
            account_id__in=financing_ids,
            journal_entry__status='posted',
            journal_entry__date__gte=from_date,
            journal_entry__date__lte=to_date,
        ).aggregate(
            credit=Coalesce(Sum('credit'), Value(Decimal('0.00'))),
            debit=Coalesce(Sum('debit'), Value(Decimal('0.00'))),
        )
        financing_cash = financing_agg['credit'] - financing_agg['debit']

    operating_cash = net_profit
    net_cash_change = closing_cash - opening_cash

    return {
        'profit_and_loss': {
            'period': {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat()},
            'income': pnl_income,
            'expenses': pnl_expenses,
            'total_income': float(total_income),
            'total_expenses': float(total_expenses),
            'net_profit': float(net_profit),
        },
        'balance_sheet': {
            'as_of_date': as_of_date.isoformat(),
            'assets': assets,
            'liabilities': liabilities,
            'equity': equity,
            'total_assets': float(total_assets),
            'total_liabilities': float(total_liabilities),
            'total_equity': float(total_equity),
        },
        'trial_balance': {
            'as_of_date': as_of_date.isoformat(),
            'accounts': trial_accounts,
            'total_debit': float(total_debit),
            'total_credit': float(total_credit),
        },
        'cash_flow': {
            'period': {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat()},
            'operating_activities': float(operating_cash),
            'investing_activities': float(investing_cash),
            'financing_activities': float(financing_cash),
            'net_cash_change': float(net_cash_change),
            'opening_cash': float(opening_cash),
            'closing_cash': float(closing_cash),
        },
    }


def build_inventory_stock_summary(tenant):
    products = Product.objects.filter(tenant=tenant).annotate(
        total_stock=Coalesce(Sum('stocks__quantity'), Value(Decimal('0.00')))
    )
    total_products = products.count()
    total_units = Stock.objects.filter(tenant=tenant).aggregate(
        total=Coalesce(Sum('quantity'), Value(Decimal('0.00')))
    )['total']
    low_stock_count = products.filter(total_stock__lte=F('reorder_level'), total_stock__gt=0).count()
    out_of_stock_count = products.filter(total_stock=0).count()

    stock_data = []
    for product in products.order_by('-total_stock')[:10]:
        stock_data.append({'name': product.sku, 'stock': float(product.total_stock)})

    return {
        'summary': {
            'total_products': total_products,
            'total_units': float(total_units),
            'low_stock': low_stock_count,
            'out_of_stock': out_of_stock_count,
        },
        'stock_data': stock_data,
    }


def build_inventory_low_stock(tenant):
    products = Product.objects.filter(tenant=tenant).annotate(
        total_stock=Coalesce(Sum('stocks__quantity'), Value(Decimal('0.00')))
    ).filter(total_stock__lte=F('reorder_level')).select_related('category', 'unit').order_by('total_stock')

    items = []
    for product in products:
        shortage = max(Decimal('0'), product.reorder_level - product.total_stock)
        status_label = 'Out of Stock' if product.total_stock == 0 else 'Low Stock'
        items.append({
            'id': product.id,
            'name': product.name,
            'sku': product.sku,
            'current_stock': float(product.total_stock),
            'reorder_level': float(product.reorder_level),
            'shortage': float(shortage),
            'status': status_label,
            'category': product.category.name if product.category else None,
            'unit': product.unit.name if product.unit else 'unit',
        })

    return {'items': items, 'total_count': len(items)}


def build_inventory_valuation_report(tenant):
    products = Product.objects.filter(tenant=tenant).annotate(
        total_stock=Coalesce(Sum('stocks__quantity'), Value(Decimal('0.00')))
    ).filter(total_stock__gt=0).select_related('category', 'unit')

    valuation_items = []
    total_cost_value = Decimal('0.00')
    total_sale_value = Decimal('0.00')
    valuation_data = []

    for product in products:
        cost_value = product.total_stock * product.cost_price
        sale_value = product.total_stock * product.selling_price
        total_cost_value += cost_value
        total_sale_value += sale_value
        valuation_items.append({
            'id': product.id,
            'name': product.name,
            'sku': product.sku,
            'stock': float(product.total_stock),
            'cost_price': float(product.cost_price),
            'selling_price': float(product.selling_price),
            'total_cost_value': float(cost_value),
            'total_sale_value': float(sale_value),
            'unit': product.unit.name if product.unit else 'unit',
        })

    for item in sorted(valuation_items, key=lambda x: x['total_cost_value'], reverse=True)[:10]:
        valuation_data.append({'name': item['sku'], 'value': item['total_cost_value']})

    return {
        'summary': {
            'total_cost_value': float(total_cost_value),
            'total_sale_value': float(total_sale_value),
            'potential_profit': float(total_sale_value - total_cost_value),
        },
        'items': valuation_items,
        'valuation_data': valuation_data,
    }
