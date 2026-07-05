"""
Build unified main-dashboard payloads keyed by enabled tenant modules.
"""
from decimal import Decimal

from django.db.models import Avg, Count, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from users.dynamic_permissions import tenant_has_active_module

OVERVIEW_MODULE_IDS = [
    'sales',
    'purchase',
    'inventory',
    'accounting',
    'hr',
    'pos',
    'construction',
    'hardware',
    'reports',
]

MODULE_META = {
    'sales': {'title': 'Sales & Billing', 'href': '/dashboard/sales'},
    'purchase': {'title': 'Purchase Management', 'href': '/dashboard/purchase'},
    'inventory': {'title': 'Inventory Management', 'href': '/dashboard/inventory'},
    'accounting': {'title': 'Accounting', 'href': '/dashboard/accounting'},
    'hr': {'title': 'HR & Payroll', 'href': '/dashboard/hr'},
    'pos': {'title': 'Point of Sale', 'href': '/dashboard/pos'},
    'construction': {'title': 'Construction Management', 'href': '/dashboard/construction'},
    'hardware': {'title': 'Hardware Business', 'href': '/dashboard/hardware'},
    'reports': {'title': 'Reports & Analytics', 'href': '/dashboard/reports'},
}


def _enabled_overview_modules(tenant):
    if not tenant:
        return []
    active = getattr(tenant, 'active_modules', None) or []
    enabled = []
    for module_id in OVERVIEW_MODULE_IDS:
        if tenant_has_active_module(tenant, module_id):
            enabled.append(module_id)
    # Fallback: if tenant has no module list, show catalog defaults
    if not active:
        return OVERVIEW_MODULE_IDS[:6]
    return enabled


def _period_ranges(period, now):
    from datetime import timedelta

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == 'today':
        start_date = today_start
        previous_start = start_date - timedelta(days=1)
        previous_end = start_date
    elif period == 'week':
        start_date = today_start - timedelta(days=now.weekday())
        previous_start = start_date - timedelta(days=7)
        previous_end = start_date
    elif period == 'year':
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        previous_start = start_date.replace(year=start_date.year - 1)
        previous_end = start_date
    else:
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start_date.month == 1:
            previous_start = start_date.replace(year=start_date.year - 1, month=12)
        else:
            previous_start = start_date.replace(month=start_date.month - 1)
        previous_end = start_date

    return start_date, previous_start, previous_end, today_start


def _pct_change(current, previous):
    if not previous:
        return 0
    return round(((current - previous) / previous) * 100, 1)


def _build_sales_module(tenant, period, start_date, previous_start, previous_end, now, today_start):
    from datetime import timedelta

    from inventory.models import Product
    from sales.models import Customer, SalesOrder, SalesOrderLine

    current_orders = SalesOrder.objects.filter(tenant=tenant, date__gte=start_date)
    current_revenue = current_orders.aggregate(total=Sum('total'))['total'] or Decimal('0')
    current_order_count = current_orders.count()

    previous_orders = SalesOrder.objects.filter(
        tenant=tenant,
        date__gte=previous_start,
        date__lt=previous_end,
    )
    previous_revenue = previous_orders.aggregate(total=Sum('total'))['total'] or Decimal('0')
    previous_order_count = previous_orders.count()

    total_customers = Customer.objects.filter(tenant=tenant).count()
    new_customers = Customer.objects.filter(tenant=tenant, created_at__gte=start_date).count()
    previous_new_customers = Customer.objects.filter(
        tenant=tenant,
        created_at__gte=previous_start,
        created_at__lt=previous_end,
    ).count()

    total_products = Product.objects.filter(tenant=tenant).count()

    revenue_data = []
    if period == 'today':
        for hour in range(0, 24, 3):
            hour_start = today_start + timedelta(hours=hour)
            hour_end = hour_start + timedelta(hours=3)
            revenue = SalesOrder.objects.filter(
                tenant=tenant,
                date__gte=hour_start,
                date__lt=hour_end,
            ).aggregate(total=Sum('total'))['total'] or Decimal('0')
            time_label = f"{hour % 12 if hour % 12 != 0 else 12} {'AM' if hour < 12 else 'PM'}"
            revenue_data.append({'time': time_label, 'value': float(revenue)})
    elif period == 'week':
        for day in range(7):
            day_start = start_date + timedelta(days=day)
            day_end = day_start + timedelta(days=1)
            revenue = SalesOrder.objects.filter(
                tenant=tenant,
                date__gte=day_start,
                date__lt=day_end,
            ).aggregate(total=Sum('total'))['total'] or Decimal('0')
            revenue_data.append({'time': day_start.strftime('%a'), 'value': float(revenue)})
    elif period == 'year':
        for month in range(1, 13):
            month_start = start_date.replace(month=month)
            if month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1)
            else:
                month_end = month_start.replace(month=month + 1)
            revenue = SalesOrder.objects.filter(
                tenant=tenant,
                date__gte=month_start,
                date__lt=month_end,
            ).aggregate(total=Sum('total'))['total'] or Decimal('0')
            revenue_data.append({'time': month_start.strftime('%b'), 'value': float(revenue)})
    else:
        week_num = 1
        current = start_date
        while current < now:
            week_end = min(current + timedelta(days=7), now)
            revenue = SalesOrder.objects.filter(
                tenant=tenant,
                date__gte=current,
                date__lt=week_end,
            ).aggregate(total=Sum('total'))['total'] or Decimal('0')
            revenue_data.append({'time': f"Week {week_num}", 'value': float(revenue)})
            current = week_end
            week_num += 1

    recent_orders = SalesOrder.objects.filter(tenant=tenant).select_related('customer').order_by('-date')[:5]
    recent_orders_data = [
        {
            'primary': order.order_number,
            'secondary': order.customer.name if order.customer else 'Walk-in Customer',
            'meta': f"Rs. {order.total:,.0f}",
            'status': order.status,
        }
        for order in recent_orders
    ]

    top_products = SalesOrderLine.objects.filter(
        sales_order__tenant=tenant,
        sales_order__date__gte=start_date,
    ).values('product__name').annotate(total_qty=Sum('quantity')).order_by('-total_qty')[:5]

    top_products_data = [
        {
            'primary': item['product__name'],
            'meta': f"{int(item['total_qty'])} sold",
        }
        for item in top_products
    ]

    meta = MODULE_META['sales']
    return {
        'id': 'sales',
        'title': meta['title'],
        'href': meta['href'],
        'stats': [
            {
                'label': 'Revenue',
                'value': f"Rs. {current_revenue:,.0f}",
                'change': _pct_change(float(current_revenue), float(previous_revenue)),
            },
            {
                'label': 'Orders',
                'value': str(current_order_count),
                'change': _pct_change(current_order_count, previous_order_count),
            },
            {
                'label': 'Customers',
                'value': str(total_customers),
                'change': _pct_change(new_customers, previous_new_customers),
            },
            {
                'label': 'Products',
                'value': str(total_products),
            },
        ],
        'chart': {'data': revenue_data},
        'lists': [
            {'title': 'Recent Orders', 'items': recent_orders_data},
            {'title': 'Top Products', 'items': top_products_data},
        ],
    }


def _build_purchase_module(tenant, start_date, previous_start, previous_end):
    from purchase.models import PurchaseInvoice, PurchaseOrder, PurchaseRequest, Supplier

    pending_requests = PurchaseRequest.objects.filter(tenant=tenant, status='Pending Approval').count()
    open_orders = PurchaseOrder.objects.filter(
        tenant=tenant,
        status__in=['Draft', 'Sent', 'Partially Received'],
    ).count()
    supplier_count = Supplier.objects.filter(tenant=tenant).count()

    current_spend = PurchaseInvoice.objects.filter(
        tenant=tenant,
        date__gte=start_date,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    previous_spend = PurchaseInvoice.objects.filter(
        tenant=tenant,
        date__gte=previous_start,
        date__lt=previous_end,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    recent_orders = PurchaseOrder.objects.filter(tenant=tenant).select_related('supplier').order_by('-date')[:5]
    recent_items = [
        {
            'primary': order.po_number,
            'secondary': order.supplier.name if order.supplier else 'No supplier',
            'meta': f"Rs. {order.total:,.0f}" if order.total else '',
            'status': order.status,
        }
        for order in recent_orders
    ]

    meta = MODULE_META['purchase']
    return {
        'id': 'purchase',
        'title': meta['title'],
        'href': meta['href'],
        'stats': [
            {'label': 'Pending Requests', 'value': str(pending_requests)},
            {'label': 'Open Orders', 'value': str(open_orders)},
            {'label': 'Suppliers', 'value': str(supplier_count)},
            {
                'label': 'Period Spend',
                'value': f"Rs. {current_spend:,.0f}",
                'change': _pct_change(float(current_spend), float(previous_spend)),
            },
        ],
        'lists': [{'title': 'Recent Purchase Orders', 'items': recent_items}],
    }


def _build_inventory_module(tenant):
    from inventory.models import Product

    products = Product.objects.filter(tenant=tenant)
    total_skus = products.count()

    annotated = products.annotate(
        total_stock=Coalesce(Sum('stocks__quantity'), Value(Decimal('0.00')))
    )
    low_stock = annotated.filter(
        total_stock__lte=F('reorder_level'),
        total_stock__gt=0,
    ).count()
    out_of_stock = annotated.filter(total_stock=0).count()
    in_stock = annotated.filter(total_stock__gt=F('reorder_level')).count()

    low_stock_products = annotated.filter(total_stock__lt=F('reorder_level')).order_by('total_stock')[:5]
    low_stock_items = [
        {
            'primary': product.name,
            'secondary': product.sku or '',
            'meta': f"{float(product.total_stock)} / {float(product.reorder_level)}",
            'status': 'critical' if product.total_stock == 0 else 'low',
        }
        for product in low_stock_products
    ]

    meta = MODULE_META['inventory']
    return {
        'id': 'inventory',
        'title': meta['title'],
        'href': meta['href'],
        'stats': [
            {'label': 'Total SKUs', 'value': str(total_skus)},
            {'label': 'In Stock', 'value': str(in_stock)},
            {'label': 'Low Stock', 'value': str(low_stock)},
            {'label': 'Out of Stock', 'value': str(out_of_stock)},
        ],
        'tiles': [
            {'label': 'In Stock', 'value': str(in_stock), 'tone': 'success'},
            {'label': 'Low Stock', 'value': str(low_stock), 'tone': 'warning'},
            {'label': 'Out of Stock', 'value': str(out_of_stock), 'tone': 'danger'},
            {'label': 'Total SKUs', 'value': str(total_skus), 'tone': 'info'},
        ],
        'lists': [{'title': 'Low Stock Alerts', 'items': low_stock_items}],
    }


def _build_accounting_module(tenant):
    from accounting.models import Account, JournalEntry
    from sales.models import Customer

    journal_count = JournalEntry.objects.filter(tenant=tenant).count()
    accounts_count = Account.objects.filter(tenant=tenant).count()
    receivables = Customer.objects.filter(tenant=tenant).aggregate(
        total=Coalesce(Sum('current_balance'), Value(Decimal('0.00')))
    )['total'] or Decimal('0')

    try:
        from purchase.models import Supplier

        payables = Supplier.objects.filter(tenant=tenant).aggregate(
            total=Coalesce(Sum('current_balance'), Value(Decimal('0.00')))
        )['total'] or Decimal('0')
    except Exception:
        payables = Decimal('0')

    recent_entries = JournalEntry.objects.filter(tenant=tenant).order_by('-date')[:5]
    recent_items = [
        {
            'primary': entry.entry_number or str(entry.id),
            'secondary': entry.description or 'Journal entry',
            'meta': entry.date.strftime('%Y-%m-%d') if entry.date else '',
            'status': entry.status if hasattr(entry, 'status') else '',
        }
        for entry in recent_entries
    ]

    meta = MODULE_META['accounting']
    return {
        'id': 'accounting',
        'title': meta['title'],
        'href': meta['href'],
        'stats': [
            {'label': 'Journal Entries', 'value': str(journal_count)},
            {'label': 'Accounts', 'value': str(accounts_count)},
            {'label': 'Receivables', 'value': f"Rs. {receivables:,.0f}"},
            {'label': 'Payables', 'value': f"Rs. {payables:,.0f}"},
        ],
        'lists': [{'title': 'Recent Journal Entries', 'items': recent_items}],
    }


def _build_hr_module(tenant):
    from hr.models import Department, Employee

    employees = Employee.objects.filter(tenant=tenant)
    active_count = employees.filter(status='active').count()
    total_count = employees.count()
    department_count = Department.objects.filter(tenant=tenant).count()

    total_salary = employees.filter(status='active').aggregate(
        total=Coalesce(Sum('basic_salary'), Value(Decimal('0.00')))
    )['total'] or Decimal('0')

    recent_employees = employees.filter(status='active').order_by('-join_date')[:5]
    recent_items = [
        {
            'primary': emp.name,
            'secondary': emp.designation or emp.department.name if emp.department else '',
            'meta': emp.join_date.strftime('%Y-%m-%d') if emp.join_date else '',
        }
        for emp in recent_employees
    ]

    meta = MODULE_META['hr']
    return {
        'id': 'hr',
        'title': meta['title'],
        'href': meta['href'],
        'stats': [
            {'label': 'Total Employees', 'value': str(total_count)},
            {'label': 'Active', 'value': str(active_count)},
            {'label': 'Departments', 'value': str(department_count)},
            {'label': 'Monthly Payroll', 'value': f"Rs. {total_salary:,.0f}"},
        ],
        'lists': [{'title': 'Recent Employees', 'items': recent_items}],
    }


def _build_pos_module(tenant, today_start):
    from pos.models import POSSession, POSTransaction

    open_sessions = POSSession.objects.filter(tenant=tenant, status='open').count()
    today_tx = POSTransaction.objects.filter(tenant=tenant, date__gte=today_start).count()
    today_revenue = POSTransaction.objects.filter(
        tenant=tenant,
        date__gte=today_start,
    ).aggregate(total=Coalesce(Sum('total'), Value(Decimal('0.00'))))['total'] or Decimal('0')

    recent_tx = POSTransaction.objects.filter(tenant=tenant).order_by('-date')[:5]
    recent_items = [
        {
            'primary': tx.transaction_number or str(tx.id),
            'secondary': tx.customer_name or 'Walk-in',
            'meta': f"Rs. {tx.total:,.0f}",
            'status': tx.status if hasattr(tx, 'status') else '',
        }
        for tx in recent_tx
    ]

    meta = MODULE_META['pos']
    return {
        'id': 'pos',
        'title': meta['title'],
        'href': meta['href'],
        'stats': [
            {'label': 'Open Sessions', 'value': str(open_sessions)},
            {'label': "Today's Transactions", 'value': str(today_tx)},
            {'label': "Today's Sales", 'value': f"Rs. {today_revenue:,.0f}"},
        ],
        'lists': [{'title': 'Recent Transactions', 'items': recent_items}],
    }


def _build_construction_module(tenant):
    try:
        from construction.models import Attendance, Site

        active_sites = Site.objects.filter(tenant=tenant, status='active').count()
        total_sites = Site.objects.filter(tenant=tenant).count()
        workers_today = Attendance.objects.filter(
            tenant=tenant,
            date=timezone.now().date(),
        ).count()

        recent_sites = Site.objects.filter(tenant=tenant).order_by('-created_at')[:5]
        recent_items = [
            {
                'primary': site.name,
                'secondary': site.location or '',
                'meta': site.status,
            }
            for site in recent_sites
        ]
    except Exception:
        active_sites = total_sites = workers_today = 0
        recent_items = []

    meta = MODULE_META['construction']
    return {
        'id': 'construction',
        'title': meta['title'],
        'href': meta['href'],
        'stats': [
            {'label': 'Active Sites', 'value': str(active_sites)},
            {'label': 'Total Sites', 'value': str(total_sites)},
            {'label': 'Workers Today', 'value': str(workers_today)},
        ],
        'lists': [{'title': 'Sites', 'items': recent_items}],
    }


def _build_hardware_module(tenant):
    from sales.models import Customer, SalesOrder

    credit_customers = Customer.objects.filter(tenant=tenant, current_balance__gt=0).count()
    outstanding = Customer.objects.filter(tenant=tenant).aggregate(
        total=Coalesce(Sum('current_balance'), Value(Decimal('0.00')))
    )['total'] or Decimal('0')
    open_orders = SalesOrder.objects.filter(
        tenant=tenant,
        status__in=['Draft', 'Confirmed', 'Pending', 'draft', 'confirmed', 'pending'],
    ).count()

    meta = MODULE_META['hardware']
    return {
        'id': 'hardware',
        'title': meta['title'],
        'href': meta['href'],
        'stats': [
            {'label': 'Credit Customers', 'value': str(credit_customers)},
            {'label': 'Outstanding Credit', 'value': f"Rs. {outstanding:,.0f}"},
            {'label': 'Open Orders', 'value': str(open_orders)},
        ],
    }


def _build_reports_module(tenant):
    meta = MODULE_META['reports']
    return {
        'id': 'reports',
        'title': meta['title'],
        'href': meta['href'],
        'stats': [
            {'label': 'Sales Reports', 'value': 'Available'},
            {'label': 'Financial Reports', 'value': 'Available'},
            {'label': 'Custom Reports', 'value': 'Available'},
        ],
        'lists': [
            {
                'title': 'Quick links',
                'items': [
                    {'primary': 'Sales Report', 'secondary': '/dashboard/reports/sales'},
                    {'primary': 'Financial Report', 'secondary': '/dashboard/reports/financial'},
                    {'primary': 'Inventory Report', 'secondary': '/dashboard/reports/inventory'},
                ],
            }
        ],
    }


def build_main_dashboard_response(tenant, period='month'):
    now = timezone.now()
    start_date, previous_start, previous_end, today_start = _period_ranges(period, now)
    enabled = _enabled_overview_modules(tenant)

    if not tenant:
        return {
            'activeModules': [],
            'period': period,
            'modules': [],
        }

    modules = []
    builders = {
        'sales': lambda: _build_sales_module(
            tenant, period, start_date, previous_start, previous_end, now, today_start
        ),
        'purchase': lambda: _build_purchase_module(tenant, start_date, previous_start, previous_end),
        'inventory': lambda: _build_inventory_module(tenant),
        'accounting': lambda: _build_accounting_module(tenant),
        'hr': lambda: _build_hr_module(tenant),
        'pos': lambda: _build_pos_module(tenant, today_start),
        'construction': lambda: _build_construction_module(tenant),
        'hardware': lambda: _build_hardware_module(tenant),
        'reports': lambda: _build_reports_module(tenant),
    }

    for module_id in enabled:
        builder = builders.get(module_id)
        if not builder:
            continue
        try:
            modules.append(builder())
        except Exception:
            meta = MODULE_META.get(module_id, {'title': module_id.title(), 'href': f'/dashboard/{module_id}'})
            modules.append({
                'id': module_id,
                'title': meta['title'],
                'href': meta['href'],
                'stats': [],
            })

    return {
        'activeModules': enabled,
        'period': period,
        'modules': modules,
    }
