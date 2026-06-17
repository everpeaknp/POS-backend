from django.db import models
from utils.models import TenantModel


class Category(TenantModel):
    """
    Hierarchical product categories (e.g., Construction > Cement > OPC Cement)
    """
    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    description = models.TextField(blank=True)
    
    class Meta:
        db_table = 'categories'
        ordering = ['name']
        verbose_name_plural = 'Categories'
    
    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name


class UnitOfMeasure(TenantModel):
    """
    Units of measure: kg, ton, bag, piece, litre, meter, etc.
    """
    name = models.CharField(max_length=100)
    abbreviation = models.CharField(max_length=20)
    type = models.CharField(
        max_length=50,
        choices=[
            ('count', 'Count'),
            ('weight', 'Weight'),
            ('length', 'Length'),
            ('volume', 'Volume'),
            ('area', 'Area'),
        ],
        default='count'
    )
    
    class Meta:
        db_table = 'units_of_measure'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.abbreviation})"


class Warehouse(TenantModel):
    """
    Named storage locations (site, godown, shop floor)
    """
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=500, blank=True)
    manager = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_warehouses'
    )
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'warehouses'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Product(TenantModel):
    """
    Product model with automatic tenant scoping and price history tracking.
    """
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Categorization
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products'
    )
    unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.CASCADE,
        related_name='products'
    )
    
    # Pricing (in NPR paisa - stored as decimal)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Stock Management
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Active'),
            ('inactive', 'Inactive'),
            ('discontinued', 'Discontinued'),
        ],
        default='active'
    )
    
    class Meta:
        db_table = 'products'
        ordering = ['name']
        unique_together = [['tenant', 'sku']]
    
    def __str__(self):
        return f"{self.name} ({self.sku})"
    
    def get_total_stock(self):
        """Get total stock across all warehouses"""
        return self.stocks.aggregate(
            total=models.Sum('quantity')
        )['total'] or 0
    
    def get_price_for_customer(self, customer, quantity=1, date=None):
        """
        Get the applicable price for a customer considering:
        1. Customer-specific pricing (highest priority)
        2. Bulk pricing (if no customer-specific price)
        3. Base selling price (fallback)
        """
        from inventory.pricing_models import CustomerSpecificPrice
        from inventory.bulk_pricing_models import BulkPricing
        
        # Check customer-specific pricing first
        customer_price = CustomerSpecificPrice.get_price_for_customer(
            customer, self, quantity, date
        )
        if customer_price is not None:
            return customer_price
        
        # Check bulk pricing
        bulk_price = BulkPricing.get_price_for_quantity(self, quantity)
        if bulk_price != self.selling_price:
            return bulk_price
        
        # Return base selling price
        return self.selling_price
    
    def save(self, *args, **kwargs):
        """Override save to track price changes"""
        # Track if this is an update (has pk) and prices changed
        if self.pk:
            try:
                old_product = Product.objects.get(pk=self.pk)
                old_cost = old_product.cost_price
                old_selling = old_product.selling_price
                
                # Save the product first
                super().save(*args, **kwargs)
                
                # Create price history if prices changed
                if old_cost != self.cost_price or old_selling != self.selling_price:
                    from inventory.pricing_models import PriceHistory
                    PriceHistory.create_from_product_change(
                        product=self,
                        old_cost=old_cost,
                        old_selling=old_selling,
                        reason=kwargs.get('price_change_reason', ''),
                        changed_by=kwargs.get('changed_by', None)
                    )
            except Product.DoesNotExist:
                # Product doesn't exist yet, just save
                super().save(*args, **kwargs)
        else:
            # New product, just save
            super().save(*args, **kwargs)


class Stock(TenantModel):
    """
    Stock tracking per warehouse with automatic tenant scoping.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='stocks'
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='stocks'
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    class Meta:
        db_table = 'stocks'
        unique_together = [['tenant', 'product', 'warehouse']]
    
    def __str__(self):
        return f"{self.product.name} @ {self.warehouse.name}: {self.quantity}"


class StockMovement(TenantModel):
    """
    Immutable audit trail of all stock movements.
    """
    MOVEMENT_TYPE_CHOICES = [
        ('in', 'Stock In'),
        ('out', 'Stock Out'),
        ('transfer', 'Transfer'),
        ('adjustment', 'Adjustment'),
    ]
    
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='movements'
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='movements'
    )
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPE_CHOICES)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    
    # For transfers
    from_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='outgoing_movements'
    )
    to_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='incoming_movements'
    )
    
    # Reference to source document
    reference_type = models.CharField(max_length=50, blank=True)
    reference_id = models.IntegerField(null=True, blank=True)
    
    # Details
    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    
    # Audit
    performed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='stock_movements'
    )
    
    class Meta:
        db_table = 'stock_movements'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.movement_type}: {self.product.name} ({self.quantity})"
