"""
Views for Pricing Management (SRS 5.4)
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from users.dynamic_permissions import DynamicModulePermission
from django.utils import timezone
from decimal import Decimal

from inventory.pricing_models import CustomerSpecificPrice, PriceHistory
from inventory.pricing_serializers import (
    CustomerSpecificPriceSerializer,
    PriceHistorySerializer,
    ProductPricingDetailSerializer,
    PriceCalculationSerializer
)
from inventory.models import Product
from sales.models import Customer


class CustomerSpecificPriceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing customer-specific pricing
    
    Endpoints:
    - GET /api/inventory/customer-prices/ - List all customer-specific prices
    - POST /api/inventory/customer-prices/ - Create new customer-specific price
    - GET /api/inventory/customer-prices/{id}/ - Get specific price
    - PATCH /api/inventory/customer-prices/{id}/ - Update price
    - DELETE /api/inventory/customer-prices/{id}/ - Delete price
    - GET /api/inventory/customer-prices/by_customer/{customer_id}/ - Get all prices for a customer
    - GET /api/inventory/customer-prices/by_product/{product_id}/ - Get all customers with special prices for a product
    """
    
    serializer_class = CustomerSpecificPriceSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'inventory'
    
    def get_queryset(self):
        """Filter by tenant"""
        return CustomerSpecificPrice.objects.filter(
            tenant=self.request.user.tenant
        ).select_related('customer', 'product', 'created_by')
    
    def perform_create(self, serializer):
        """Set tenant and created_by on creation"""
        serializer.save(
            tenant=self.request.user.tenant,
            created_by=self.request.user
        )
    
    @action(detail=False, methods=['get'], url_path='by_customer/(?P<customer_id>[^/.]+)')
    def by_customer(self, request, customer_id=None):
        """Get all special prices for a specific customer"""
        prices = self.get_queryset().filter(
            customer_id=customer_id,
            is_active=True
        )
        serializer = self.get_serializer(prices, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='by_product/(?P<product_id>[^/.]+)')
    def by_product(self, request, product_id=None):
        """Get all customers with special prices for a specific product"""
        prices = self.get_queryset().filter(
            product_id=product_id,
            is_active=True
        )
        serializer = self.get_serializer(prices, many=True)
        return Response(serializer.data)


class PriceHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for price history
    
    Endpoints:
    - GET /api/inventory/price-history/ - List all price changes
    - GET /api/inventory/price-history/{id}/ - Get specific price change
    - GET /api/inventory/price-history/by_product/{product_id}/ - Get price history for a product
    - GET /api/inventory/price-history/recent/ - Get recent price changes across all products
    """
    
    serializer_class = PriceHistorySerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'inventory'
    
    def get_queryset(self):
        """Filter by tenant"""
        return PriceHistory.objects.filter(
            tenant=self.request.user.tenant
        ).select_related('product', 'changed_by')
    
    @action(detail=False, methods=['get'], url_path='by_product/(?P<product_id>[^/.]+)')
    def by_product(self, request, product_id=None):
        """Get complete price history for a specific product"""
        history = self.get_queryset().filter(product_id=product_id)
        
        # Optional date range filtering
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if start_date:
            history = history.filter(effective_date__gte=start_date)
        if end_date:
            history = history.filter(effective_date__lte=end_date)
        
        serializer = self.get_serializer(history, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent price changes across all products (last 30 days)"""
        from datetime import timedelta
        
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        recent_changes = self.get_queryset().filter(
            effective_date__gte=thirty_days_ago
        )[:50]  # Limit to 50 most recent
        
        serializer = self.get_serializer(recent_changes, many=True)
        return Response(serializer.data)


class ProductPricingViewSet(viewsets.GenericViewSet):
    """
    ViewSet for product pricing operations
    
    Endpoints:
    - GET /api/inventory/product-pricing/{product_id}/ - Get complete pricing info for a product
    - POST /api/inventory/product-pricing/calculate/ - Calculate price for customer-product-quantity
    - POST /api/inventory/product-pricing/bulk_calculate/ - Calculate prices for multiple items
    """
    
    permission_classes = [DynamicModulePermission]
    permission_module = 'inventory'
    
    def get_queryset(self):
        """Filter products by tenant"""
        return Product.objects.filter(tenant=self.request.user.tenant)
    
    @action(detail=False, methods=['get'], url_path='(?P<product_id>[^/.]+)')
    def get_pricing_detail(self, request, product_id=None):
        """Get complete pricing information for a product"""
        try:
            product = self.get_queryset().get(id=product_id)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ProductPricingDetailSerializer(product)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def calculate(self, request):
        """
        Calculate the applicable price for a customer-product-quantity combination
        
        Request body:
        {
            "product_id": 1,
            "customer_id": 2,  // optional
            "quantity": 100,
            "date": "2026-03-30"  // optional, defaults to today
        }
        
        Response:
        {
            "applicable_price": 95.00,
            "price_type": "bulk_pricing",  // or "customer_specific", "base_price"
            "total_amount": 9500.00,
            "discount_from_base": 500.00,
            "discount_percent": 5.00
        }
        """
        serializer = PriceCalculationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = serializer.validated_data['product_id']
        customer_id = serializer.validated_data.get('customer_id')
        quantity = serializer.validated_data['quantity']
        date = serializer.validated_data.get('date') or timezone.now().date()
        
        # Get product
        try:
            product = self.get_queryset().get(id=product_id)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get customer if provided
        customer = None
        if customer_id:
            try:
                customer = Customer.objects.get(
                    id=customer_id,
                    tenant=request.user.tenant
                )
            except Customer.DoesNotExist:
                return Response(
                    {'error': 'Customer not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Calculate price
        if customer:
            applicable_price = product.get_price_for_customer(customer, quantity, date)
            
            # Determine price type
            from inventory.pricing_models import CustomerSpecificPrice
            customer_price = CustomerSpecificPrice.get_price_for_customer(
                customer, product, quantity, date
            )
            if customer_price is not None:
                price_type = 'customer_specific'
            elif applicable_price != product.selling_price:
                price_type = 'bulk_pricing'
            else:
                price_type = 'base_price'
        else:
            # No customer, check bulk pricing only
            from inventory.bulk_pricing_models import BulkPricing
            applicable_price = BulkPricing.get_price_for_quantity(product, quantity)
            price_type = 'bulk_pricing' if applicable_price != product.selling_price else 'base_price'
        
        # Calculate totals and discounts
        total_amount = applicable_price * quantity
        base_total = product.selling_price * quantity
        discount_from_base = base_total - total_amount
        discount_percent = (discount_from_base / base_total * 100) if base_total > 0 else Decimal('0')
        
        return Response({
            'product_id': product.id,
            'product_name': product.name,
            'product_sku': product.sku,
            'customer_id': customer.id if customer else None,
            'customer_name': customer.name if customer else None,
            'quantity': float(quantity),
            'applicable_price': float(applicable_price),
            'price_type': price_type,
            'total_amount': float(total_amount),
            'base_price': float(product.selling_price),
            'base_total': float(base_total),
            'discount_from_base': float(discount_from_base),
            'discount_percent': float(discount_percent),
            'date': date.isoformat()
        })
    
    @action(detail=False, methods=['post'])
    def bulk_calculate(self, request):
        """
        Calculate prices for multiple items at once
        
        Request body:
        {
            "customer_id": 2,  // optional
            "date": "2026-03-30",  // optional
            "items": [
                {"product_id": 1, "quantity": 100},
                {"product_id": 2, "quantity": 50}
            ]
        }
        
        Response:
        {
            "items": [...],  // array of price calculations
            "summary": {
                "total_items": 2,
                "total_quantity": 150,
                "total_amount": 15000.00,
                "total_discount": 500.00
            }
        }
        """
        customer_id = request.data.get('customer_id')
        date = request.data.get('date')
        items = request.data.get('items', [])
        
        if not items:
            return Response(
                {'error': 'No items provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get customer if provided
        customer = None
        if customer_id:
            try:
                customer = Customer.objects.get(
                    id=customer_id,
                    tenant=request.user.tenant
                )
            except Customer.DoesNotExist:
                return Response(
                    {'error': 'Customer not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Calculate price for each item
        results = []
        total_amount = Decimal('0')
        total_discount = Decimal('0')
        total_quantity = Decimal('0')
        
        for item in items:
            product_id = item.get('product_id')
            quantity = Decimal(str(item.get('quantity', 1)))
            
            try:
                product = self.get_queryset().get(id=product_id)
            except Product.DoesNotExist:
                results.append({
                    'product_id': product_id,
                    'error': 'Product not found'
                })
                continue
            
            # Calculate price
            if customer:
                applicable_price = product.get_price_for_customer(customer, quantity, date)
            else:
                from inventory.bulk_pricing_models import BulkPricing
                applicable_price = BulkPricing.get_price_for_quantity(product, quantity)
            
            item_total = applicable_price * quantity
            base_total = product.selling_price * quantity
            item_discount = base_total - item_total
            
            results.append({
                'product_id': product.id,
                'product_name': product.name,
                'quantity': float(quantity),
                'applicable_price': float(applicable_price),
                'total_amount': float(item_total),
                'discount': float(item_discount)
            })
            
            total_amount += item_total
            total_discount += item_discount
            total_quantity += quantity
        
        return Response({
            'items': results,
            'summary': {
                'total_items': len(results),
                'total_quantity': float(total_quantity),
                'total_amount': float(total_amount),
                'total_discount': float(total_discount)
            }
        })
