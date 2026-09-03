"""
Default chart of accounts for new tenants.
Codes align with accounting.services get_or_create_account helpers.
"""

from accounting.models import Account

DEFAULT_CHART_OF_ACCOUNTS = [
    # Assets
    {'code': '1000', 'name': 'Cash', 'type': 'Assets', 'sub_type': 'Cash',
     'description': 'Petty cash and cash on hand'},
    {'code': '1005', 'name': 'Petty Cash', 'type': 'Assets', 'sub_type': 'Cash',
     'description': 'Small expenses and cash drawer float'},
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
    {'code': '2200', 'name': 'Salary Payable', 'type': 'Liabilities', 'sub_type': 'Payable',
     'description': 'Unpaid salaries owed to HR employees'},
    {'code': '2250', 'name': 'VAT Payable', 'type': 'Liabilities', 'sub_type': 'Tax',
     'description': 'Output VAT collected'},
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


PERSONAL_CHART_OF_ACCOUNTS = [
    # Assets
    {'code': '1000', 'name': 'Cash', 'type': 'Assets', 'sub_type': 'Cash',
     'description': 'Cash on hand and wallet'},
    {'code': '1010', 'name': 'Checking Account', 'type': 'Assets', 'sub_type': 'Bank',
     'description': 'Primary checking/current account'},
    {'code': '1020', 'name': 'Savings Account', 'type': 'Assets', 'sub_type': 'Bank',
     'description': 'Savings and deposit accounts'},
    {'code': '1030', 'name': 'Investment Account', 'type': 'Assets', 'sub_type': 'Current Asset',
     'description': 'Brokerage and investment accounts'},
    {'code': '1500', 'name': 'Fixed Assets', 'type': 'Assets', 'sub_type': 'Fixed Asset',
     'description': 'Property, vehicle, and long-term personal assets'},
    # Liabilities
    {'code': '2100', 'name': 'Credit Card', 'type': 'Liabilities', 'sub_type': 'Payable',
     'description': 'Credit card balances'},
    {'code': '2200', 'name': 'Personal Loan', 'type': 'Liabilities', 'sub_type': 'Payable',
     'description': 'Personal loans and borrowings'},
    {'code': '2300', 'name': 'Home Loan', 'type': 'Liabilities', 'sub_type': 'Payable',
     'description': 'Mortgage and home loans'},
    {'code': '2400', 'name': 'Car Loan', 'type': 'Liabilities', 'sub_type': 'Payable',
     'description': 'Vehicle financing'},
    {'code': '2500', 'name': 'Student Loan', 'type': 'Liabilities', 'sub_type': 'Payable',
     'description': 'Education loans'},
    # Equity
    {'code': '3000', 'name': 'Opening Balance', 'type': 'Equity', 'sub_type': 'Capital',
     'description': 'Initial net worth when starting to track finances'},
    {'code': '3100', 'name': 'Retained Earnings', 'type': 'Equity', 'sub_type': 'Retained Earnings',
     'description': 'Accumulated savings and net worth changes'},
    # Income
    {'code': '4000', 'name': 'Salary Income', 'type': 'Income', 'sub_type': 'Revenue',
     'description': 'Primary employment salary'},
    {'code': '4100', 'name': 'Freelance Income', 'type': 'Income', 'sub_type': 'Revenue',
     'description': 'Freelance and contract work'},
    {'code': '4200', 'name': 'Investment Income', 'type': 'Income', 'sub_type': 'Other Income',
     'description': 'Interest, dividends, and capital gains'},
    {'code': '4300', 'name': 'Rental Income', 'type': 'Income', 'sub_type': 'Other Income',
     'description': 'Property rental income'},
    {'code': '4400', 'name': 'Other Income', 'type': 'Income', 'sub_type': 'Other Income',
     'description': 'Gifts, bonuses, and miscellaneous income'},
    # Expenses
    {'code': '5000', 'name': 'Groceries', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Food and household supplies'},
    {'code': '5100', 'name': 'Rent', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Housing rent or mortgage payment'},
    {'code': '5200', 'name': 'Utilities', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Electricity, water, gas, internet'},
    {'code': '5300', 'name': 'Transportation', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Fuel, public transport, vehicle maintenance'},
    {'code': '5400', 'name': 'Dining & Entertainment', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Restaurants, movies, recreation'},
    {'code': '5500', 'name': 'Healthcare', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Medical expenses, insurance, medications'},
    {'code': '5600', 'name': 'Education', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Tuition, courses, books'},
    {'code': '5700', 'name': 'Insurance', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Health, life, vehicle insurance premiums'},
    {'code': '5800', 'name': 'Shopping', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Clothing, electronics, personal items'},
    {'code': '5900', 'name': 'Personal Care', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Haircuts, cosmetics, gym memberships'},
]


KIRANA_CHART_OF_ACCOUNTS = [
    # Assets
    {'code': '1000', 'name': 'Cash in Hand', 'type': 'Assets', 'sub_type': 'Cash',
     'description': 'Shop cash drawer and cash on hand'},
    {'code': '1010', 'name': 'Bank Account', 'type': 'Assets', 'sub_type': 'Bank',
     'description': 'Shop bank account'},
    {'code': '1200', 'name': 'Stock/Inventory', 'type': 'Assets', 'sub_type': 'Current Asset',
     'description': 'Goods available for sale'},
    # Liabilities
    {'code': '2000', 'name': 'Udhaaro / Accounts Payable', 'type': 'Liabilities', 'sub_type': 'Payable',
     'description': 'Amounts owed to suppliers and credit given to customers'},
    # Equity
    {'code': '3000', 'name': "Owner's Capital", 'type': 'Equity', 'sub_type': 'Capital',
     'description': 'Initial investment in the shop'},
    {'code': '3100', 'name': 'Retained Earnings', 'type': 'Equity', 'sub_type': 'Retained Earnings',
     'description': 'Accumulated profits'},
    # Income
    {'code': '4000', 'name': 'Sales', 'type': 'Income', 'sub_type': 'Revenue',
     'description': 'Revenue from sales of goods'},
    # Expenses
    {'code': '5000', 'name': 'Purchases / Cost of Goods', 'type': 'Expense', 'sub_type': 'COGS',
     'description': 'Cost of goods purchased for resale'},
    {'code': '5100', 'name': 'Utilities', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Electricity, water, rent for shop'},
    {'code': '5200', 'name': 'Other Expenses', 'type': 'Expense', 'sub_type': 'Operating',
     'description': 'Miscellaneous operating expenses'},
]


def seed_default_chart_of_accounts(tenant):
    """
    Create the standard chart of accounts for a business tenant.
    Idempotent — existing accounts (matched by code) are skipped.
    Uses _base_manager so lookup is not affected by TenantManager thread-local filtering.
    """
    from django.db import transaction, IntegrityError
    from accounting.models import PaymentMethod

    created = []
    skipped = []
    cash_account_obj = None

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
                # Auto-create default Cash payment method when Cash account (1000) is created
                if spec['code'] == '1000':
                    cash_account_obj = account
            else:
                skipped.append(account)
                # Track existing Cash account for PaymentMethod creation
                if spec['code'] == '1000':
                    cash_account_obj = account
        
        # Create default Payment Methods if Cash account exists
        if cash_account_obj:
            default_payment_methods = [
                ('Cash', 'cash'),
                ('Bank', 'bank_transfer'),
                ('Fonepay', 'digital_wallet'),
                ('Credit Card', 'card'),
            ]
            for name, method_type in default_payment_methods:
                PaymentMethod._base_manager.get_or_create(
                    tenant=tenant,
                    name=name,
                    defaults={
                        'method_type': method_type,
                        'linked_account': cash_account_obj,
                        'is_active': True,
                        'is_system_default': True,
                    }
                )

    return {
        'created': len(created),
        'skipped': len(skipped),
        'total': len(DEFAULT_CHART_OF_ACCOUNTS),
        'accounts': created,
    }


def seed_personal_chart_of_accounts(tenant):
    """
    Create the personal finance chart of accounts for a personal tenant.
    Idempotent — existing accounts (matched by code) are skipped.
    Uses _base_manager so lookup is not affected by TenantManager thread-local filtering.
    """
    from django.db import transaction, IntegrityError
    from accounting.models import PaymentMethod

    created = []
    skipped = []
    cash_account_obj = None

    with transaction.atomic():
        for spec in PERSONAL_CHART_OF_ACCOUNTS:
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
                if spec['code'] == '1000':
                    cash_account_obj = account
            else:
                skipped.append(account)
                if spec['code'] == '1000':
                    cash_account_obj = account
        
        # Create default Cash PaymentMethod
        if cash_account_obj:
            PaymentMethod._base_manager.get_or_create(
                tenant=tenant,
                name='Cash',
                defaults={
                    'method_type': 'cash',
                    'linked_account': cash_account_obj,
                    'is_active': True,
                    'is_system_default': True,
                }
            )

    return {
        'created': len(created),
        'skipped': len(skipped),
        'total': len(PERSONAL_CHART_OF_ACCOUNTS),
        'accounts': created,
    }


def seed_kirana_chart_of_accounts(tenant):
    """
    Create the simplified chart of accounts for a kirana/small retail tenant.
    Idempotent — existing accounts (matched by code) are skipped.
    Uses _base_manager so lookup is not affected by TenantManager thread-local filtering.
    """
    from django.db import transaction, IntegrityError
    from accounting.models import PaymentMethod

    created = []
    skipped = []
    cash_account_obj = None

    with transaction.atomic():
        for spec in KIRANA_CHART_OF_ACCOUNTS:
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
                if spec['code'] == '1000':
                    cash_account_obj = account
            else:
                skipped.append(account)
                if spec['code'] == '1000':
                    cash_account_obj = account
        
        # Create default Cash PaymentMethod
        if cash_account_obj:
            PaymentMethod._base_manager.get_or_create(
                tenant=tenant,
                name='Cash',
                defaults={
                    'method_type': 'cash',
                    'linked_account': cash_account_obj,
                    'is_active': True,
                    'is_system_default': True,
                }
            )

    return {
        'created': len(created),
        'skipped': len(skipped),
        'total': len(KIRANA_CHART_OF_ACCOUNTS),
        'accounts': created,
    }


def seed_chart_of_accounts_for_tenant(tenant):
    """
    Seed the appropriate chart of accounts based on tenant business_type.
    
    Args:
        tenant: Tenant instance
    
    Returns:
        dict: Result of seeding operation
    """
    if tenant.business_type == 'personal':
        return seed_personal_chart_of_accounts(tenant)
    elif tenant.business_type == 'kirana':
        return seed_kirana_chart_of_accounts(tenant)
    else:
        return seed_default_chart_of_accounts(tenant)
