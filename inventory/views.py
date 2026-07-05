from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from users.dynamic_permissions import DynamicModulePermission
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction, models
from django.db.models import Q, Sum, F
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
from .models import Category, UnitOfMeasure, Warehouse, Product, Stock, StockMovement
from .bulk_pricing_models import BulkPricing
from .serializers import (
    CategorySerializer, UnitOfMeasureSerializer, WarehouseSerializer,
    ProductListSerializer, ProductDetailSerializer, StockSerializer,
    StockMovementSerializer, StockAdjustmentSerializer, StockTransferSerializer,
    BulkPricingSerializer, BulkPricingCreateSerializer
)
from .permissions import IsSupervisorOrAdmin


@extend_schema_view(
    list=extend_schema(
        tags=['Inventory - Categories'],
        summary='List all categories',
        description='Get a paginated list of all product categories for the current tenant.',
    ),
    retrieve=extend_schema(
        tags=['Inventory - Categories'],
        summary='Get category details',
        description='Retrieve detailed information about a specific category.',
    ),
    create=extend_schema(
        tags=['Inventory - Categories'],
        summary='Create a new category',
        description='Create a new product category. Categories can be hierarchical.',
    ),
    update=extend_schema(
        tags=['Inventory - Categories'],
        summary='Update category',
        description='Update an existing category.',
    ),
    partial_update=extend_schema(
        tags=['Inventory - Categories'],
        summary='Partially update category',
        description='Partially update an existing category.',
    ),
    destroy=extend_schema(
        tags=['Inventory - Categories'],
        summary='Delete category',
        description='Delete a category. Cannot delete if it has child categories or products.',
    ),
)
class CategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing product categories.
    Supports hierarchical categories.
    """
    serializer_class = CategorySerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'inventory'
    filterset_fields = ['parent']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    
    def get_queryset(self):
        """Filter categories by current tenant"""
        try:
            if self.request.user and self.request.user.is_authenticated and self.request.user.tenant:
                return Category.objects.filter(tenant=self.request.user.tenant)
        except AttributeError:
            pass
        return Category.objects.none()
    
    def perform_create(self, serializer):
        """Ensure tenant is set when creating category"""
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['Inventory - Categories'],
        summary='Get category tree',
        description='Get all root categories with their hierarchical structure.',
    )
    @action(detail=False, methods=['get'])
    def tree(self, request):
        """Get categories in tree structure"""
        root_categories = self.get_queryset().filter(parent__isnull=True)
        serializer = self.get_serializer(root_categories, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        tags=['Inventory - Units'],
        summary='List all units of measure',
    ),
    retrieve=extend_schema(
        tags=['Inventory - Units'],
        summary='Get unit details',
    ),
    create=extend_schema(
        tags=['Inventory - Units'],
        summary='Create a new unit',
    ),
    update=extend_schema(
        tags=['Inventory - Units'],
        summary='Update unit',
    ),
    destroy=extend_schema(
        tags=['Inventory - Units'],
        summary='Delete unit',
    ),
)
class UnitOfMeasureViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing units of measure.
    """
    serializer_class = UnitOfMeasureSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'inventory'
    filterset_fields = ['type']
    search_fields = ['name', 'abbreviation']
    ordering_fields = ['name', 'type']
    
    def get_queryset(self):
        """Filter units by current tenant"""
        try:
            if self.request.user and self.request.user.is_authenticated and self.request.user.tenant:
                return UnitOfMeasure.objects.filter(tenant=self.request.user.tenant)
        except AttributeError:
            pass
        return UnitOfMeasure.objects.none()
    
    def perform_create(self, serializer):
        """Ensure tenant is set when creating unit"""
        serializer.save(tenant=self.request.user.tenant)


@extend_schema_view(
    list=extend_schema(
        tags=['Inventory - Warehouses'],
        summary='List all warehouses',
    ),
    retrieve=extend_schema(
        tags=['Inventory - Warehouses'],
        summary='Get warehouse details',
    ),
    create=extend_schema(
        tags=['Inventory - Warehouses'],
        summary='Create a new warehouse',
    ),
    update=extend_schema(
        tags=['Inventory - Warehouses'],
        summary='Update warehouse',
    ),
    destroy=extend_schema(
        tags=['Inventory - Warehouses'],
        summary='Delete warehouse',
    ),
)
class WarehouseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing warehouses/storage locations.
    """
    serializer_class = WarehouseSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'inventory'
    filterset_fields = ['is_active', 'manager']
    search_fields = ['name', 'location']
    ordering_fields = ['name', 'created_at']
    
    def get_queryset(self):
        """Filter warehouses by current tenant"""
        try:
            if self.request.user and self.request.user.is_authenticated and self.request.user.tenant:
                return Warehouse.objects.filter(tenant=self.request.user.tenant)
        except AttributeError:
            pass
        return Warehouse.objects.none()
    
    def perform_create(self, serializer):
        """Ensure tenant is set when creating warehouse"""
        serializer.save(tenant=self.request.user.tenant)

    @extend_schema(
        tags=['Inventory - Warehouses'],
        summary='Get warehouse stock summary',
        description='Get all products with stock in this warehouse.',
    )
    @action(detail=True, methods=['get'])
    def stock_summary(self, request, pk=None):
        """Get stock summary for a warehouse"""
        warehouse = self.get_object()
        stocks = warehouse.stocks.select_related('product', 'product__unit').filter(quantity__gt=0)
        serializer = StockSerializer(stocks, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        tags=['Inventory - Products'],
        summary='List all products',
        description='Get a paginated list of all products with basic information.',
    ),
    retrieve=extend_schema(
        tags=['Inventory - Products'],
        summary='Get product details',
        description='Get detailed information about a product including stock levels by warehouse.',
    ),
    create=extend_schema(
        tags=['Inventory - Products'],
        summary='Create a new product',
    ),
    update=extend_schema(
        tags=['Inventory - Products'],
        summary='Update product',
    ),
    destroy=extend_schema(
        tags=['Inventory - Products'],
        summary='Delete product',
    ),
)
class ProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing products.
    RBAC: Only ADMIN users can delete products.
    """
    permission_classes = [DynamicModulePermission]
    permission_module = 'inventory'
    filterset_fields = ['category', 'status']
    search_fields = ['name', 'sku', 'description']
    ordering_fields = ['name', 'sku', 'created_at']
    
    def get_queryset(self):
        """Filter products by current tenant"""
        # Explicitly filter by user's tenant to ensure proper scoping
        try:
            if self.request.user and self.request.user.is_authenticated and self.request.user.tenant:
                return Product.objects.filter(tenant=self.request.user.tenant).select_related('category', 'unit')
        except AttributeError:
            pass
        return Product.objects.none()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        return ProductDetailSerializer
    
    def create(self, request, *args, **kwargs):
        """Override create with tenant-aware validation"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"Creating product - User: {request.user.username}, Tenant: {request.user.tenant.name if request.user.tenant else 'None'}")
            logger.info(f"Request data: {request.data}")
            
            # The TenantManager automatically filters by current tenant,
            # so we just need to check if the category/unit exists
            category_id = request.data.get('category')
            unit_id = request.data.get('unit')
            
            if category_id:
                try:
                    from .models import Category
                    # This will raise DoesNotExist if category doesn't belong to current tenant
                    category = Category.objects.get(id=category_id)
                    logger.info(f"Category validated: {category.name} (ID: {category.id})")
                except Category.DoesNotExist:
                    logger.error(f"Category ID {category_id} not found for current tenant")
                    return Response(
                        {'category': ['Category not found. Please select a valid category.']},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            if unit_id:
                try:
                    from .models import UnitOfMeasure
                    # This will raise DoesNotExist if unit doesn't belong to current tenant
                    unit = UnitOfMeasure.objects.get(id=unit_id)
                    logger.info(f"Unit validated: {unit.name} (ID: {unit.id})")
                except UnitOfMeasure.DoesNotExist:
                    logger.error(f"Unit ID {unit_id} not found for current tenant")
                    return Response(
                        {'unit': ['Unit not found. Please select a valid unit.']},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            return super().create(request, *args, **kwargs)
            
        except Exception as e:
            logger.error(f"Error creating product: {str(e)}", exc_info=True)
            return Response(
                {
                    'detail': str(e),
                    'error_type': type(e).__name__
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def perform_create(self, serializer):
        """Ensure tenant is set when creating product"""
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['Inventory - Products'],
        summary='Get low stock products',
        description='Get all products where total stock is below the reorder level.',
    )
    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Get products with stock below reorder level"""
        products = self.get_queryset().annotate(
            total_stock=Sum('stocks__quantity')
        ).filter(
            Q(total_stock__lt=F('reorder_level')) | Q(total_stock__isnull=True)
        )
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        tags=['Inventory - Products'],
        summary='Get product stock history',
        description='Get the last 50 stock movements for this product.',
    )
    @action(detail=True, methods=['get'])
    def stock_history(self, request, pk=None):
        """Get stock movement history for a product"""
        product = self.get_object()
        movements = product.movements.select_related(
            'warehouse', 'from_warehouse', 'to_warehouse', 'performed_by'
        ).all()[:50]
        serializer = StockMovementSerializer(movements, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=['Inventory - Products'],
        summary='Get product activity',
        description='Stock movements plus linked purchase and sales orders for this product.',
    )
    @action(detail=True, methods=['get'])
    def activity(self, request, pk=None):
        """Get movements and linked purchase/sales documents for a product."""
        product = self.get_object()
        tenant = request.user.tenant

        movements = product.movements.select_related(
            'warehouse', 'from_warehouse', 'to_warehouse', 'performed_by'
        ).all()[:50]

        from purchase.models import PurchaseOrderLine
        from sales.models import SalesOrderLine

        po_lines = (
            PurchaseOrderLine.objects.filter(product=product, purchase_order__tenant=tenant)
            .select_related('purchase_order')
            .order_by('-purchase_order__date')[:20]
        )
        so_lines = (
            SalesOrderLine.objects.filter(product=product, sales_order__tenant=tenant)
            .select_related('sales_order')
            .order_by('-sales_order__date')[:20]
        )

        return Response({
            'movements': StockMovementSerializer(movements, many=True).data,
            'purchase_orders': [
                {
                    'id': line.purchase_order.id,
                    'po_number': line.purchase_order.po_number,
                    'date': line.purchase_order.date,
                    'status': line.purchase_order.status,
                    'quantity': line.quantity,
                    'received_quantity': line.received_quantity,
                }
                for line in po_lines
            ],
            'sales_orders': [
                {
                    'id': line.sales_order.id,
                    'order_number': line.sales_order.order_number,
                    'date': line.sales_order.date,
                    'status': line.sales_order.status,
                    'quantity': line.quantity,
                }
                for line in so_lines
            ],
        })


@extend_schema_view(
    list=extend_schema(
        tags=['Inventory - Stocks'],
        summary='List all stock levels',
        description='View current stock levels across all warehouses. Stock cannot be edited directly - use stock operations.',
    ),
    retrieve=extend_schema(
        tags=['Inventory - Stocks'],
        summary='Get stock details',
    ),
)
class StockViewSet(viewsets.ModelViewSet):
    """
    ViewSet for viewing stock levels.
    Stock is updated through stock operations, not direct editing.
    """
    serializer_class = StockSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'inventory'
    filterset_fields = ['product', 'warehouse']
    search_fields = ['product__name', 'product__sku', 'warehouse__name']
    ordering_fields = ['quantity', 'created_at']
    
    def get_queryset(self):
        """Filter stocks by current tenant"""
        try:
            if self.request.user and self.request.user.is_authenticated and self.request.user.tenant:
                return Stock.objects.filter(tenant=self.request.user.tenant).select_related('product', 'warehouse', 'product__unit')
        except AttributeError:
            pass
        return Stock.objects.none()
    
    # Disable create, update, delete - stock is managed through operations
    http_method_names = ['get', 'head', 'options']


@extend_schema_view(
    list=extend_schema(
        tags=['Inventory - Movements'],
        summary='List all stock movements',
        description='View immutable audit trail of all stock movements.',
    ),
    retrieve=extend_schema(
        tags=['Inventory - Movements'],
        summary='Get movement details',
    ),
)
class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing stock movement history.
    Movements are immutable - created through stock operations only.
    """
    serializer_class = StockMovementSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'inventory'
    filterset_fields = ['product', 'warehouse', 'movement_type']
    search_fields = ['product__name', 'product__sku', 'reason']
    ordering_fields = ['created_at']
    
    def get_queryset(self):
        """Filter movements by current tenant"""
        try:
            if self.request.user and self.request.user.is_authenticated and self.request.user.tenant:
                return StockMovement.objects.filter(tenant=self.request.user.tenant).select_related(
                    'product', 'warehouse', 'from_warehouse', 'to_warehouse', 'performed_by'
                )
        except AttributeError:
            pass
        return StockMovement.objects.none()


@extend_schema(tags=['Inventory - Operations'])
class StockOperationsViewSet(viewsets.ViewSet):
    """
    ViewSet for stock operations: in, out, transfer, adjustment.
    RBAC: Only SUPERVISOR or ADMIN users can create stock movements.
    """
    permission_classes = [IsSupervisorOrAdmin]
    
    @extend_schema(
        summary='Add stock to warehouse',
        description='Increase stock quantity in a warehouse. Creates a stock movement record.',
        request=StockAdjustmentSerializer,
        responses={201: {'description': 'Stock added successfully'}},
    )
    @action(detail=False, methods=['post'])
    def stock_in(self, request):
        """Add stock to warehouse"""
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            product = Product.objects.get(id=serializer.validated_data['product'])
            warehouse = Warehouse.objects.get(id=serializer.validated_data['warehouse'])
            quantity = serializer.validated_data['quantity']
            
            # Get tenant from request user
            tenant = request.user.tenant if hasattr(request.user, 'tenant') else None
            
            # Update or create stock with tenant
            stock, created = Stock.objects.get_or_create(
                product=product,
                warehouse=warehouse,
                tenant=tenant,
                defaults={'quantity': 0}
            )
            stock.quantity += quantity
            stock.save()
            
            # Get tenant from request user
            tenant = request.user.tenant if hasattr(request.user, 'tenant') else None
            
            # Create movement record with tenant
            StockMovement.objects.create(
                product=product,
                warehouse=warehouse,
                movement_type='in',
                quantity=quantity,
                reason=serializer.validated_data['reason'],
                notes=serializer.validated_data.get('notes', ''),
                performed_by=request.user,
                tenant=tenant
            )
        
        return Response({'message': 'Stock added successfully'}, status=status.HTTP_201_CREATED)
    
    @extend_schema(
        summary='Remove stock from warehouse',
        description='Decrease stock quantity in a warehouse. Validates sufficient stock is available.',
        request=StockAdjustmentSerializer,
        responses={
            200: {'description': 'Stock removed successfully'},
            400: {'description': 'Insufficient stock or validation error'}
        },
    )
    @action(detail=False, methods=['post'])
    def stock_out(self, request):
        """Remove stock from warehouse"""
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            product = Product.objects.get(id=serializer.validated_data['product'])
            warehouse = Warehouse.objects.get(id=serializer.validated_data['warehouse'])
            quantity = serializer.validated_data['quantity']
            
            # Get stock
            try:
                stock = Stock.objects.get(product=product, warehouse=warehouse)
            except Stock.DoesNotExist:
                return Response(
                    {'error': 'No stock available for this product in this warehouse'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if stock.quantity < quantity:
                return Response(
                    {'error': f'Insufficient stock. Available: {stock.quantity}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            stock.quantity -= quantity
            stock.save()
            
            # Get tenant from request user
            tenant = request.user.tenant if hasattr(request.user, 'tenant') else None
            
            # Create movement record with tenant
            StockMovement.objects.create(
                product=product,
                warehouse=warehouse,
                movement_type='out',
                quantity=quantity,
                reason=serializer.validated_data['reason'],
                notes=serializer.validated_data.get('notes', ''),
                performed_by=request.user,
                tenant=tenant
            )
        
        return Response({'message': 'Stock removed successfully'})

    @extend_schema(
        summary='Transfer stock between warehouses',
        description='Move stock from one warehouse to another. Validates sufficient stock in source warehouse.',
        request=StockTransferSerializer,
        responses={
            200: {'description': 'Stock transferred successfully'},
            400: {'description': 'Insufficient stock or validation error'}
        },
    )
    @action(detail=False, methods=['post'])
    def transfer(self, request):
        """Transfer stock between warehouses"""
        serializer = StockTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            product = Product.objects.get(id=serializer.validated_data['product'])
            from_warehouse = Warehouse.objects.get(id=serializer.validated_data['from_warehouse'])
            to_warehouse = Warehouse.objects.get(id=serializer.validated_data['to_warehouse'])
            quantity = serializer.validated_data['quantity']
            
            # Check source stock
            try:
                from_stock = Stock.objects.get(product=product, warehouse=from_warehouse)
            except Stock.DoesNotExist:
                return Response(
                    {'error': 'No stock available in source warehouse'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if from_stock.quantity < quantity:
                return Response(
                    {'error': f'Insufficient stock. Available: {from_stock.quantity}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Deduct from source
            from_stock.quantity -= quantity
            from_stock.save()
            
            # Get tenant from request user
            tenant = request.user.tenant if hasattr(request.user, 'tenant') else None
            
            # Add to destination with tenant
            to_stock, created = Stock.objects.get_or_create(
                product=product,
                warehouse=to_warehouse,
                tenant=tenant,
                defaults={'quantity': 0}
            )
            to_stock.quantity += quantity
            to_stock.save()
            
            # Create movement record with tenant
            StockMovement.objects.create(
                product=product,
                warehouse=from_warehouse,
                movement_type='transfer',
                quantity=quantity,
                from_warehouse=from_warehouse,
                to_warehouse=to_warehouse,
                notes=serializer.validated_data.get('notes', ''),
                performed_by=request.user,
                tenant=tenant
            )
        
        return Response({'message': 'Stock transferred successfully'})
    
    @extend_schema(
        summary='Adjust stock (correction)',
        description='Make a correction to stock levels. Can be positive or negative. Requires a reason.',
        request=StockAdjustmentSerializer,
        responses={
            200: {'description': 'Stock adjusted successfully'},
            400: {'description': 'Adjustment would result in negative stock'}
        },
    )
    @action(detail=False, methods=['post'])
    def adjustment(self, request):
        """Adjust stock (correction entry)"""
        import logging
        logger = logging.getLogger(__name__)
        
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            with transaction.atomic():
                product = Product.objects.get(id=serializer.validated_data['product'])
                warehouse = Warehouse.objects.get(id=serializer.validated_data['warehouse'])
                quantity = serializer.validated_data['quantity']
                
                # Get tenant from request user
                tenant = request.user.tenant if hasattr(request.user, 'tenant') else None
                
                if not tenant:
                    logger.error(f"No tenant found for user: {request.user.username}")
                    return Response(
                        {'error': 'User is not associated with a tenant'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                logger.info(f"Adjusting stock - Product: {product.id}, Warehouse: {warehouse.id}, Tenant: {tenant.id}, Quantity: {quantity}")
                
                # Get or create stock with tenant
                stock, created = Stock.objects.get_or_create(
                    product=product,
                    warehouse=warehouse,
                    tenant=tenant,
                    defaults={'quantity': 0}
                )
                
                logger.info(f"Stock {'created' if created else 'found'}: {stock.id}, Current quantity: {stock.quantity}")
                
                # Adjustment can be positive or negative
                stock.quantity += quantity
                if stock.quantity < 0:
                    return Response(
                        {'error': 'Adjustment would result in negative stock'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                stock.save()
                
                logger.info(f"Stock updated to: {stock.quantity}")
                
                # Create movement record with tenant
                StockMovement.objects.create(
                    product=product,
                    warehouse=warehouse,
                    movement_type='adjustment',
                    quantity=quantity,
                    reason=serializer.validated_data['reason'],
                    notes=serializer.validated_data.get('notes', ''),
                    performed_by=request.user,
                    tenant=tenant
                )
                
                logger.info("Stock adjustment completed successfully")
            
            return Response({'message': 'Stock adjusted successfully'})
            
        except Product.DoesNotExist:
            logger.error(f"Product not found: {serializer.validated_data['product']}")
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Warehouse.DoesNotExist:
            logger.error(f"Warehouse not found: {serializer.validated_data['warehouse']}")
            return Response(
                {'error': 'Warehouse not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error adjusting stock: {str(e)}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



@extend_schema_view(
    list=extend_schema(
        tags=['Inventory - Reports'],
        summary='Inventory Reports',
        description='Get comprehensive inventory reports including stock summary, low stock, valuation, and movement',
    ),
)
class InventoryReportsViewSet(viewsets.ViewSet):
    """
    ViewSet for inventory reporting and analytics.
    Provides stock summary, low stock alerts, valuation, and movement reports.
    """
    permission_classes = [DynamicModulePermission]
    permission_module = 'inventory'
    
    def get_tenant(self):
        """Get current user's tenant"""
        return self.request.user.tenant
    
    @extend_schema(
        tags=['Inventory - Reports'],
        summary='Stock Summary Report',
        description='Get overall stock summary with total products, units, low stock, and out of stock counts',
    )
    @action(detail=False, methods=['get'], url_path='stock-summary')
    def stock_summary(self, request):
        """Stock summary with counts and chart data"""
        from django.db.models import Sum, Count, Q, F, DecimalField, Value
        from django.db.models.functions import Coalesce
        from decimal import Decimal
        
        tenant = self.get_tenant()
        
        # Get all products with their total stock
        products = Product.objects.filter(tenant=tenant).annotate(
            total_stock=Coalesce(Sum('stocks__quantity'), Value(Decimal('0.00')))
        )
        
        # Calculate summary stats
        total_products = products.count()
        total_units = products.aggregate(
            total=Coalesce(Sum('stocks__quantity'), Value(Decimal('0.00')))
        )['total']
        
        low_stock_count = products.filter(
            total_stock__lte=F('reorder_level'),
            total_stock__gt=0
        ).count()
        
        out_of_stock_count = products.filter(total_stock=0).count()
        
        # Get stock by product for chart (top 10 products by stock)
        stock_data = []
        top_products = products.order_by('-total_stock')[:10]
        for product in top_products:
            stock_data.append({
                'name': product.sku,
                'stock': float(product.total_stock)
            })
        
        return Response({
            'summary': {
                'total_products': total_products,
                'total_units': float(total_units),
                'low_stock': low_stock_count,
                'out_of_stock': out_of_stock_count,
            },
            'stock_data': stock_data,
        })
    
    @extend_schema(
        tags=['Inventory - Reports'],
        summary='Low Stock Report',
        description='Get list of products with stock at or below reorder level',
    )
    @action(detail=False, methods=['get'], url_path='low-stock')
    def low_stock(self, request):
        """Products with low stock or out of stock"""
        from django.db.models import Sum, F, DecimalField, Value
        from django.db.models.functions import Coalesce
        from decimal import Decimal
        
        tenant = self.get_tenant()
        
        # Get products with low stock
        products = Product.objects.filter(tenant=tenant).annotate(
            total_stock=Coalesce(Sum('stocks__quantity'), Value(Decimal('0.00')))
        ).filter(
            total_stock__lte=F('reorder_level')
        ).select_related('category', 'unit').order_by('total_stock')
        
        low_stock_items = []
        for product in products:
            shortage = max(0, product.reorder_level - product.total_stock)
            status_label = "Out of Stock" if product.total_stock == 0 else "Low Stock"
            
            low_stock_items.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'current_stock': float(product.total_stock),
                'reorder_level': float(product.reorder_level),
                'shortage': float(shortage),
                'status': status_label,
                'category': product.category.name if product.category else None,
                'unit': product.unit.name if product.unit else 'unit',
            })
        
        return Response({
            'items': low_stock_items,
            'total_count': len(low_stock_items),
        })
    
    @extend_schema(
        tags=['Inventory - Reports'],
        summary='Inventory Valuation Report',
        description='Get inventory valuation with cost price and selling price calculations',
    )
    @action(detail=False, methods=['get'], url_path='valuation')
    def valuation(self, request):
        """Inventory valuation by product"""
        from django.db.models import Sum, F, DecimalField, Value
        from django.db.models.functions import Coalesce
        from decimal import Decimal
        
        tenant = self.get_tenant()
        
        # Get products with stock and calculate values
        products = Product.objects.filter(tenant=tenant).annotate(
            total_stock=Coalesce(Sum('stocks__quantity'), Value(Decimal('0.00')))
        ).filter(total_stock__gt=0).select_related('category', 'unit')
        
        valuation_items = []
        total_cost_value = Decimal('0.00')
        total_sale_value = Decimal('0.00')
        
        # Valuation data for chart (top 10 by value)
        valuation_data = []
        
        for product in products:
            cost_value = product.total_stock * product.cost_price
            sale_value = product.total_stock * product.selling_price
            
            total_cost_value += cost_value
            total_sale_value += sale_value
            
            valuation_items.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'stock': float(product.total_stock),
                'cost_price': float(product.cost_price),
                'selling_price': float(product.selling_price),
                'total_cost_value': float(cost_value),
                'total_sale_value': float(sale_value),
                'unit': product.unit.name if product.unit else 'unit',
            })
        
        # Sort by cost value and get top 10 for chart
        valuation_items_sorted = sorted(valuation_items, key=lambda x: x['total_cost_value'], reverse=True)
        for item in valuation_items_sorted[:10]:
            valuation_data.append({
                'name': item['sku'],
                'value': item['total_cost_value']
            })
        
        return Response({
            'summary': {
                'total_cost_value': float(total_cost_value),
                'total_sale_value': float(total_sale_value),
                'potential_profit': float(total_sale_value - total_cost_value),
            },
            'items': valuation_items,
            'valuation_data': valuation_data,
        })
    
    @extend_schema(
        tags=['Inventory - Reports'],
        summary='Stock Movement Report',
        description='Get stock movement summary showing opening, in, out, and closing stock',
        parameters=[
            OpenApiParameter('start_date', str, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('end_date', str, description='End date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='movement')
    def movement(self, request):
        """Stock movement report with opening and closing balances"""
        from django.db.models import Sum, Q, F, DecimalField, Value
        from django.db.models.functions import Coalesce
        from decimal import Decimal
        from datetime import datetime
        
        tenant = self.get_tenant()
        
        # Parse date parameters
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Get all products with current stock
        products = Product.objects.filter(tenant=tenant).annotate(
            current_stock=Coalesce(Sum('stocks__quantity'), Value(Decimal('0.00')))
        ).select_related('category', 'unit')
        
        movement_items = []
        
        for product in products:
            # Get movements for the period
            movements_qs = StockMovement.objects.filter(
                tenant=tenant,
                product=product
            )
            
            if start_date:
                movements_qs = movements_qs.filter(date__gte=start_date)
            if end_date:
                movements_qs = movements_qs.filter(date__lte=end_date)
            
            # Calculate in and out quantities
            in_qty = movements_qs.filter(
                movement_type__in=['in', 'adjustment']
            ).filter(quantity__gt=0).aggregate(
                total=Coalesce(Sum('quantity'), Value(Decimal('0.00')))
            )['total']
            
            out_qty = movements_qs.filter(
                Q(movement_type='out') | Q(movement_type='adjustment', quantity__lt=0)
            ).aggregate(
                total=Coalesce(Sum('quantity'), Value(Decimal('0.00')))
            )['total']
            
            # Make out_qty positive for display
            out_qty = abs(out_qty)
            
            # Calculate opening stock (current - in + out)
            opening = product.current_stock - in_qty + out_qty
            closing = product.current_stock
            
            movement_items.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'category': product.category.name if product.category else None,
                'opening': float(opening),
                'in': float(in_qty),
                'out': float(out_qty),
                'closing': float(closing),
                'unit': product.unit.name if product.unit else 'unit',
            })
        
        return Response({
            'items': movement_items,
            'period': {
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
            }
        })



# ============================================================================
# BULK PRICING VIEWSET
# ============================================================================

from .serializers import BulkPricingSerializer, BulkPricingCreateSerializer

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
    permission_classes = [DynamicModulePermission]
    permission_module = 'inventory'
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
