"""
Accounting Services - Core Layer
Provides accounting operations used by all industry modules.
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from accounting.models import JournalEntry, JournalLine, Account, FiscalYear
from accounting.vat_helpers import split_tax_inclusive_amount
from accounting.utils import get_vat_payable_account
from tenants.middleware import get_current_tenant


def assert_period_open(tenant, entry_date) -> None:
    """Block posting into a closed fiscal year."""
    if not tenant or not entry_date:
        return
    if FiscalYear.objects.filter(
        tenant=tenant,
        is_closed=True,
        start_date__lte=entry_date,
        end_date__gte=entry_date,
    ).exists():
        raise ValueError('Cannot post transactions into a closed fiscal year.')


def has_posted_journal(tenant, reference, entry_type=None):
    """Return True if a posted journal already exists for this reference."""
    if not reference:
        return False
    qs = JournalEntry.objects.filter(tenant=tenant, reference=reference, status='posted')
    if entry_type:
        qs = qs.filter(type=entry_type)
    return qs.exists()


def create_journal_entry(tenant, description, entries, reference=None, date=None, entry_type='Manual'):
    """
    Create a double-entry journal entry.
    
    This is the CORE accounting function used by all modules to record
    financial transactions. Ensures double-entry bookkeeping is maintained.
    
    Args:
        tenant: Tenant instance
        description: Entry description
        entries: List of dicts with 'account', 'debit', 'credit'
                 Example: [
                     {'account': account_obj, 'debit': 1000, 'credit': 0},
                     {'account': account_obj, 'debit': 0, 'credit': 1000}
                 ]
        reference: Optional reference number (e.g., invoice number)
        date: Optional date (defaults to today)
    
    Returns:
        JournalEntry instance
    
    Raises:
        ValueError: If debits don't equal credits
    """
    with transaction.atomic():
        # Validate double-entry
        total_debit = sum(Decimal(str(e['debit'])) for e in entries)
        total_credit = sum(Decimal(str(e['credit'])) for e in entries)
        
        if total_debit != total_credit:
            raise ValueError(
                f"Debits ({total_debit}) must equal credits ({total_credit}). "
                f"Double-entry bookkeeping violation."
            )

        entry_date = date or timezone.now().date()
        assert_period_open(tenant, entry_date)
        
        from accounting.utils import generate_entry_number
        entry_number = generate_entry_number(tenant)
        
        # Create journal entry
        journal_entry = JournalEntry.objects.create(
            tenant=tenant,
            entry_number=entry_number,
            date=entry_date,
            description=description,
            reference=reference or '',
            type=entry_type,
            total_debit=total_debit,
            total_credit=total_credit,
            status='posted',
            posted_date=timezone.now(),
        )
        
        # Create journal lines
        for entry in entries:
            JournalLine.objects.create(
                tenant=tenant,
                journal_entry=journal_entry,
                account=entry['account'],
                debit=Decimal(str(entry['debit'])),
                credit=Decimal(str(entry['credit'])),
                description=entry.get('description', description)
            )

        apply_entry_balances(journal_entry)
        
        return journal_entry


# ============================================================================
# CORE ACCOUNT GETTERS
# These functions ensure standard accounts exist for all tenants
# ============================================================================

def get_or_create_account(code, name, account_type, tenant=None):
    """Helper to get or create a standard account"""
    if tenant is None:
        tenant = get_current_tenant()
    
    if not tenant:
        raise ValueError("No tenant in context. Cannot create account.")
    
    # Map simple account types to Account model types
    type_mapping = {
        'asset': 'Assets',
        'liability': 'Liabilities',
        'equity': 'Equity',
        'revenue': 'Income',
        'expense': 'Expense'
    }
    
    # Map to sub_types
    sub_type_mapping = {
        '1000': 'Cash',  # Cash
        '1100': 'Receivable',  # Accounts Receivable
        '1200': 'Current Asset',  # Inventory
        '2000': 'Payable',  # Accounts Payable
        '2100': 'Payable',  # Wages Payable (Construction Workers)
        '2200': 'Payable',  # Salary Payable (HR Employees)
        '4000': 'Revenue',  # Sales Revenue
        '5000': 'COGS',  # Cost of Goods Sold
        '5100': 'Operating',  # Construction Expenses
        '5200': 'Operating',  # Labor Expenses (Construction)
        '5300': 'Operating',  # Equipment Expenses
        '5400': 'Operating',  # Salary Expense (HR Employees)
    }
    
    account, created = Account._base_manager.get_or_create(
        tenant=tenant,
        code=code,
        defaults={
            'name': name,
            'type': type_mapping.get(account_type, 'Expense'),
            'sub_type': sub_type_mapping.get(code, 'Operating'),
            'status': 'active',
            'level': 0
        }
    )
    return account


def get_cash_account(tenant=None):
    """Get or create Cash account (Asset)"""
    return get_or_create_account('1000', 'Cash', 'asset', tenant)


def get_accounts_receivable_account(tenant=None):
    """Get or create Accounts Receivable account (Asset)"""
    return get_or_create_account('1100', 'Accounts Receivable', 'asset', tenant)


def get_inventory_asset_account(tenant=None):
    """Get or create Inventory account (Asset)"""
    return get_or_create_account('1200', 'Inventory', 'asset', tenant)


def get_accounts_payable_account(tenant=None):
    """Get or create Accounts Payable account (Liability)"""
    return get_or_create_account('2000', 'Accounts Payable', 'liability', tenant)


def get_wages_payable_account(tenant=None):
    """Get or create Wages Payable account (Liability) — used for construction workers"""
    return get_or_create_account('2100', 'Wages Payable', 'liability', tenant)


def get_salary_payable_account(tenant=None):
    """Get or create Salary Payable account (Liability) — used for HR employees"""
    if tenant is None:
        tenant = get_current_tenant()
    if not tenant:
        raise ValueError("No tenant in context. Cannot create account.")
    account, _ = Account._base_manager.get_or_create(
        tenant=tenant,
        code='2200',
        defaults={
            'name': 'Salary Payable',
            'type': 'Liabilities',
            'sub_type': 'Payable',
            'status': 'active',
            'level': 0,
        }
    )
    return account


def get_sales_revenue_account(tenant=None):
    """Get or create Sales Revenue account (Revenue)"""
    return get_or_create_account('4000', 'Sales Revenue', 'revenue', tenant)


def get_cost_of_goods_sold_account(tenant=None):
    """Get or create Cost of Goods Sold account (Expense)"""
    return get_or_create_account('5000', 'Cost of Goods Sold', 'expense', tenant)


def get_construction_expense_account(tenant=None):
    """Get or create Construction Expense account (Expense)"""
    return get_or_create_account('5100', 'Construction Expenses', 'expense', tenant)


def get_labor_expense_account(tenant=None):
    """Get or create Labor Expense account (Expense)"""
    return get_or_create_account('5200', 'Labor Expenses', 'expense', tenant)


def get_equipment_expense_account(tenant=None):
    """Get or create Equipment Expense account (Expense)"""
    return get_or_create_account('5300', 'Equipment Expenses', 'expense', tenant)


# ============================================================================
# INDUSTRY MODULE HELPERS
# These functions are called by industry modules to record transactions
# ============================================================================

def record_material_consumption(site, product, quantity, unit_cost, reference, tenant=None):
    """
    Record material consumption for construction site.
    Called by Construction module.
    
    Accounting Entry:
    Dr. Construction Expense (Site Cost Center)
    Cr. Inventory Asset
    """
    if tenant is None:
        tenant = get_current_tenant()
    
    if not tenant:
        raise ValueError("Tenant is required for accounting entry")
    if has_posted_journal(tenant, reference, 'Construction'):
        return None
    
    total_cost = Decimal(str(quantity)) * Decimal(str(unit_cost))
    
    # Get site's cost center account or use default construction expense
    cost_center = getattr(site, 'cost_center_account', None) or get_construction_expense_account(tenant)
    
    return create_journal_entry(
        tenant=tenant,
        description=f"Material consumption: {product.name} at {site.name}",
        reference=reference,
        entry_type='Construction',
        entries=[
            {
                'account': cost_center,
                'debit': total_cost,
                'credit': 0,
                'description': f"Material: {product.name} ({quantity} units)"
            },
            {
                'account': get_inventory_asset_account(tenant),
                'debit': 0,
                'credit': total_cost,
                'description': f"Stock reduction: {product.name}"
            }
        ]
    )


def reverse_material_consumption(site, product, quantity, unit_cost, reference, tenant=None):
    """
    Reverse material consumption journal entry (e.g. on consumption delete).
    """
    if tenant is None:
        tenant = get_current_tenant()

    if not tenant:
        raise ValueError("Tenant is required for accounting entry")

    rev_ref = f"{reference}-REV"
    if has_posted_journal(tenant, rev_ref, 'Construction'):
        return None

    total_cost = Decimal(str(quantity)) * Decimal(str(unit_cost))
    cost_center = getattr(site, 'cost_center_account', None) or get_construction_expense_account(tenant)

    return create_journal_entry(
        tenant=tenant,
        description=f"Reversal: {product.name} at {site.name}",
        reference=rev_ref,
        entry_type='Construction',
        entries=[
            {
                'account': get_inventory_asset_account(tenant),
                'debit': total_cost,
                'credit': 0,
                'description': f"Stock restored: {product.name} ({quantity} units)",
            },
            {
                'account': cost_center,
                'debit': 0,
                'credit': total_cost,
                'description': f"Expense reversal: {product.name}",
            },
        ],
    )


def record_labor_wage(site, worker, wage_amount, date, reference, tenant=None):
    """
    Record labor wage expense for construction site.
    Called by Construction module.
    
    Accounting Entry:
    Dr. Labor Expense (Site Cost Center)
    Cr. Wages Payable
    """
    if tenant is None:
        tenant = get_current_tenant()
    if not tenant:
        raise ValueError("Tenant is required for accounting entry")
    if has_posted_journal(tenant, reference, 'Construction'):
        return None

    wage_amount = Decimal(str(wage_amount))
    if wage_amount <= 0:
        return None
    
    cost_center = getattr(site, 'cost_center_account', None) or get_labor_expense_account(tenant)
    
    return create_journal_entry(
        tenant=tenant,
        description=f"Labor wage: {worker.name} at {site.name}",
        reference=reference,
        date=date,
        entry_type='Construction',
        entries=[
            {
                'account': cost_center,
                'debit': wage_amount,
                'credit': 0,
                'description': f"Worker: {worker.name} ({worker.category})"
            },
            {
                'account': get_wages_payable_account(tenant),
                'debit': 0,
                'credit': wage_amount,
                'description': f"Wage payable to {worker.name}"
            }
        ]
    )


def record_equipment_usage(site, equipment, amount, date, reference, tenant=None):
    """Record rented equipment usage expense."""
    if tenant is None:
        tenant = get_current_tenant()
    if not tenant:
        raise ValueError("Tenant is required for accounting entry")
    if has_posted_journal(tenant, reference, 'Construction'):
        return None

    amount = Decimal(str(amount))
    if amount <= 0:
        return None

    return create_journal_entry(
        tenant=tenant,
        description=f"Equipment usage: {equipment.name} at {site.name}",
        reference=reference,
        date=date,
        entry_type='Construction',
        entries=[
            {
                'account': get_equipment_expense_account(tenant),
                'debit': amount,
                'credit': 0,
                'description': f"Equipment: {equipment.name}",
            },
            {
                'account': get_accounts_payable_account(tenant),
                'debit': 0,
                'credit': amount,
                'description': f"Equipment rental payable",
            },
        ],
    )


def record_site_other_expense(site, amount, date, reference, description, tenant=None):
    """Record miscellaneous site expenses from daily logs."""
    if tenant is None:
        tenant = get_current_tenant()
    if not tenant:
        raise ValueError("Tenant is required for accounting entry")
    if has_posted_journal(tenant, reference, 'Construction'):
        return None

    amount = Decimal(str(amount))
    if amount <= 0:
        return None

    return create_journal_entry(
        tenant=tenant,
        description=description or f"Site expense at {site.name}",
        reference=reference,
        date=date,
        entry_type='Construction',
        entries=[
            {
                'account': get_construction_expense_account(tenant),
                'debit': amount,
                'credit': 0,
                'description': description or "Other site expense",
            },
            {
                'account': get_cash_account(tenant),
                'debit': 0,
                'credit': amount,
                'description': "Cash payment for site expense",
            },
        ],
    )


def record_payroll_expense(employee, net_salary, reference, date, tenant=None):
    """
    Record HR employee payroll expense.
    Called by HR Payroll module.

    Accounting Entry:
    Dr. Salary Expense   (5400)
    Cr. Salary Payable   (2200)  ← HR employees, NOT construction wages
    """
    if tenant is None:
        tenant = get_current_tenant()
    if not tenant:
        raise ValueError("Tenant is required for accounting entry")
    if has_posted_journal(tenant, reference, 'Payroll'):
        return None

    net_salary = Decimal(str(net_salary))
    if net_salary <= 0:
        return None

    salary_expense_account = get_or_create_account('5400', 'Salary Expense', 'expense', tenant)

    return create_journal_entry(
        tenant=tenant,
        description=f"Payroll: {employee.name}",
        reference=reference,
        date=date,
        entry_type='Payroll',
        entries=[
            {
                'account': salary_expense_account,
                'debit': net_salary,
                'credit': 0,
                'description': f"Salary for {employee.name}",
            },
            {
                'account': get_salary_payable_account(tenant),
                'debit': 0,
                'credit': net_salary,
                'description': f"Salary payable to {employee.name}",
            },
        ],
    )


def _sale_gl_entries(*, debit_account, gross_amount, tax_amount, tenant, description):
    """Build balanced sale lines with optional VAT split."""
    net_amount, vat_amount = split_tax_inclusive_amount(
        gross_amount, tax_amount=tax_amount, tenant=tenant, applicable_on='Sales'
    )
    revenue_account = get_sales_revenue_account(tenant)
    lines = [
        {'account': debit_account, 'debit': net_amount + vat_amount, 'credit': 0, 'description': description},
        {'account': revenue_account, 'debit': 0, 'credit': net_amount, 'description': description},
    ]
    if vat_amount > 0:
        lines.append({
            'account': get_vat_payable_account(tenant),
            'debit': 0,
            'credit': vat_amount,
            'description': f'Output VAT — {description}',
        })
    return lines


def _purchase_gl_entries(*, gross_amount, tax_amount, tenant, description, supplier_name):
    net_amount, vat_amount = split_tax_inclusive_amount(
        gross_amount, tax_amount=tax_amount, tenant=tenant, applicable_on='Purchase'
    )
    lines = [
        {
            'account': get_inventory_asset_account(tenant),
            'debit': net_amount,
            'credit': 0,
            'description': f'Supplier: {supplier_name}',
        },
    ]
    if vat_amount > 0:
        lines.append({
            'account': get_vat_payable_account(tenant),
            'debit': vat_amount,
            'credit': 0,
            'description': f'Input VAT — {supplier_name}',
        })
    lines.append({
        'account': get_accounts_payable_account(tenant),
        'debit': 0,
        'credit': net_amount + vat_amount,
        'description': f'Payable to {supplier_name}',
    })
    return lines


def record_credit_sale(customer, total_amount, reference, tenant=None, tax_amount=None):
    """
    Record credit sale to customer.
    Called by Sales module.
    
    Accounting Entry:
    Dr. Accounts Receivable
    Cr. Sales Revenue
    """
    if tenant is None:
        tenant = get_current_tenant()
    if has_posted_journal(tenant, reference, 'Sales'):
        return None

    total_amount = Decimal(str(total_amount))
    
    return create_journal_entry(
        tenant=tenant,
        description=f"Credit sale to {customer.name}",
        reference=reference,
        entry_type='Sales',
        entries=_sale_gl_entries(
            debit_account=get_accounts_receivable_account(tenant),
            gross_amount=total_amount,
            tax_amount=tax_amount,
            tenant=tenant,
            description=f"Customer: {customer.name}",
        ),
    )


def record_cash_sale(total_amount, reference, customer_name=None, tenant=None, tax_amount=None):
    """
    Record cash sale.
    Called by Sales / POS module.
    
    Accounting Entry:
    Dr. Cash
    Cr. Sales Revenue
    """
    if tenant is None:
        tenant = get_current_tenant()
    if has_posted_journal(tenant, reference, 'Sales'):
        return None

    total_amount = Decimal(str(total_amount))
    
    description = "Cash sale"
    if customer_name:
        description += f" to {customer_name}"
    
    return create_journal_entry(
        tenant=tenant,
        description=description,
        reference=reference,
        entry_type='Sales',
        entries=_sale_gl_entries(
            debit_account=get_cash_account(tenant),
            gross_amount=total_amount,
            tax_amount=tax_amount,
            tenant=tenant,
            description=description,
        ),
    )


def record_purchase(supplier, total_amount, reference, tenant=None, tax_amount=None):
    """
    Record purchase from supplier.
    Called by Purchase module.
    
    Accounting Entry:
    Dr. Inventory Asset
    Cr. Accounts Payable
    """
    if tenant is None:
        tenant = get_current_tenant()
    if has_posted_journal(tenant, reference, 'Purchase'):
        return None

    total_amount = Decimal(str(total_amount))
    
    return create_journal_entry(
        tenant=tenant,
        description=f"Purchase from {supplier.name}",
        reference=reference,
        entry_type='Purchase',
        entries=_purchase_gl_entries(
            gross_amount=total_amount,
            tax_amount=tax_amount,
            tenant=tenant,
            description=f"Purchase from {supplier.name}",
            supplier_name=supplier.name,
        ),
    )


def record_payment_to_supplier(supplier, amount, reference, tenant=None):
    """
    Record payment to supplier.
    
    Accounting Entry:
    Dr. Accounts Payable
    Cr. Cash
    """
    if tenant is None:
        tenant = get_current_tenant()
    if has_posted_journal(tenant, reference, 'Payment'):
        return None

    amount = Decimal(str(amount))
    
    return create_journal_entry(
        tenant=tenant,
        description=f"Payment to {supplier.name}",
        reference=reference,
        entry_type='Payment',
        entries=[
            {
                'account': get_accounts_payable_account(tenant),
                'debit': amount,
                'credit': 0,
                'description': f"Payment to {supplier.name}"
            },
            {
                'account': get_cash_account(tenant),
                'debit': 0,
                'credit': amount,
                'description': f"Cash paid to {supplier.name}"
            }
        ]
    )


def record_payment_from_customer(customer, amount, reference, tenant=None):
    """
    Record payment received from customer.
    
    Accounting Entry:
    Dr. Cash
    Cr. Accounts Receivable
    """
    if tenant is None:
        tenant = get_current_tenant()
    if has_posted_journal(tenant, reference, 'Receipt'):
        return None

    amount = Decimal(str(amount))
    
    return create_journal_entry(
        tenant=tenant,
        description=f"Payment from {customer.name}",
        reference=reference,
        entry_type='Receipt',
        entries=[
            {
                'account': get_cash_account(tenant),
                'debit': amount,
                'credit': 0,
                'description': f"Payment from {customer.name}"
            },
            {
                'account': get_accounts_receivable_account(tenant),
                'debit': 0,
                'credit': amount,
                'description': f"Receivable from {customer.name}"
            }
        ]
    )


def record_sales_credit_note(customer, amount, reference, tenant=None):
    """Reverse part of a credit sale: Dr Revenue, Cr AR."""
    if tenant is None:
        tenant = get_current_tenant()
    if has_posted_journal(tenant, reference, 'Sales'):
        return None

    amount = Decimal(str(amount))
    return create_journal_entry(
        tenant=tenant,
        description=f"Sales credit note for {customer.name}",
        reference=reference,
        entry_type='Sales',
        entries=[
            {
                'account': get_sales_revenue_account(tenant),
                'debit': amount,
                'credit': 0,
                'description': f"Credit note: {reference}",
            },
            {
                'account': get_accounts_receivable_account(tenant),
                'debit': 0,
                'credit': amount,
                'description': f"Reduce receivable: {customer.name}",
            },
        ],
    )


def record_purchase_debit_note(supplier, amount, reference, tenant=None):
    """Reduce supplier payable: Dr AP, Cr Inventory."""
    if tenant is None:
        tenant = get_current_tenant()
    if has_posted_journal(tenant, reference, 'Purchase'):
        return None

    amount = Decimal(str(amount))
    return create_journal_entry(
        tenant=tenant,
        description=f"Purchase debit note for {supplier.name}",
        reference=reference,
        entry_type='Purchase',
        entries=[
            {
                'account': get_accounts_payable_account(tenant),
                'debit': amount,
                'credit': 0,
                'description': f"Debit note: {reference}",
            },
            {
                'account': get_inventory_asset_account(tenant),
                'debit': 0,
                'credit': amount,
                'description': f"Reduce inventory purchase: {supplier.name}",
            },
        ],
    )


def record_cogs(amount, reference, description, tenant=None):
    """Record cost of goods sold: Dr COGS, Cr Inventory."""
    if tenant is None:
        tenant = get_current_tenant()
    if has_posted_journal(tenant, reference, 'Sales'):
        return None

    amount = Decimal(str(amount))
    if amount <= 0:
        return None

    return create_journal_entry(
        tenant=tenant,
        description=description,
        reference=reference,
        entry_type='Sales',
        entries=[
            {
                'account': get_cost_of_goods_sold_account(tenant),
                'debit': amount,
                'credit': 0,
                'description': description,
            },
            {
                'account': get_inventory_asset_account(tenant),
                'debit': 0,
                'credit': amount,
                'description': description,
            },
        ],
    )


def reverse_cogs(amount, reference, description, tenant=None):
    """Reverse COGS on cancellation: Dr Inventory, Cr COGS."""
    if tenant is None:
        tenant = get_current_tenant()
    reversal_ref = f"{reference}-REV"
    if has_posted_journal(tenant, reversal_ref, 'Sales'):
        return None

    amount = Decimal(str(amount))
    if amount <= 0:
        return None

    return create_journal_entry(
        tenant=tenant,
        description=description,
        reference=reversal_ref,
        entry_type='Sales',
        entries=[
            {
                'account': get_inventory_asset_account(tenant),
                'debit': amount,
                'credit': 0,
                'description': description,
            },
            {
                'account': get_cost_of_goods_sold_account(tenant),
                'debit': 0,
                'credit': amount,
                'description': description,
            },
        ],
    )


def apply_entry_balances(entry):
    """Update account.balance fields when a journal entry is posted."""
    for line in entry.lines.all():
        account = line.account
        if account.type in ['Assets', 'Expense']:
            account.balance += line.debit - line.credit
        else:
            account.balance += line.credit - line.debit
        account.save()


def get_opening_balance_equity_account(tenant):
    """Equity offset account for opening balance journal entries."""
    from django.db import IntegrityError

    lookup = {'tenant': tenant, 'code': '3900'}
    defaults = {
        'name': 'Opening Balance Equity',
        'type': 'Equity',
        'sub_type': 'Capital',
        'status': 'active',
        'level': 0,
    }
    try:
        account, _ = Account._base_manager.get_or_create(defaults=defaults, **lookup)
    except IntegrityError:
        account = Account._base_manager.get(**lookup)
    return account


def create_account_opening_balance(account, amount, date, balance_side, tenant):
    """
    Post an opening balance journal entry for a new account.
    balance_side: 'debit' or 'credit' — the normal side of the opening amount.
    """
    amount = Decimal(str(amount))
    if amount <= 0:
        return None

    equity = get_opening_balance_equity_account(tenant)
    side = str(balance_side).lower()

    if side == 'debit':
        entries = [
            {'account': account, 'debit': amount, 'credit': Decimal('0')},
            {'account': equity, 'debit': Decimal('0'), 'credit': amount},
        ]
    else:
        entries = [
            {'account': account, 'debit': Decimal('0'), 'credit': amount},
            {'account': equity, 'debit': amount, 'credit': Decimal('0')},
        ]

    return create_journal_entry(
        tenant=tenant,
        description=f"Opening balance for {account.code} - {account.name}",
        entries=entries,
        reference=f"OB-{account.code}",
        date=date,
    )
