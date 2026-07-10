"""
Inventory Services - Core Layer
Provides inventory operations used by all industry modules.
"""

from decimal import Decimal
from django.db import transaction
import logging
from inventory.models import Stock, StockMovement, Warehouse, Product
from tenants.middleware import get_current_tenant

logger = logging.getLogger(__name__)


def _resolve_tenant(tenant=None, product=None, warehouse=None):
    """Resolve tenant from explicit arg, request context, or related objects."""
    if tenant is not None:
        return tenant

    tenant = get_current_tenant()
    if tenant:
        return tenant

    if warehouse is not None and getattr(warehouse, 'tenant_id', None):
        return warehouse.tenant

    if product is not None and getattr(product, 'tenant_id', None):
        return product.tenant

    return None


def _maybe_notify_low_stock(product, tenant) -> None:
    try:
        from users.business_alerts import notify_low_stock_for_product
        notify_low_stock_for_product(product, tenant)
    except Exception:
        logger.exception('Low stock notification failed for product %s', product.id)


def resolve_warehouse_for_product(product, tenant, warehouse_id=None):
    """Pick warehouse for a stock movement."""
    if warehouse_id:
        return Warehouse.objects.get(id=warehouse_id, tenant=tenant, is_active=True)

    stock = (
        Stock.objects.filter(tenant=tenant, product=product, quantity__gt=0)
        .select_related('warehouse')
        .order_by('-quantity')
        .first()
    )
    if stock:
        return stock.warehouse

    return Warehouse.objects.filter(tenant=tenant, is_active=True).order_by('id').first()


def _get_or_create_stock_locked(tenant, product, warehouse):
    stock = (
        Stock.objects.select_for_update()
        .filter(tenant=tenant, product=product, warehouse=warehouse)
        .first()
    )
    if stock:
        return stock
    return Stock.objects.create(
        tenant=tenant,
        product=product,
        warehouse=warehouse,
        quantity=Decimal('0'),
    )


def validate_product_stock(product, quantity, tenant, warehouse_id=None):
    """Ensure enough stock exists in the warehouse that would be used for deduction."""
    warehouse = resolve_warehouse_for_product(product, tenant, warehouse_id=warehouse_id)
    if not warehouse:
        raise ValueError(f'No active warehouse available for {product.name}')
    available = get_stock_level(product, warehouse)
    required = Decimal(str(quantity))
    if available < required:
        raise ValueError(
            f'Insufficient stock for {product.name} in {warehouse.name}. '
            f'Available: {available}, Required: {required}'
        )
    return warehouse


def validate_order_line_stock(lines_data, tenant, warehouse_id=None):
    """Aggregate duplicate products and validate per-warehouse availability."""
    from collections import defaultdict

    totals = defaultdict(lambda: Decimal('0'))
    products = {}
    for line_data in lines_data:
        product = line_data.get('product')
        quantity = line_data.get('quantity')
        if not product or not quantity:
            continue
        totals[product.id] += Decimal(str(quantity))
        products[product.id] = product

    for product_id, quantity in totals.items():
        validate_product_stock(products[product_id], quantity, tenant, warehouse_id=warehouse_id)


def stock_in(
    product,
    warehouse,
    quantity,
    reference_type='',
    reference_id=None,
    notes='',
    reason='',
    performed_by=None,
    tenant=None,
):
    """
    Add stock to warehouse and create movement record.
    """
    tenant = _resolve_tenant(tenant=tenant, product=product, warehouse=warehouse)
    if not tenant:
        raise ValueError("No tenant in context. Cannot perform stock operation.")

    quantity = Decimal(str(quantity))

    if quantity <= 0:
        raise ValueError(f"Quantity must be positive. Got: {quantity}")

    with transaction.atomic():
        stock = _get_or_create_stock_locked(tenant, product, warehouse)

        stock.quantity += quantity
        stock.save()

        movement = StockMovement.objects.create(
            tenant=tenant,
            product=product,
            warehouse=warehouse,
            movement_type='in',
            quantity=quantity,
            reference_type=reference_type or '',
            reference_id=reference_id,
            reason=reason or f"Stock in: {quantity} units",
            notes=notes or '',
            performed_by=performed_by,
        )

        return movement, stock.quantity


def stock_out(
    product,
    warehouse,
    quantity,
    reference_type='',
    reference_id=None,
    notes='',
    reason='',
    performed_by=None,
    tenant=None,
):
    """
    Remove stock from warehouse and create movement record.
    """
    tenant = _resolve_tenant(tenant=tenant, product=product, warehouse=warehouse)
    if not tenant:
        raise ValueError("No tenant in context. Cannot perform stock operation.")

    quantity = Decimal(str(quantity))

    if quantity <= 0:
        raise ValueError(f"Quantity must be positive. Got: {quantity}")

    with transaction.atomic():
        stock = (
            Stock.objects.select_for_update()
            .filter(tenant=tenant, product=product, warehouse=warehouse)
            .first()
        )
        if not stock:
            raise ValueError(
                f"No stock record found for {product.name} in {warehouse.name}. "
                f"Cannot remove stock that doesn't exist."
            )

        if stock.quantity < quantity:
            raise ValueError(
                f"Insufficient stock for {product.name} in {warehouse.name}. "
                f"Available: {stock.quantity}, Required: {quantity}"
            )

        stock.quantity -= quantity
        stock.save()

        movement = StockMovement.objects.create(
            tenant=tenant,
            product=product,
            warehouse=warehouse,
            movement_type='out',
            quantity=quantity,
            reference_type=reference_type or '',
            reference_id=reference_id,
            reason=reason or f"Stock out: {quantity} units",
            notes=notes or '',
            performed_by=performed_by,
        )

        _maybe_notify_low_stock(product, tenant)

        return movement, stock.quantity


def stock_transfer(product, from_warehouse, to_warehouse, quantity, reference_type='', reference_id=None, notes='', reason='', performed_by=None, tenant=None):
    """Transfer stock between warehouses."""
    if from_warehouse.id == to_warehouse.id:
        raise ValueError("Cannot transfer to the same warehouse.")

    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise ValueError(f"Quantity must be positive. Got: {quantity}")

    tenant = _resolve_tenant(tenant=tenant, product=product, warehouse=from_warehouse)

    with transaction.atomic():
        from_movement, from_stock_qty = stock_out(
            product=product,
            warehouse=from_warehouse,
            quantity=quantity,
            reference_type=reference_type,
            reference_id=reference_id,
            reason=reason or f"Transfer to {to_warehouse.name}",
            notes=notes,
            performed_by=performed_by,
            tenant=tenant,
        )

        from_movement.movement_type = 'transfer'
        from_movement.to_warehouse = to_warehouse
        from_movement.save(update_fields=['movement_type', 'to_warehouse'])

        to_movement, to_stock_qty = stock_in(
            product=product,
            warehouse=to_warehouse,
            quantity=quantity,
            reference_type=reference_type,
            reference_id=reference_id,
            reason=reason or f"Transfer from {from_warehouse.name}",
            notes=notes,
            performed_by=performed_by,
            tenant=tenant,
        )

        to_movement.movement_type = 'transfer'
        to_movement.from_warehouse = from_warehouse
        to_movement.save(update_fields=['movement_type', 'from_warehouse'])

        return from_movement, to_movement, from_stock_qty, to_stock_qty


def stock_adjustment(product, warehouse, quantity, reference_type='', reference_id=None, notes='', reason='', performed_by=None, tenant=None):
    """Adjust stock quantity (positive adds, negative removes)."""
    note_text = (notes or reason or '').strip()
    if not note_text:
        raise ValueError("Notes or reason are required for stock adjustments.")

    quantity = Decimal(str(quantity))
    if quantity == 0:
        raise ValueError("Adjustment quantity cannot be zero.")

    tenant = _resolve_tenant(tenant=tenant, product=product, warehouse=warehouse)
    if not tenant:
        raise ValueError("No tenant in context. Cannot perform stock operation.")

    with transaction.atomic():
        stock = _get_or_create_stock_locked(tenant, product, warehouse)
        new_quantity = stock.quantity + quantity
        if new_quantity < 0:
            raise ValueError('Adjustment would result in negative stock')

        stock.quantity = new_quantity
        stock.save()

        movement = StockMovement.objects.create(
            tenant=tenant,
            product=product,
            warehouse=warehouse,
            movement_type='adjustment',
            quantity=quantity,
            reference_type=reference_type or 'Adjustment',
            reference_id=reference_id,
            reason=reason or 'Stock adjustment',
            notes=note_text,
            performed_by=performed_by,
        )

        if quantity < 0:
            _maybe_notify_low_stock(product, tenant)

        return movement, stock.quantity


def get_stock_level(product, warehouse=None):
    """Get current stock level for a product."""
    tenant = get_current_tenant()
    if not tenant:
        return Decimal('0')

    if warehouse:
        try:
            stock = Stock.objects.get(
                tenant=tenant,
                product=product,
                warehouse=warehouse,
            )
            return stock.quantity
        except Stock.DoesNotExist:
            return Decimal('0')

    stocks = Stock.objects.filter(tenant=tenant, product=product)
    return sum((s.quantity for s in stocks), Decimal('0'))


def is_sales_order_stock_allocated(sales_order):
    """Net stock allocated for a sales order (out minus reversal in)."""
    tenant = sales_order.tenant
    movements = StockMovement.objects.filter(
        tenant=tenant,
        reference_type='SalesOrder',
        reference_id=sales_order.id,
    )
    out_qty = sum(
        (m.quantity for m in movements if m.movement_type == 'out'),
        Decimal('0'),
    )
    in_qty = sum(
        (m.quantity for m in movements if m.movement_type == 'in'),
        Decimal('0'),
    )
    return out_qty - in_qty


def apply_sales_order_stock(sales_order, performed_by=None, warehouse_id=None):
    """Deduct stock when a sales order is confirmed."""
    if is_sales_order_stock_allocated(sales_order) > 0:
        return []

    movements = []
    for line in sales_order.lines.select_related('product'):
        warehouse = resolve_warehouse_for_product(
            line.product,
            sales_order.tenant,
            warehouse_id=warehouse_id,
        )
        if not warehouse:
            raise ValueError(f"No active warehouse available for {line.product.name}")

        movement, _qty = stock_out(
            product=line.product,
            warehouse=warehouse,
            quantity=line.quantity,
            reference_type='SalesOrder',
            reference_id=sales_order.id,
            reason=f"Sales Order {sales_order.order_number}",
            notes=f"Stock allocated on confirmation",
            performed_by=performed_by,
            tenant=sales_order.tenant,
        )
        movements.append(movement)

    return movements


def reverse_sales_order_stock(sales_order, performed_by=None):
    """Restore stock when a confirmed sales order is cancelled."""
    if is_sales_order_stock_allocated(sales_order) <= 0:
        return []

    movements = []
    out_movements = StockMovement.objects.filter(
        tenant=sales_order.tenant,
        reference_type='SalesOrder',
        reference_id=sales_order.id,
        movement_type='out',
    ).select_related('product', 'warehouse')

    for mov in out_movements:
        movement, _qty = stock_in(
            product=mov.product,
            warehouse=mov.warehouse,
            quantity=mov.quantity,
            reference_type='SalesOrder',
            reference_id=sales_order.id,
            reason=f"Cancelled Sales Order {sales_order.order_number}",
            notes="Stock restored on cancellation",
            performed_by=performed_by,
            tenant=sales_order.tenant,
        )
        movements.append(movement)

    return movements


def apply_purchase_receive_stock(purchase_order, line, quantity, performed_by=None, warehouse_id=None):
    """Increase stock when purchase order items are received."""
    warehouse = resolve_warehouse_for_product(
        line.product,
        purchase_order.tenant,
        warehouse_id=warehouse_id,
    )
    if not warehouse:
        raise ValueError(f"No active warehouse available for {line.product.name}")

    unit_price = Decimal(str(getattr(line, 'unit_price', 0) or 0))
    quantity_dec = Decimal(str(quantity))
    movement, _qty = stock_in(
        product=line.product,
        warehouse=warehouse,
        quantity=quantity,
        reference_type='PurchaseOrder',
        reference_id=purchase_order.id,
        reason=f"Received from PO {purchase_order.po_number}",
        notes=f"PO line {line.id}",
        performed_by=performed_by,
        tenant=purchase_order.tenant,
    )

    if unit_price > 0:
        product = line.product
        current_total = get_stock_level(product)
        old_qty = current_total - quantity_dec
        old_cost = product.cost_price or Decimal('0')
        receipt_cost = quantity_dec * unit_price
        if current_total > 0:
            new_cost = (max(Decimal('0'), old_qty) * old_cost + receipt_cost) / current_total
            Product.objects.filter(pk=product.pk).update(cost_price=new_cost)

    return movement


def check_low_stock(product, warehouse=None):
    """Check if product is below reorder level."""
    current_stock = get_stock_level(product, warehouse)
    minimum_stock = product.reorder_level or Decimal('0')
    is_low = current_stock < minimum_stock
    shortage = max(Decimal('0'), minimum_stock - current_stock)

    return {
        'is_low': is_low,
        'current_stock': current_stock,
        'minimum_stock': minimum_stock,
        'shortage': shortage,
    }


def get_stock_value(product, warehouse=None):
    """Calculate total value of stock for a product."""
    quantity = get_stock_level(product, warehouse)
    if quantity == 0:
        return Decimal('0')
    return quantity * (product.cost_price or Decimal('0'))
