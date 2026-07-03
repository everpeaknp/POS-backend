"""Platform-wide constants aligned with the customer app module picker."""

AVAILABLE_MODULES = [
    ('accounting', 'Accounting'),
    ('inventory', 'Inventory Management'),
    ('sales', 'Sales & Billing'),
    ('purchase', 'Purchase Management'),
    ('reports', 'Reports & Analytics'),
    ('settings', 'Settings'),
    ('pos', 'Point of Sale (POS)'),
    ('hr', 'HR & Payroll'),
    ('construction', 'Construction Management'),
    ('hardware', 'Hardware Business'),
    ('dashboard', 'Dashboard'),
]

DEFAULT_FREE_MODULES = [
    'accounting', 'inventory', 'sales', 'purchase', 'reports', 'settings', 'dashboard',
]
