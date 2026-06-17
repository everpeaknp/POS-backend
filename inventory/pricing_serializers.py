"""
Serializers for Pricing Management (SRS 5.4)
"""

from rest_framework import serializers
from inventory.pricing_models import CustomerSpecificPrice, PriceHistory
from inventory.models import Product
from sales.models import Customer


class CustomerSpecificPriceSerializer(serializers.ModelSerializer):
    """Serializer for customer-specific pricing"""
    
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = CustomerSpecificPrice
        fields = [
            'id',
            'customer',
            'customer_name',
            'product',
            'product_name',
            'product_sku',
            'unit_price',
            'min_quantity',
            'valid_from',
            'valid_until',
            'is_active',
            'notes',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']
    
    def validate(self, data):
        """Validate customer-specific price"""
        # Check if customer and product belong to same tenant
        customer = data.get('customer')
        product = data.get('product')
        
        if customer and product:
            if customer.tenant != product.tenant:
                raise serializers.ValidationError(
                    "Customer and product must belong to the same organization"
                )
        
        # Validate date range
        valid_from = data.get('valid_from')
        valid_until = data.get('valid_until')
        
        if valid_until and valid_from and valid_until < valid_from:
            raise serializers.ValidationError({
                'valid_until': 'Valid until date must be after valid from date'
            })
        
        return data


class PriceHistorySerializer(serializers.ModelSerializer):
    """Serializer for price history (read-only)"""
    
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    changed_by_name = serializers.CharField(source='changed_by.get_full_name', read_only=True)
    
    # Calculated fields
    cost_price_change_amount = serializers.SerializerMethodField()
    selling_price_change_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = PriceHistory
        fields = [
            'id',
            'product',
            'product_name',
            'product_sku',
            'old_cost_price',
            'new_cost_price',
            'cost_price_change_amount',
            'cost_price_change_percent',
            'old_selling_price',
            'new_selling_price',
            'selling_price_change_amount',
            'selling_price_change_percent',
            'change_type',
            'change_reason',
            'changed_by',
            'changed_by_name',
            'effective_date',
            'created_at',
        ]
        read_only_fields = ['__all__']  # All fields are read-only
    
    def get_cost_price_change_amount(self, obj):
        """Calculate cost price change amount"""
        if obj.old_cost_price and obj.new_cost_price:
            return float(obj.new_cost_price - obj.old_cost_price)
        return None
    
    def get_selling_price_change_amount(self, obj):
        """Calculate selling price change amount"""
        if obj.old_selling_price and obj.new_selling_price:
            return float(obj.new_selling_price - obj.old_selling_price)
        return None


class ProductPricingDetailSerializer(serializers.ModelSerializer):
    """
    Extended product serializer with all pricing information
    """
    
    # Base pricing
    cost_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    selling_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    # Bulk pricing tiers
    bulk_prices = serializers.SerializerMethodField()
    
    # Customer-specific prices count
    customer_specific_prices_count = serializers.SerializerMethodField()
    
    # Recent price changes
    recent_price_changes = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'sku',
            'cost_price',
            'selling_price',
            'bulk_prices',
            'customer_specific_prices_count',
            'recent_price_changes',
        ]
    
    def get_bulk_prices(self, obj):
        """Get all bulk pricing tiers for this product"""
        from inventory.bulk_pricing_serializers import BulkPricingSerializer
        bulk_prices = obj.bulk_prices.filter(is_active=True).order_by('min_quantity')
        return BulkPricingSerializer(bulk_prices, many=True).data
    
    def get_customer_specific_prices_count(self, obj):
        """Count of active customer-specific prices"""
        return obj.customer_prices.filter(is_active=True).count()
    
    def get_recent_price_changes(self, obj):
        """Get last 5 price changes"""
        recent_changes = obj.price_history.all()[:5]
        return PriceHistorySerializer(recent_changes, many=True).data


class PriceCalculationSerializer(serializers.Serializer):
    """
    Serializer for price calculation requests
    Used to calculate the applicable price for a customer-product-quantity combination
    """
    
    product_id = serializers.IntegerField(required=True)
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        min_value=0.01
    )
    date = serializers.DateField(required=False, allow_null=True)
    
    # Response fields
    applicable_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    price_type = serializers.CharField(read_only=True)
    total_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    discount_from_base = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    discount_percent = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        read_only=True
    )
