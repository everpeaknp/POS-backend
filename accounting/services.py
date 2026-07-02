"""
Accounting Services - Core Layer
Provides accounting operations used by all industry modules.
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from accounting.models import JournalEntry, JournalLine, Account
from tenants.middleware import get_current_tenant


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
        
        # Generate entry number
        import time
        entry_number = f"JE-{int(time.time() * 1000)}"
        
        # Create journal entry
        journal_entry = JournalEntry.objects.create(
            tenant=tenant,
            entry_number=entry_number,
            date=date or timezone.now().date(),
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
        '2100': 'Payable',  # Wages Payable
        '4000': 'Revenue',  # Sales Revenue
        '5000': 'COGS',  # Cost of Goods Sold
        '5100': 'Operating',  # Construction Expenses
        '5200': 'Operating',  # Labor Expenses
        '5300': 'Operating',  # Equipment Expenses
    }
    
    account, created = Account.objects.get_or_create(
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
    """Get or create Wages Payable account (Liability)"""
    return get_or_create_account('2100', 'Wages Payable', 'liability', tenant)


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
    
    total_cost = Decimal(str(quantity)) * Decimal(str(unit_cost))
    
    # Get site's cost center account or use default construction expense
    cost_center = getattr(site, 'cost_center_account', None) or get_construction_expense_account(tenant)
    
    return create_journal_entry(
        tenant=tenant,
        description=f"Material consumption: {product.name} at {site.name}",
        reference=reference,
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


def record_labor_wage(site, worker, wage_amount, date, reference):
    """
    Record labor wage expense for construction site.
    Called by Construction module.
    
    Accounting Entry:
    Dr. Labor Expense (Site Cost Center)
    Cr. Wages Payable
    """
    tenant = get_current_tenant()
    wage_amount = Decimal(str(wage_amount))
    
    # Get site's cost center account or use default labor expense
    cost_center = getattr(site, 'cost_center_account', None) or get_labor_expense_account()
    
    return create_journal_entry(
        tenant=tenant,
        description=f"Labor wage: {worker.name} at {site.name}",
        reference=reference,
        date=date,
        entries=[
            {
                'account': cost_center,
                'debit': wage_amount,
                'credit': 0,
                'description': f"Worker: {worker.name} ({worker.category})"
            },
            {
                'account': get_wages_payable_account(),
                'debit': 0,
                'credit': wage_amount,
                'description': f"Wage payable to {worker.name}"
            }
        ]
    )


def record_credit_sale(customer, total_amount, reference, tenant=None):
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
        entries=[
            {
                'account': get_accounts_receivable_account(tenant),
                'debit': total_amount,
                'credit': 0,
                'description': f"Customer: {customer.name}"
            },
            {
                'account': get_sales_revenue_account(tenant),
                'debit': 0,
                'credit': total_amount,
                'description': f"Sale to {customer.name}"
            }
        ]
    )


def record_cash_sale(total_amount, reference, customer_name=None, tenant=None):
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
        entries=[
            {
                'account': get_cash_account(tenant),
                'debit': total_amount,
                'credit': 0,
                'description': description
            },
            {
                'account': get_sales_revenue_account(tenant),
                'debit': 0,
                'credit': total_amount,
                'description': description
            }
        ]
    )


def record_purchase(supplier, total_amount, reference, tenant=None):
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
        entries=[
            {
                'account': get_inventory_asset_account(tenant),
                'debit': total_amount,
                'credit': 0,
                'description': f"Supplier: {supplier.name}"
            },
            {
                'account': get_accounts_payable_account(tenant),
                'debit': 0,
                'credit': total_amount,
                'description': f"Payable to {supplier.name}"
            }
        ]
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
    account, _ = Account.objects.get_or_create(
        tenant=tenant,
        code='3900',
        defaults={
            'name': 'Opening Balance Equity',
            'type': 'Equity',
            'sub_type': 'Capital',
            'status': 'active',
            'level': 0,
        }
    )
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

    entry = create_journal_entry(
        tenant=tenant,
        description=f"Opening balance for {account.code} - {account.name}",
        entries=entries,
        reference=f"OB-{account.code}",
        date=date,
    )
    apply_entry_balances(entry)
    return entry
