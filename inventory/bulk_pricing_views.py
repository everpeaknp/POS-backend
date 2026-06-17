from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import extend_schema, extend_schema_view
from django.db import models

from .models import BulkPricing
from .bulk_pricing_serializers import BulkPricingSerializer, BulkPricingCreateSerializer


@extend_schema_view(
    list=extend_schema(tags=['Inventory - Bulk Pricing'], summary='List bulk pricing tiers'),
    retrieve=extend_schema(tags=['Inventory - Bulk Pricing'], summary='Get bulk pricing tier details'),
    create=extend_schema(tags=['Inventory - Bulk Pricing'], summary='Create bulk pricing tier'),
    update=extend_schema(tags=['Inventory - Bulk Pricing'], summary='Update bulk pricing tier'),
    partial_update=extend_schema(tags=['Inventory - Bulk Pricing'], summary='Partially update bulk pricing tier'),
    destroy=extend_schema(tags=['Inventory - Bulk Pricing'], summary='Delete bulk pricing tier'),
)
class BulkPricingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing bulk pricing tiers
    Allows creating tiered pricing based on quantity ranges
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['product', 'is_active']
    search_fields = ['product__name', 'product__sku']
    ordering_fields = ['min_quantity', 'unit_price', 'created_at']
    ordering = ['product', 'min_quantity']
    
    def get_queryset(self):
        """Filter by current tenant"""
        if not self.request.user.tenant:
            return BulkPricing.objects.none()
        return BulkPricing.objects.filter(
            tenant=self.request.user.tenant
        ).select_related('product')
    
    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action in ['create', 'update', 'partial_update']:
            return BulkPricingCreateSerializer
        return BulkPricingSerializer
    
    def perform_create(self, serializer):
        """Assign tenant when creating"""
        if not self.request.user.tenant:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'You must be assigned to an organization to create bulk pricing.'})
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['Inventory - Bulk Pricing'],
        summary='Get price for quantity',
        description='Get the applicable unit price for a product at a given quantity',
        responses={200: {'type': 'object', 'properties': {
            'product_id': {'type': 'integer'},
            'quantity': {'type': 'number'},
            'unit_price': {'type': 'number'},
            'bulk_pricing_applied': {'type': 'boolean'},
            'tier': {'type': 'object'}
        }}}
    )
    @action(detail=False, methods=['get'], url_path='get-price')
    def get_price(self, request):
        """
        Get the applicable price for a product at a given quantity
        Query params: product_id, quantity
        """
        product_id = request.query_params.get('product_id')
        quantity = request.query_params.get('quantity')
        
        if not product_id or not quantity:
            return Response(
                {'error': 'product_id and quantity are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from .models import Product
            from decimal import Decimal
            
            product = Product.objects.get(
                id=product_id,
                tenant=request.user.tenant
            )
            quantity = Decimal(quantity)
            
            # Get applicable bulk pricing
            bulk_price = BulkPricing.objects.filter(
                product=product,
                tenant=request.user.tenant,
                is_active=True,
                min_quantity__lte=quantity
            ).filter(
                models.Q(max_quantity__gte=quantity) | models.Q(max_quantity__isnull=True)
            ).order_by('-min_quantity').first()
            
            if bulk_price:
                return Response({
                    'product_id': product.id,
                    'product_name': product.name,
                    'quantity': float(quantity),
                    'unit_price': float(bulk_price.unit_price),
                    'bulk_pricing_applied': True,
                    'tier': {
                        'id': bulk_price.id,
                        'min_quantity': float(bulk_price.min_quantity),
                        'max_quantity': float(bulk_price.max_quantity) if bulk_price.max_quantity else None,
                        'discount_percent': float(bulk_price.discount_percent)
                    }
                })
            else:
                return Response({
                    'product_id': product.id,
                    'product_name': product.name,
                    'quantity': float(quantity),
                    'unit_price': float(product.selling_price),
                    'bulk_pricing_applied': False,
                    'tier': None
                })
        
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(
        tags=['Inventory - Bulk Pricing'],
        summary='Get all tiers for a product',
        description='Get all bulk pricing tiers for a specific product',
    )
    @action(detail=False, methods=['get'], url_path='by-product/(?P<product_id>[^/.]+)')
    def by_product(self, request, product_id=None):
        """Get all bulk pricing tiers for a specific product"""
        tiers = self.get_queryset().filter(product_id=product_id)
        serializer = self.get_serializer(tiers, many=True)
        return Response(serializer.data)

