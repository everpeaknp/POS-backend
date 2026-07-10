"""Business alert producers: inventory, sales, purchase, payments, expiry."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from reports.utils import build_low_stock_items

from .alert_services import (
    PREF_INVENTORY,
    PREF_ORDERS,
    PREF_PAYMENT,
    PREF_TEAM,
    iter_tenant_approvers,
    iter_tenant_finance_users,
    iter_tenant_users,
    notify_user,
    notify_users,
)

DEDUPE_HOURS = 24
PAYMENT_DUE_DAYS = 3
EXPIRY_LOOKAHEAD_DAYS = 14


def _frontend_path(path: str) -> str:
    return path if path.startswith('/') else f'/{path}'


def notify_low_stock_for_product(product, tenant) -> int:
    """Notify tenant users when a product drops below reorder level."""
    if not product.reorder_level or product.reorder_level <= 0:
        return 0
    if product.status != 'active':
        return 0

    total_stock = product.get_total_stock()
    if total_stock >= product.reorder_level:
        return 0

    urgency = 'critical' if total_stock < (product.reorder_level * Decimal('0.5')) else 'warning'
    level = 'critical' if urgency == 'critical' else 'warning'
    title = f"Low stock: {product.name}"
    message = (
        f"{product.name} ({product.sku}) is below reorder level. "
        f"Current stock: {total_stock}, reorder at: {product.reorder_level}."
    )
    action_url = _frontend_path(f'/dashboard/inventory/products/{product.id}')

    return notify_users(
        iter_tenant_users(tenant),
        tenant=tenant,
        title=title,
        message=message,
        notification_type='inventory_alert',
        level=level,
        reference_type='product',
        reference_id=product.id,
        action_url=action_url,
        email_pref_key=PREF_INVENTORY,
        dedupe_hours=DEDUPE_HOURS,
        data={'sku': product.sku, 'current_stock': float(total_stock), 'reorder_level': float(product.reorder_level)},
    )


def scan_low_stock_alerts(tenant) -> int:
    """Daily scan for all low-stock products."""
    count = 0
    for item in build_low_stock_items(tenant):
        from inventory.models import Product

        try:
            product = Product.objects.get(tenant=tenant, id=item['product_id'])
        except Product.DoesNotExist:
            continue
        count += notify_low_stock_for_product(product, tenant)
    return count


def notify_sales_order_status_change(sales_order, *, old_status: str, new_status: str) -> int:
    if old_status == new_status:
        return 0

    tenant = sales_order.tenant
    title = f"Sales order {sales_order.order_number} updated"
    message = (
        f"Order for {sales_order.customer.name} changed from {old_status} to {new_status}."
    )
    action_url = _frontend_path(f'/dashboard/sales/orders/{sales_order.id}')

    recipients = list(iter_tenant_users(tenant))
    if sales_order.created_by_id:
        recipients = [u for u in recipients if u.id == sales_order.created_by_id] or recipients

    return notify_users(
        recipients,
        tenant=tenant,
        title=title,
        message=message,
        notification_type='sales_alert',
        level='info' if new_status != 'Cancelled' else 'warning',
        reference_type='sales_order',
        reference_id=sales_order.id,
        action_url=action_url,
        email_pref_key=PREF_ORDERS,
        dedupe_hours=1,
        data={'old_status': old_status, 'new_status': new_status},
    )


def notify_purchase_request_submitted(purchase_request) -> int:
    tenant = purchase_request.tenant
    requester = purchase_request.requested_by
    title = f"Purchase request {purchase_request.request_number} needs approval"
    message = (
        f"{requester.get_full_name() or requester.username} submitted a purchase request "
        f"for {purchase_request.department} (required by {purchase_request.required_by})."
    )
    action_url = _frontend_path(f'/dashboard/purchase/requests/{purchase_request.id}')

    return notify_users(
        iter_tenant_approvers(tenant),
        tenant=tenant,
        title=title,
        message=message,
        notification_type='purchase_reminder',
        level='warning' if purchase_request.priority == 'High' else 'info',
        reference_type='purchase_request',
        reference_id=purchase_request.id,
        action_url=action_url,
        email_pref_key=PREF_TEAM,
        exclude_user=requester,
        dedupe_hours=12,
    )


def notify_purchase_request_decision(purchase_request, *, approved: bool) -> int:
    tenant = purchase_request.tenant
    requester = purchase_request.requested_by
    if approved:
        title = f"Purchase request {purchase_request.request_number} approved"
        message = f"Your purchase request for {purchase_request.department} was approved."
        level = 'success'
    else:
        title = f"Purchase request {purchase_request.request_number} rejected"
        reason = purchase_request.rejection_reason or 'No reason provided.'
        message = f"Your purchase request was rejected. Reason: {reason}"
        level = 'warning'

    action_url = _frontend_path(f'/dashboard/purchase/requests/{purchase_request.id}')
    notification = notify_user(
        user=requester,
        tenant=tenant,
        title=title,
        message=message,
        notification_type='purchase_reminder',
        level=level,
        reference_type='purchase_request',
        reference_id=purchase_request.id,
        action_url=action_url,
        email_pref_key=PREF_ORDERS,
        dedupe_hours=1,
        skip_dedupe=True,
    )
    return 1 if notification else 0


def _notify_invoice_payment(
    *,
    tenant,
    invoice,
    invoice_kind: str,
    party_name: str,
    title: str,
    message: str,
    action_url: str,
    level: str = 'warning',
) -> int:
    ref_type = f'{invoice_kind}_invoice'
    return notify_users(
        iter_tenant_finance_users(tenant) or iter_tenant_users(tenant),
        tenant=tenant,
        title=title,
        message=message,
        notification_type='payment_reminder',
        level=level,
        reference_type=ref_type,
        reference_id=invoice.id,
        action_url=action_url,
        email_pref_key=PREF_PAYMENT,
        dedupe_hours=DEDUPE_HOURS,
        data={
            'invoice_number': invoice.invoice_number,
            'due_date': str(invoice.due_date),
            'balance': float(getattr(invoice, 'balance', invoice.amount - invoice.paid_amount)),
        },
    )


def scan_payment_reminders(tenant) -> int:
    """Remind finance users about due/overdue customer and supplier invoices."""
    from sales.credit_utils import mark_overdue_invoices
    from sales.models import Invoice
    from purchase.models import PurchaseInvoice
    from purchase.payables_utils import mark_overdue_purchase_invoices

    today = timezone.now().date()
    due_cutoff = today + timedelta(days=PAYMENT_DUE_DAYS)
    count = 0

    sales_qs = Invoice.objects.filter(tenant=tenant)
    mark_overdue_invoices(sales_qs)
    purchase_qs = PurchaseInvoice.objects.filter(tenant=tenant)
    mark_overdue_purchase_invoices(purchase_qs)

    overdue_sales = Invoice.objects.filter(tenant=tenant, status='Overdue')
    for invoice in overdue_sales:
        balance = invoice.balance
        if balance <= 0:
            continue
        count += _notify_invoice_payment(
            tenant=tenant,
            invoice=invoice,
            invoice_kind='sales',
            party_name=invoice.customer.name,
            title=f"Overdue invoice: {invoice.invoice_number}",
            message=(
                f"Customer {invoice.customer.name} owes Rs. {balance:,.2f} "
                f"on invoice {invoice.invoice_number} (due {invoice.due_date})."
            ),
            action_url=_frontend_path(f'/dashboard/sales/invoices/{invoice.id}'),
            level='critical',
        )

    due_soon_sales = Invoice.objects.filter(
        tenant=tenant,
        status__in=['Sent', 'Partially Paid'],
        due_date__gte=today,
        due_date__lte=due_cutoff,
    )
    for invoice in due_soon_sales:
        balance = invoice.balance
        if balance <= 0:
            continue
        days_left = (invoice.due_date - today).days
        count += _notify_invoice_payment(
            tenant=tenant,
            invoice=invoice,
            invoice_kind='sales',
            party_name=invoice.customer.name,
            title=f"Payment due in {days_left} day(s): {invoice.invoice_number}",
            message=(
                f"Customer {invoice.customer.name} has Rs. {balance:,.2f} due "
                f"on {invoice.due_date} for invoice {invoice.invoice_number}."
            ),
            action_url=_frontend_path(f'/dashboard/sales/invoices/{invoice.id}'),
            level='warning',
        )

    overdue_purchase = PurchaseInvoice.objects.filter(
        tenant=tenant,
        status='Overdue',
    )
    for invoice in overdue_purchase:
        balance = invoice.amount - invoice.paid_amount
        if balance <= 0:
            continue
        count += _notify_invoice_payment(
            tenant=tenant,
            invoice=invoice,
            invoice_kind='purchase',
            party_name=invoice.supplier.name,
            title=f"Supplier payment overdue: {invoice.invoice_number}",
            message=(
                f"Pay Rs. {balance:,.2f} to {invoice.supplier.name} "
                f"for invoice {invoice.invoice_number} (due {invoice.due_date})."
            ),
            action_url=_frontend_path(f'/dashboard/purchase/invoices/{invoice.id}'),
            level='critical',
        )

    due_soon_purchase = PurchaseInvoice.objects.filter(
        tenant=tenant,
        status__in=['Received', 'Partially Paid'],
        due_date__gte=today,
        due_date__lte=due_cutoff,
    )
    for invoice in due_soon_purchase:
        balance = invoice.amount - invoice.paid_amount
        if balance <= 0:
            continue
        days_left = (invoice.due_date - today).days
        count += _notify_invoice_payment(
            tenant=tenant,
            invoice=invoice,
            invoice_kind='purchase',
            party_name=invoice.supplier.name,
            title=f"Supplier payment due in {days_left} day(s): {invoice.invoice_number}",
            message=(
                f"Rs. {balance:,.2f} payable to {invoice.supplier.name} "
                f"by {invoice.due_date} for invoice {invoice.invoice_number}."
            ),
            action_url=_frontend_path(f'/dashboard/purchase/invoices/{invoice.id}'),
            level='warning',
        )

    return count


def scan_purchase_reminders(tenant) -> int:
    """Remind approvers about pending requests and requesters about upcoming required dates."""
    from purchase.models import PurchaseRequest

    today = timezone.now().date()
    required_cutoff = today + timedelta(days=PAYMENT_DUE_DAYS)
    count = 0

    pending = PurchaseRequest.objects.filter(tenant=tenant, status='Pending Approval')
    for pr in pending:
        count += notify_users(
            iter_tenant_approvers(tenant),
            tenant=tenant,
            title=f"Pending approval: {pr.request_number}",
            message=(
                f"Purchase request for {pr.department} is awaiting approval "
                f"(required by {pr.required_by})."
            ),
            notification_type='purchase_reminder',
            level='warning' if pr.required_by <= required_cutoff else 'info',
            reference_type='purchase_request',
            reference_id=pr.id,
            action_url=_frontend_path(f'/dashboard/purchase/requests/{pr.id}'),
            email_pref_key=PREF_TEAM,
            exclude_user=pr.requested_by,
            dedupe_hours=DEDUPE_HOURS,
        )

    upcoming = PurchaseRequest.objects.filter(
        tenant=tenant,
        status__in=['Pending Approval', 'Approved'],
        required_by__gte=today,
        required_by__lte=required_cutoff,
    )
    for pr in upcoming:
        days_left = (pr.required_by - today).days
        count += notify_user(
            user=pr.requested_by,
            tenant=tenant,
            title=f"Purchase required in {days_left} day(s): {pr.request_number}",
            message=(
                f"Items for {pr.department} are required by {pr.required_by}. "
                f"Current status: {pr.status}."
            ),
            notification_type='purchase_reminder',
            level='warning',
            reference_type='purchase_request',
            reference_id=pr.id,
            action_url=_frontend_path(f'/dashboard/purchase/requests/{pr.id}'),
            email_pref_key=PREF_ORDERS,
            dedupe_hours=DEDUPE_HOURS,
        ) and 1 or 0

    return count


def notify_product_expiry(product, *, days_left: int, expired: bool = False) -> int:
    tenant = product.tenant
    total_stock = product.get_total_stock()
    if total_stock <= 0:
        return 0

    if expired:
        title = f"Expired product: {product.name}"
        message = (
            f"{product.name} ({product.sku}) expired on {product.expiry_date}. "
            f"{total_stock} units still in stock."
        )
        level = 'critical'
    else:
        title = f"Expiring soon: {product.name}"
        message = (
            f"{product.name} ({product.sku}) expires in {days_left} day(s) "
            f"({product.expiry_date}). {total_stock} units in stock."
        )
        level = 'warning' if days_left <= 7 else 'info'

    return notify_users(
        iter_tenant_users(tenant),
        tenant=tenant,
        title=title,
        message=message,
        notification_type='inventory_alert',
        level=level,
        reference_type='product_expiry',
        reference_id=product.id,
        action_url=_frontend_path(f'/dashboard/inventory/products/{product.id}'),
        email_pref_key=PREF_INVENTORY,
        dedupe_hours=DEDUPE_HOURS,
        data={'expiry_date': str(product.expiry_date), 'days_left': days_left},
    )


def scan_expiry_alerts(tenant) -> int:
    from inventory.models import Product

    today = timezone.now().date()
    cutoff = today + timedelta(days=EXPIRY_LOOKAHEAD_DAYS)
    count = 0

    products = Product.objects.filter(
        tenant=tenant,
        status='active',
        expiry_date__isnull=False,
        expiry_date__lte=cutoff,
    ).annotate(
        total_stock=Coalesce(Sum('stocks__quantity'), Value(Decimal('0.00')))
    ).filter(total_stock__gt=0)

    for product in products:
        days_left = (product.expiry_date - today).days
        count += notify_product_expiry(
            product,
            days_left=days_left,
            expired=days_left < 0,
        )
    return count


def process_tenant_business_alerts(tenant) -> dict:
    return {
        'low_stock': scan_low_stock_alerts(tenant),
        'payment_reminders': scan_payment_reminders(tenant),
        'purchase_reminders': scan_purchase_reminders(tenant),
        'expiry_alerts': scan_expiry_alerts(tenant),
    }
