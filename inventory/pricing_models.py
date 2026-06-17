"""
Pricing Management Models for SRS 5.4
- Customer-specific pricing
- Price history tracking
"""

from django.db import models
from django.core.exceptions import ValidationError
from decimal import Decimal
from utils.models import TenantModel


class CustomerSpecificPrice(TenantModel):
    """
    Special pricing for specific customers (loyal customer discounts, negotiated rates)
    Overrides both base price and bulk pricing for the specified customer
    """
    customer = models.ForeignKey(
        'sales.Customer',
        on_delete=models.CASCADE,
        related_name='special_prices'
    )
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.CASCADE,
        related_name='customer_prices'
    )
    
    # Special price for this customer
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Special price per unit for this customer"
    )
    
    # Optional: Minimum quantity for this price to apply
    min_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        help_text="Minimum quantity required (default: 1)"
    )
    
    # Validity period
    valid_from = models.DateField(
        help_text="Date from which this price is valid"
    )
    valid_until = models.DateField(
        null=True,
        blank=True,
        help_text="Date until which this price is valid (null = no expiry)"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Notes
    notes = models.TextField(
        blank=True,
        help_text="Reason for special pricing (e.g., 'Loyal customer discount', 'Negotiated rate')"
    )
    
    # Audit
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_customer_prices'
    )
    
    class Meta:
        db_table = 'customer_specific_prices'
        ordering = ['customer', 'product']
        unique_together = [['tenant', 'customer', 'product']]
        indexes = [
            models.Index(fields=['customer', 'product']),
            models.Index(fields=['tenant', 'customer']),
            models.Index(fields=['valid_from', 'valid_until']),
        ]
    
    def __str__(self):
        return f"{self.customer.name} - {self.product.name}: Rs {self.unit_price}"
    
    def clean(self):
        """Validate date ranges"""
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValidationError("Valid until date must be after valid from date")
    
    def is_valid_on_date(self, date):
        """Check if this price is valid on a specific date"""
        if not self.is_active:
            return False
        
        if date < self.valid_from:
            return False
        
        if self.valid_until and date > self.valid_until:
            return False
        
        return True
    
    @staticmethod
    def get_price_for_customer(customer, product, quantity, date=None):
        """
        Get the applicable price for a customer-product combination
        Returns None if no customer-specific price applies
        """
        from django.utils import timezone
        
        if date is None:
            date = timezone.now().date()
        
        customer_price = CustomerSpecificPrice.objects.filter(
            customer=customer,
            product=product,
            is_active=True,
            valid_from__lte=date,
            min_quantity__lte=quantity
        ).filter(
            models.Q(valid_until__gte=date) | models.Q(valid_until__isnull=True)
        ).order_by('-min_quantity').first()
        
        if customer_price:
            return customer_price.unit_price
        
        return None


class PriceHistory(TenantModel):
    """
    Immutable audit trail of all price changes
    Tracks when prices changed and by how much
    """
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.CASCADE,
        related_name='price_history'
    )
    
    # Price change details
    old_cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    new_cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    old_selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    new_selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Change metadata
    change_type = models.CharField(
        max_length=50,
        choices=[
            ('cost_price', 'Cost Price Change'),
            ('selling_price', 'Selling Price Change'),
            ('both', 'Both Prices Changed'),
        ]
    )
    
    change_reason = models.TextField(
        blank=True,
        help_text="Reason for price change (e.g., 'Supplier price increase', 'Promotional discount')"
    )
    
    # Percentage changes (calculated)
    cost_price_change_percent = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percentage change in cost price"
    )
    
    selling_price_change_percent = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percentage change in selling price"
    )
    
    # Audit
    changed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='price_changes'
    )
    
    # Effective date (when the price change takes effect)
    effective_date = models.DateField(
        help_text="Date when this price change becomes effective"
    )
    
    class Meta:
        db_table = 'price_history'
        ordering = ['-effective_date', '-created_at']
        indexes = [
            models.Index(fields=['product', '-effective_date']),
            models.Index(fields=['tenant', 'product']),
            models.Index(fields=['effective_date']),
        ]
    
    def __str__(self):
        return f"{self.product.name} - {self.change_type} on {self.effective_date}"
    
    def save(self, *args, **kwargs):
        """Calculate percentage changes before saving"""
        # Calculate cost price change percentage
        if self.old_cost_price and self.new_cost_price and self.old_cost_price != 0:
            change = self.new_cost_price - self.old_cost_price
            self.cost_price_change_percent = (change / self.old_cost_price) * 100
        
        # Calculate selling price change percentage
        if self.old_selling_price and self.new_selling_price and self.old_selling_price != 0:
            change = self.new_selling_price - self.old_selling_price
            self.selling_price_change_percent = (change / self.old_selling_price) * 100
        
        super().save(*args, **kwargs)
    
    @staticmethod
    def create_from_product_change(product, old_cost, old_selling, reason='', changed_by=None, effective_date=None):
        """
        Create a price history entry when a product's price changes
        """
        from django.utils import timezone
        
        if effective_date is None:
            effective_date = timezone.now().date()
        
        # Determine change type
        cost_changed = old_cost != product.cost_price
        selling_changed = old_selling != product.selling_price
        
        if not cost_changed and not selling_changed:
            return None  # No change
        
        if cost_changed and selling_changed:
            change_type = 'both'
        elif cost_changed:
            change_type = 'cost_price'
        else:
            change_type = 'selling_price'
        
        return PriceHistory.objects.create(
            tenant=product.tenant,
            product=product,
            old_cost_price=old_cost if cost_changed else None,
            new_cost_price=product.cost_price if cost_changed else None,
            old_selling_price=old_selling if selling_changed else None,
            new_selling_price=product.selling_price if selling_changed else None,
            change_type=change_type,
            change_reason=reason,
            changed_by=changed_by,
            effective_date=effective_date
        )
