from rest_framework import serializers
from decimal import Decimal
from .bulk_pricing_models import BulkPricing


class BulkPricingSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    
    class Meta:
        model = BulkPricing
        fields = [
            'id', 'product', 'product_name', 'product_sku',
            'min_quantity', 'max_quantity', 'unit_price', 'discount_percent',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'product_name', 'product_sku']
    
    def validate(self, data):
        """Validate quantity ranges"""
        min_qty = data.get('min_quantity')
        max_qty = data.get('max_quantity')
        
        if max_qty and max_qty < min_qty:
            raise serializers.ValidationError({
                'max_quantity': 'Maximum quantity must be greater than minimum quantity'
            })
        
        return data


class BulkPricingCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating bulk pricing tiers"""
    
    class Meta:
        model = BulkPricing
        fields = [
            'product', 'min_quantity', 'max_quantity', 
            'unit_price', 'discount_percent', 'is_active'
        ]
    
    def validate(self, data):
        """Validate quantity ranges and check for overlaps"""
        min_qty = data.get('min_quantity')
        max_qty = data.get('max_quantity')
        product = data.get('product')
        
        if max_qty and max_qty < min_qty:
            raise serializers.ValidationError({
                'max_quantity': 'Maximum quantity must be greater than minimum quantity'
            })
        
        # Check for overlapping ranges (excluding current instance if updating)
        instance_id = self.instance.id if self.instance else None
        overlapping = BulkPricing.objects.filter(
            tenant=self.context['request'].user.tenant,
            product=product,
            is_active=True
        ).exclude(id=instance_id)
        
        for other in overlapping:
            # Check if ranges overlap
            if max_qty is None:
                # This tier is unlimited
                if other.max_quantity is None or min_qty <= other.max_quantity:
                    raise serializers.ValidationError({
                        'min_quantity': f'Quantity range overlaps with existing tier: {other.min_quantity}-{other.max_quantity or "∞"}'
                    })
            elif other.max_quantity is None:
                # Other tier is unlimited
                if max_qty >= other.min_quantity:
                    raise serializers.ValidationError({
                        'max_quantity': f'Quantity range overlaps with existing tier: {other.min_quantity}-∞'
                    })
            else:
                # Both have limits, check for overlap
                if not (max_qty < other.min_quantity or min_qty > other.max_quantity):
                    raise serializers.ValidationError({
                        'min_quantity': f'Quantity range overlaps with existing tier: {other.min_quantity}-{other.max_quantity}'
                    })
        
        return data
    
    def create(self, validated_data):
        """Create bulk pricing with tenant"""
        validated_data['tenant'] = self.context['request'].user.tenant
        return super().create(validated_data)
