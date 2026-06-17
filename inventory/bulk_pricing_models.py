from django.db import models
from utils.models import TenantModel


class BulkPricing(TenantModel):
    """
    Tiered pricing based on quantity ranges
    Example: 1-10 units = Rs 100, 11-50 units = Rs 95, 51+ units = Rs 90
    """
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.CASCADE,
        related_name='bulk_prices'
    )
    
    # Quantity range
    min_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Minimum quantity for this price tier"
    )
    max_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum quantity (null = unlimited)"
    )
    
    # Price for this tier
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Price per unit for this quantity range"
    )
    
    # Optional discount percentage (alternative to fixed price)
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Discount percentage from base selling price"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'bulk_pricing'
        ordering = ['product', 'min_quantity']
        unique_together = [['tenant', 'product', 'min_quantity']]
        indexes = [
            models.Index(fields=['product', 'min_quantity']),
            models.Index(fields=['tenant', 'product']),
        ]
    
    def __str__(self):
        max_qty = f"{self.max_quantity}" if self.max_quantity else "∞"
        return f"{self.product.name}: {self.min_quantity}-{max_qty} @ Rs {self.unit_price}"
    
    def clean(self):
        """Validate quantity ranges"""
        from django.core.exceptions import ValidationError
        
        if self.max_quantity and self.max_quantity < self.min_quantity:
            raise ValidationError("Maximum quantity must be greater than minimum quantity")
        
        # Check for overlapping ranges
        overlapping = BulkPricing.objects.filter(
            tenant=self.tenant,
            product=self.product,
            is_active=True
        ).exclude(id=self.id)
        
        for other in overlapping:
            # Check if ranges overlap
            if self.max_quantity is None:
                # This tier is unlimited, check if it starts before another tier ends
                if other.max_quantity is None or self.min_quantity <= other.max_quantity:
                    raise ValidationError(
                        f"Quantity range overlaps with existing tier: "
                        f"{other.min_quantity}-{other.max_quantity or '∞'}"
                    )
            elif other.max_quantity is None:
                # Other tier is unlimited
                if self.max_quantity >= other.min_quantity:
                    raise ValidationError(
                        f"Quantity range overlaps with existing tier: "
                        f"{other.min_quantity}-∞"
                    )
            else:
                # Both have limits, check for overlap
                if not (self.max_quantity < other.min_quantity or self.min_quantity > other.max_quantity):
                    raise ValidationError(
                        f"Quantity range overlaps with existing tier: "
                        f"{other.min_quantity}-{other.max_quantity}"
                    )
    
    @staticmethod
    def get_price_for_quantity(product, quantity):
        """
        Get the applicable unit price for a given quantity
        Returns the product's base selling_price if no bulk pricing applies
        """
        bulk_price = BulkPricing.objects.filter(
            product=product,
            is_active=True,
            min_quantity__lte=quantity
        ).filter(
            models.Q(max_quantity__gte=quantity) | models.Q(max_quantity__isnull=True)
        ).order_by('-min_quantity').first()
        
        if bulk_price:
            return bulk_price.unit_price
        
        return product.selling_price
