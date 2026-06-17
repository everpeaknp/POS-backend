"""
Inventory Services - Core Layer
Provides inventory operations used by all industry modules.
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from inventory.models import Stock, StockMovement
from tenants.middleware import get_current_tenant


def stock_in(product, warehouse, quantity, unit_cost, reference, notes='', created_by=None):
    """
    Add stock to warehouse and create movement record.
    
    This is the CORE inventory function used by all modules to receive materials.
    Called by: Purchase module (GRN), Stock adjustment, Stock transfer (destination)
    
    Args:
        product: Product instance
        warehouse: Warehouse instance
        quantity: Quantity to add (Decimal or number)
        unit_cost: Cost per unit (Decimal or number)
        reference: Reference number (e.g., GRN-001, PO-001)
        notes: Optional notes
        created_by: User who created this movement
    
    Returns:
        tuple: (StockMovement instance, new_stock_quantity)
    
    Raises:
        ValueError: If quantity or unit_cost is invalid
    """
    tenant = get_current_tenant()
    if not tenant:
        raise ValueError("No tenant in context. Cannot perform stock operation.")
    
    quantity = Decimal(str(quantity))
    unit_cost = Decimal(str(unit_cost))
    
    if quantity <= 0:
        raise ValueError(f"Quantity must be positive. Got: {quantity}")
    
    if unit_cost < 0:
        raise ValueError(f"Unit cost cannot be negative. Got: {unit_cost}")
    
    with transaction.atomic():
        # Get or create stock record
        stock, created = Stock.objects.get_or_create(
            tenant=tenant,
            product=product,
            warehouse=warehouse,
            defaults={'quantity': Decimal('0')}
        )
        
        # Update stock quantity
        old_quantity = stock.quantity
        stock.quantity += quantity
        stock.save()
        
        # Create movement record (immutable audit trail)
        movement = StockMovement.objects.create(
            tenant=tenant,
            product=product,
            warehouse=warehouse,
            movement_type='in',
            quantity=quantity,
            unit_cost=unit_cost,
            reference=reference,
            notes=notes or f"Stock in: {quantity} units added",
            created_by=created_by
        )
        
        return movement, stock.quantity


def stock_out(product, warehouse, quantity, unit_cost, reference, notes='', created_by=None):
    """
    Remove stock from warehouse and create movement record.
    
    This is the CORE inventory function used by all modules to issue materials.
    Called by: Sales module, Construction module (material consumption), Stock transfer (source)
    
    Args:
        product: Product instance
        warehouse: Warehouse instance
        quantity: Quantity to remove (Decimal or number)
        unit_cost: Cost per unit (Decimal or number)
        reference: Reference number (e.g., SO-001, SITE-001)
        notes: Optional notes
        created_by: User who created this movement
    
    Returns:
        tuple: (StockMovement instance, new_stock_quantity)
    
    Raises:
        ValueError: If insufficient stock or invalid quantity
    """
    tenant = get_current_tenant()
    if not tenant:
        raise ValueError("No tenant in context. Cannot perform stock operation.")
    
    quantity = Decimal(str(quantity))
    unit_cost = Decimal(str(unit_cost))
    
    if quantity <= 0:
        raise ValueError(f"Quantity must be positive. Got: {quantity}")
    
    if unit_cost < 0:
        raise ValueError(f"Unit cost cannot be negative. Got: {unit_cost}")
    
    with transaction.atomic():
        # Get stock record
        try:
            stock = Stock.objects.get(
                tenant=tenant,
                product=product,
                warehouse=warehouse
            )
        except Stock.DoesNotExist:
            raise ValueError(
                f"No stock record found for {product.name} in {warehouse.name}. "
                f"Cannot remove stock that doesn't exist."
            )
        
        # Check sufficient stock
        if stock.quantity < quantity:
            raise ValueError(
                f"Insufficient stock for {product.name} in {warehouse.name}. "
                f"Available: {stock.quantity}, Required: {quantity}"
            )
        
        # Update stock quantity
        old_quantity = stock.quantity
        stock.quantity -= quantity
        stock.save()
        
        # Create movement record (immutable audit trail)
        movement = StockMovement.objects.create(
            tenant=tenant,
            product=product,
            warehouse=warehouse,
            movement_type='out',
            quantity=quantity,
            unit_cost=unit_cost,
            reference=reference,
            notes=notes or f"Stock out: {quantity} units removed",
            created_by=created_by
        )
        
        return movement, stock.quantity


def stock_transfer(product, from_warehouse, to_warehouse, quantity, unit_cost, reference, notes='', created_by=None):
    """
    Transfer stock between warehouses.
    
    This is the CORE inventory function for inter-warehouse transfers.
    Called by: Inventory module, Construction module (site transfers)
    
    Args:
        product: Product instance
        from_warehouse: Source Warehouse instance
        to_warehouse: Destination Warehouse instance
        quantity: Quantity to transfer (Decimal or number)
        unit_cost: Cost per unit (Decimal or number)
        reference: Reference number (e.g., TR-001)
        notes: Optional notes
        created_by: User who created this movement
    
    Returns:
        tuple: (from_movement, to_movement, from_stock_qty, to_stock_qty)
    
    Raises:
        ValueError: If insufficient stock or invalid parameters
    """
    tenant = get_current_tenant()
    if not tenant:
        raise ValueError("No tenant in context. Cannot perform stock operation.")
    
    if from_warehouse.id == to_warehouse.id:
        raise ValueError("Cannot transfer to the same warehouse.")
    
    quantity = Decimal(str(quantity))
    unit_cost = Decimal(str(unit_cost))
    
    if quantity <= 0:
        raise ValueError(f"Quantity must be positive. Got: {quantity}")
    
    with transaction.atomic():
        # Stock out from source warehouse
        from_movement, from_stock_qty = stock_out(
            product=product,
            warehouse=from_warehouse,
            quantity=quantity,
            unit_cost=unit_cost,
            reference=reference,
            notes=notes or f"Transfer to {to_warehouse.name}",
            created_by=created_by
        )
        
        # Update movement type to 'transfer'
        from_movement.movement_type = 'transfer'
        from_movement.to_warehouse = to_warehouse
        from_movement.save()
        
        # Stock in to destination warehouse
        to_movement, to_stock_qty = stock_in(
            product=product,
            warehouse=to_warehouse,
            quantity=quantity,
            unit_cost=unit_cost,
            reference=reference,
            notes=notes or f"Transfer from {from_warehouse.name}",
            created_by=created_by
        )
        
        # Update movement type to 'transfer'
        to_movement.movement_type = 'transfer'
        to_movement.from_warehouse = from_warehouse
        to_movement.save()
        
        return from_movement, to_movement, from_stock_qty, to_stock_qty


def stock_adjustment(product, warehouse, quantity, unit_cost, reference, notes, created_by=None):
    """
    Adjust stock quantity (correction entry).
    
    Used for: Physical count corrections, damaged goods, theft, etc.
    
    Args:
        product: Product instance
        warehouse: Warehouse instance
        quantity: Adjustment quantity (positive = add, negative = remove)
        unit_cost: Cost per unit (Decimal or number)
        reference: Reference number (e.g., ADJ-001)
        notes: Reason for adjustment (REQUIRED)
        created_by: User who created this movement
    
    Returns:
        tuple: (StockMovement instance, new_stock_quantity)
    
    Raises:
        ValueError: If notes are empty or invalid quantity
    """
    tenant = get_current_tenant()
    if not tenant:
        raise ValueError("No tenant in context. Cannot perform stock operation.")
    
    if not notes or not notes.strip():
        raise ValueError("Notes are required for stock adjustments. Must provide reason.")
    
    quantity = Decimal(str(quantity))
    unit_cost = Decimal(str(unit_cost))
    
    if quantity == 0:
        raise ValueError("Adjustment quantity cannot be zero.")
    
    with transaction.atomic():
        # Get or create stock record
        stock, created = Stock.objects.get_or_create(
            tenant=tenant,
            product=product,
            warehouse=warehouse,
            defaults={'quantity': Decimal('0')}
        )
        
        # Check if adjustment would result in negative stock
        new_quantity = stock.quantity + quantity
        if new_quantity < 0:
            raise ValueError(
                f"Adjustment would result in negative stock. "
                f"Current: {stock.quantity}, Adjustment: {quantity}, Result: {new_quantity}"
            )
        
        # Update stock quantity
        old_quantity = stock.quantity
        stock.quantity = new_quantity
        stock.save()
        
        # Create movement record
        movement = StockMovement.objects.create(
            tenant=tenant,
            product=product,
            warehouse=warehouse,
            movement_type='adjustment',
            quantity=abs(quantity),  # Store as positive, type indicates direction
            unit_cost=unit_cost,
            reference=reference,
            notes=f"Adjustment: {notes} (Old: {old_quantity}, New: {new_quantity})",
            created_by=created_by
        )
        
        return movement, stock.quantity


def get_stock_level(product, warehouse=None):
    """
    Get current stock level for a product.
    
    Args:
        product: Product instance
        warehouse: Optional Warehouse instance (if None, returns total across all warehouses)
    
    Returns:
        Decimal: Current stock quantity
    """
    tenant = get_current_tenant()
    if not tenant:
        return Decimal('0')
    
    if warehouse:
        try:
            stock = Stock.objects.get(
                tenant=tenant,
                product=product,
                warehouse=warehouse
            )
            return stock.quantity
        except Stock.DoesNotExist:
            return Decimal('0')
    else:
        # Total across all warehouses
        stocks = Stock.objects.filter(
            tenant=tenant,
            product=product
        )
        return sum(s.quantity for s in stocks)


def check_low_stock(product, warehouse=None):
    """
    Check if product is below minimum stock level.
    
    Args:
        product: Product instance
        warehouse: Optional Warehouse instance
    
    Returns:
        dict: {
            'is_low': bool,
            'current_stock': Decimal,
            'minimum_stock': Decimal,
            'shortage': Decimal
        }
    """
    current_stock = get_stock_level(product, warehouse)
    minimum_stock = product.minimum_stock or Decimal('0')
    
    is_low = current_stock < minimum_stock
    shortage = max(Decimal('0'), minimum_stock - current_stock)
    
    return {
        'is_low': is_low,
        'current_stock': current_stock,
        'minimum_stock': minimum_stock,
        'shortage': shortage
    }


def get_stock_value(product, warehouse=None):
    """
    Calculate total value of stock for a product.
    
    Uses weighted average cost from recent stock movements.
    
    Args:
        product: Product instance
        warehouse: Optional Warehouse instance
    
    Returns:
        Decimal: Total stock value
    """
    tenant = get_current_tenant()
    if not tenant:
        return Decimal('0')
    
    # Get stock quantity
    quantity = get_stock_level(product, warehouse)
    
    if quantity == 0:
        return Decimal('0')
    
    # Get recent stock movements to calculate average cost
    movements = StockMovement.objects.filter(
        tenant=tenant,
        product=product,
        movement_type__in=['in', 'transfer']
    ).order_by('-created_at')[:10]  # Last 10 movements
    
    if not movements:
        # Fallback to product cost price
        return quantity * (product.cost_price or Decimal('0'))
    
    # Calculate weighted average
    total_cost = sum(m.quantity * m.unit_cost for m in movements)
    total_quantity = sum(m.quantity for m in movements)
    
    if total_quantity == 0:
        return quantity * (product.cost_price or Decimal('0'))
    
    avg_cost = total_cost / total_quantity
    return quantity * avg_cost
