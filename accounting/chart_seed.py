"""
Default chart of accounts for new tenants.
Codes align with accounting.services get_or_create_account helpers.
"""

from accounting.models import Account

DEFAULT_CHART_OF_ACCOUNTS = [
    # Assets
    {'code': '1000', 'name': 'Cash', 'type': 'Assets', 'sub_type': 'Cash',
     'description': 'Petty cash and cash on hand'},
    {'code': '1010', 'name': 'Bank', 'type': 'Assets', 'sub_type': 'Bank',
     'description': 'Bank accounts — link when creating bank accounts'},
    {'code': '1100', 'name': 'Accounts Receivable', 'type': 'Assets', 'sub_type': 'Receivable',
     'description': 'Customer outstanding balances'},
    {'code': '1200', 'name': 'Inventory', 'type': 'Assets', 'sub_type': 'Current Asset',
     'description': 'Stock and goods for sale'},
    {'code': '1300', 'name': 'Prepaid Expenses', 'type': 'Assets', 'sub_type': 'Current Asset',
     'description': 'Expenses paid in advance'},
    {'code': '1500', 'name': 'Fixed Assets', 'type': 'Assets', 'sub_type': 'Fixed Asset',
     'description': 'Property, equipment, and long-term assets'},
    # Liabilities
    {'code': '2000', 'name': 'Accounts Payable', 'type': 'Liabilities', 'sub_type': 'Payable',
     'description': 'Amounts owed to suppliers'},
    {'code': '2100', 'name': 'Wages Payable', 'type': 'Liabilities', 'sub_type': 'Payable',
     'description': 'Unpaid wages and salaries'},
    {'code': '2200', 'name': 'VAT Payable', 'type': 'Liabilities', 'sub_type': 'Tax',
     'description': 'Output VAT collected — link in tax rules'},
    {'code': '2300', 'name': 'TDS Payable', 'type': 'Liabilities', 'sub_type': 'Tax',
     'description': 'Tax deducted at source payable to IRD'},
    # Equity
    {'code': '3000', 'name': "Owner's Capital", 'type': 'Equity', 'sub_type': 'Capital',
     'description': 'Owner investment in the business'},
    {'code': '3100', 'name': 'Retained Earnings', 'type': 'Equity', 'sub_type': 'Retained Earnings',
     'description': 'Accumulated profits'},
    # Income
    {'code': '4000', 'name': 'Sales Revenue', 'type': 'Income', 'sub_type': 'Revenue',
     'description': 'Revenue from sales of goods and services'},
    {'code': '4100', 'name': 'Other Income', 'type': 'Income', 'sub_type': 'Other Income',
     'description': 'Interest, discounts, and miscellaneous income'},
    # Expenses
    {'code': '5000', 'name': 'Cost of Goods Sold', 'type': 'Expense', 'sub_type': 'COGS',
     'description': 'Direct cost of inventory sold'},
    {'code': '5100', 'name': 'Construction Expenses', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Site and construction project costs'},
    {'code': '5200', 'name': 'Labor Expenses', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Direct labor and subcontractor costs'},
    {'code': '5300', 'name': 'Equipment Expenses', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Equipment rental and usage costs'},
    {'code': '5400', 'name': 'Administrative Expenses', 'type': 'Expense', 'sub_type': 'Administrative',
     'description': 'Office, utilities, and general admin'},
    {'code': '5500', 'name': 'Payroll Expenses', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Salaries and employee benefits'},
]


def seed_default_chart_of_accounts(tenant):
    """
    Create the standard chart of accounts for a tenant.
    Idempotent — existing accounts (matched by code) are skipped.
    Uses _base_manager so lookup is not affected by TenantManager thread-local filtering.
    """
    from django.db import transaction, IntegrityError

    created = []
    skipped = []

    with transaction.atomic():
        for spec in DEFAULT_CHART_OF_ACCOUNTS:
            lookup = {'tenant': tenant, 'code': spec['code']}
            defaults = {
                'name': spec['name'],
                'type': spec['type'],
                'sub_type': spec['sub_type'],
                'description': spec.get('description', ''),
                'status': 'active',
                'level': 0,
            }
            try:
                account, was_created = Account._base_manager.get_or_create(
                    defaults=defaults,
                    **lookup,
                )
            except IntegrityError:
                account = Account._base_manager.get(**lookup)
                was_created = False

            if was_created:
                created.append(account)
            else:
                skipped.append(account)

    return {
        'created': len(created),
        'skipped': len(skipped),
        'total': len(DEFAULT_CHART_OF_ACCOUNTS),
        'accounts': created,
    }
