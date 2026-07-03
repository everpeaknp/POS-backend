"""
POS Views for API endpoints
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from django.http import Http404
from django.db.models import Sum, Count, Q, F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal

from users.dynamic_permissions import DynamicModulePermission
from tenants.utils import get_request_tenant
from .models import POSSession, POSDiscount, POSTransaction, POSTransactionLine, POSDailySalesReport
from .serializers import (
    POSSessionSerializer, POSDiscountSerializer, POSTransactionSerializer, POSTransactionCreateSerializer,
    POSDailySalesReportSerializer, ProductSearchSerializer
)
from inventory.models import Product


@extend_schema_view(
    list=extend_schema(description="List all POS sessions", tags=["POS - Sessions"]),
    retrieve=extend_schema(description="Get session details", tags=["POS - Sessions"]),
    create=extend_schema(description="Open a new POS session", tags=["POS - Sessions"]),
    update=extend_schema(description="Update session", tags=["POS - Sessions"]),
    partial_update=extend_schema(description="Partially update session", tags=["POS - Sessions"]),
    destroy=extend_schema(description="Delete a session", tags=["POS - Sessions"]),
)
class POSSessionViewSet(viewsets.ModelViewSet):
    """ViewSet for POS Session management"""
    permission_classes = [DynamicModulePermission]
    permission_module = 'pos'
    serializer_class = POSSessionSerializer
    filterset_fields = ['status', 'cashier']
    search_fields = ['session_number', 'cashier__username']
    ordering_fields = ['opened_at', 'closed_at']
    ordering = ['-opened_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            return POSSession.objects.none()
        # Use _base_manager to avoid TenantManager double-filtering
        return POSSession._base_manager.filter(
            tenant=tenant
        ).select_related('cashier', 'warehouse')

    def get_object(self):
        """Retrieve by numeric pk or session_number (e.g. SES-0001)."""
        lookup = self.kwargs.get(self.lookup_url_kwarg or self.lookup_field)
        queryset = self.filter_queryset(self.get_queryset())
        if not lookup:
            raise Http404

        lookup_str = str(lookup)
        if lookup_str.upper().startswith('SES-'):
            return get_object_or_404(queryset, session_number=lookup_str)

        if lookup_str.isdigit():
            return get_object_or_404(queryset, pk=int(lookup_str))

        raise Http404

    def create(self, request, *args, **kwargs):
        tenant = get_request_tenant(request.user)
        if not tenant:
            return Response({'detail': 'No active organization.'}, status=status.HTTP_400_BAD_REQUEST)

        if POSSession.objects.filter(tenant=tenant, cashier=request.user, status='open').exists():
            return Response(
                {'detail': 'You already have an open POS session. Close it before opening a new one.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().create(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        """Set tenant and cashier when creating session"""
        tenant = get_request_tenant(self.request.user)
        serializer.save(
            tenant=tenant,
            cashier=self.request.user
        )
    
    @extend_schema(
        tags=['POS - Sessions'],
        summary='Close a POS session',
        description='Close an open session and calculate final totals',
        parameters=[
            OpenApiParameter(
                name='closing_cash',
                description='Actual cash counted at closing',
                required=True,
                type=OpenApiTypes.NUMBER
            ),
        ]
    )
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close a session"""
        session = self.get_object()
        
        if session.status == 'closed':
            return Response(
                {'error': 'Session is already closed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        closing_cash = request.data.get('closing_cash')
        if closing_cash is None:
            return Response(
                {'error': 'closing_cash is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            closing_cash = Decimal(str(closing_cash))
        except:
            return Response(
                {'error': 'Invalid closing_cash value'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate session totals from transactions
        transactions = POSTransaction.objects.filter(
            tenant=request.user.tenant,
            session=session,
            status='completed'
        )
        
        aggregates = transactions.aggregate(
            total_count=Count('id'),
            total_sales=Sum('total'),
            cash_sales=Sum('total', filter=Q(payment_method='cash')),
            card_sales=Sum('total', filter=Q(payment_method='card')),
            upi_sales=Sum('total', filter=Q(payment_method='upi')),
            credit_sales=Sum('total', filter=Q(payment_method='credit')),
        )
        
        # Update session
        session.total_transactions = aggregates['total_count'] or 0
        session.total_sales = aggregates['total_sales'] or Decimal('0.00')
        session.cash_sales = aggregates['cash_sales'] or Decimal('0.00')
        session.card_sales = aggregates['card_sales'] or Decimal('0.00')
        session.upi_sales = aggregates['upi_sales'] or Decimal('0.00')
        session.credit_sales = aggregates['credit_sales'] or Decimal('0.00')
        
        session.expected_cash = session.opening_cash + session.cash_sales
        session.closing_cash = closing_cash
        session.cash_variance = closing_cash - session.expected_cash
        session.closed_at = timezone.now()
        session.status = 'closed'
        session.save()
        
        serializer = self.get_serializer(session)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(description="List all POS discounts", tags=["POS - Discounts"]),
    retrieve=extend_schema(description="Get discount details", tags=["POS - Discounts"]),
    create=extend_schema(description="Create a new discount", tags=["POS - Discounts"]),
    update=extend_schema(description="Update discount", tags=["POS - Discounts"]),
    partial_update=extend_schema(description="Partially update discount", tags=["POS - Discounts"]),
    destroy=extend_schema(description="Delete a discount", tags=["POS - Discounts"]),
)
class POSDiscountViewSet(viewsets.ModelViewSet):
    """ViewSet for POS Discount management"""
    permission_classes = [DynamicModulePermission]
    permission_module = 'pos'
    serializer_class = POSDiscountSerializer
    filterset_fields = ['discount_type', 'apply_to', 'is_active']
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'created_at', 'discount_value']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        return POSDiscount.objects.filter(tenant=self.request.user.tenant)
    
    def perform_create(self, serializer):
        """Set tenant when creating discount"""
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['POS - Discounts'],
        summary='Get active discounts',
        description='Returns all currently active discounts'
    )
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get all active discounts"""
        today = timezone.now().date()
        discounts = self.get_queryset().filter(
            is_active=True
        ).filter(
            Q(start_date__isnull=True) | Q(start_date__lte=today)
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        )
        
        serializer = self.get_serializer(discounts, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(description="List all POS transactions", tags=["POS - Transactions"]),
    retrieve=extend_schema(description="Get transaction details", tags=["POS - Transactions"]),
    create=extend_schema(
        description="Create a new POS transaction (sale)",
        tags=["POS - Transactions"],
        request=POSTransactionCreateSerializer
    ),
)
class POSTransactionViewSet(viewsets.ModelViewSet):
    """ViewSet for POS Transaction management"""
    permission_classes = [DynamicModulePermission]
    permission_module = 'pos'
    filterset_fields = ['status', 'payment_method', 'cashier', 'warehouse']
    search_fields = ['transaction_number', 'customer__name', 'customer_name']
    ordering_fields = ['date', 'total']
    ordering = ['-date']
    http_method_names = ['get', 'post', 'patch']  # No PUT or DELETE
    
    def get_queryset(self):
        """Filter by current tenant"""
        return POSTransaction.objects.filter(
            tenant=self.request.user.tenant
        ).select_related('customer', 'cashier', 'warehouse').prefetch_related('lines__product')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return POSTransactionCreateSerializer
        return POSTransactionSerializer
    
    @extend_schema(
        tags=['POS - Transactions'],
        summary='Cancel a transaction',
        description='Cancel a POS transaction and restore stock'
    )
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a transaction"""
        from django.db import transaction as db_transaction
        
        pos_transaction = self.get_object()
        
        if pos_transaction.status == 'cancelled':
            return Response(
                {'error': 'Transaction is already cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with db_transaction.atomic():
            # Restore stock
            from inventory.models import Stock, StockMovement
            
            for line in pos_transaction.lines.all():
                if pos_transaction.warehouse:
                    stock = Stock.objects.get(
                        tenant=request.user.tenant,
                        product=line.product,
                        warehouse=pos_transaction.warehouse
                    )
                    stock.quantity += line.quantity
                    stock.save()
                    
                    # Create stock movement
                    StockMovement.objects.create(
                        tenant=request.user.tenant,
                        product=line.product,
                        warehouse=pos_transaction.warehouse,
                        movement_type='in',
                        quantity=line.quantity,
                        reference_type='POSTransaction',
                        reference_id=pos_transaction.id,
                        reason=f'POS Transaction Cancelled - {pos_transaction.transaction_number}',
                        performed_by=request.user
                    )
            
            # Restore customer balance if credit sale
            if pos_transaction.payment_method == 'credit' and pos_transaction.customer:
                customer = pos_transaction.customer
                customer.current_balance -= pos_transaction.total
                customer.save()
                
                # Create ledger entry
                from sales.models import CustomerLedger
                CustomerLedger.objects.create(
                    tenant=request.user.tenant,
                    customer=customer,
                    date=timezone.now().date(),
                    transaction_type='adjustment',
                    reference_type='POSTransaction',
                    reference_number=pos_transaction.transaction_number,
                    reference_id=pos_transaction.id,
                    debit_amount=Decimal('0.00'),
                    credit_amount=pos_transaction.total,
                    running_balance=customer.current_balance,
                    description=f'POS Transaction Cancelled - {pos_transaction.transaction_number}'
                )
            
            # Update transaction status
            pos_transaction.status = 'cancelled'
            pos_transaction.save()
        
        serializer = self.get_serializer(pos_transaction)
        return Response(serializer.data)
    
    @extend_schema(
        tags=['POS - Transactions'],
        summary='Get today\'s transactions',
        description='Returns all transactions for today'
    )
    @action(detail=False, methods=['get'])
    def today(self, request):
        """Get today's transactions"""
        today = timezone.now().date()
        transactions = self.get_queryset().filter(date__date=today)
        
        serializer = self.get_serializer(transactions, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(description="List daily sales reports", tags=["POS - Reports"]),
    retrieve=extend_schema(description="Get report details", tags=["POS - Reports"]),
)
class POSDailySalesReportViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for POS Daily Sales Reports"""
    permission_classes = [DynamicModulePermission]
    permission_module = 'pos'
    serializer_class = POSDailySalesReportSerializer
    filterset_fields = ['date', 'cashier', 'warehouse']
    ordering_fields = ['date', 'net_sales']
    ordering = ['-date']
    
    def get_queryset(self):
        """Filter by current tenant"""
        return POSDailySalesReport.objects.filter(
            tenant=self.request.user.tenant
        ).select_related('cashier', 'warehouse')
    
    @extend_schema(
        tags=['POS - Reports'],
        summary='Generate daily sales report',
        description='Generate a daily sales report for a specific date',
        parameters=[
            OpenApiParameter(
                name='date',
                description='Date for report (YYYY-MM-DD)',
                required=True,
                type=OpenApiTypes.DATE
            ),
            OpenApiParameter(
                name='cashier_id',
                description='Filter by cashier (optional)',
                required=False,
                type=OpenApiTypes.INT
            ),
            OpenApiParameter(
                name='warehouse_id',
                description='Filter by warehouse (optional)',
                required=False,
                type=OpenApiTypes.INT
            ),
        ]
    )
    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Generate a daily sales report"""
        date_str = request.data.get('date')
        cashier_id = request.data.get('cashier_id')
        warehouse_id = request.data.get('warehouse_id')
        
        if not date_str:
            return Response(
                {'error': 'Date is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Build query filters
        filters = {
            'tenant': request.user.tenant,
            'date__date': report_date,
            'status': 'completed'
        }
        
        if cashier_id:
            filters['cashier_id'] = cashier_id
        if warehouse_id:
            filters['warehouse_id'] = warehouse_id
        
        # Get transactions for the day
        transactions = POSTransaction.objects.filter(**filters)
        
        # Calculate metrics
        total_transactions = transactions.count()
        
        # Aggregate data
        aggregates = transactions.aggregate(
            total_items=Sum('lines__quantity'),
            gross_sales=Sum('subtotal'),
            total_discounts=Sum('discount_amount'),
            total_tax=Sum('tax_amount'),
            net_sales=Sum('total'),
            cash_sales=Sum('total', filter=Q(payment_method='cash')),
            card_sales=Sum('total', filter=Q(payment_method='card')),
            upi_sales=Sum('total', filter=Q(payment_method='upi')),
            credit_sales=Sum('total', filter=Q(payment_method='credit')),
        )
        
        # Cancelled/Refunded
        cancelled_count = POSTransaction.objects.filter(
            **{**filters, 'status': 'cancelled'}
        ).count()
        
        refunded_amount = POSTransaction.objects.filter(
            tenant=request.user.tenant,
            date__date=report_date,
            status='refunded'
        ).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        
        # Create or update report
        report, created = POSDailySalesReport.objects.update_or_create(
            tenant=request.user.tenant,
            date=report_date,
            cashier_id=cashier_id,
            warehouse_id=warehouse_id,
            defaults={
                'total_transactions': total_transactions,
                'total_items_sold': aggregates['total_items'] or Decimal('0.00'),
                'gross_sales': aggregates['gross_sales'] or Decimal('0.00'),
                'total_discounts': aggregates['total_discounts'] or Decimal('0.00'),
                'total_tax': aggregates['total_tax'] or Decimal('0.00'),
                'net_sales': aggregates['net_sales'] or Decimal('0.00'),
                'cash_sales': aggregates['cash_sales'] or Decimal('0.00'),
                'card_sales': aggregates['card_sales'] or Decimal('0.00'),
                'upi_sales': aggregates['upi_sales'] or Decimal('0.00'),
                'credit_sales': aggregates['credit_sales'] or Decimal('0.00'),
                'cancelled_transactions': cancelled_count,
                'refunded_amount': refunded_amount,
                'generated_by': request.user
            }
        )
        
        serializer = self.get_serializer(report)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(description="Search products for POS", tags=["POS - Products"]),
)
class POSProductSearchViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for product search in POS"""
    permission_classes = [IsAuthenticated]
    serializer_class = ProductSearchSerializer
    search_fields = ['name', 'sku']
    ordering_fields = ['name', 'selling_price']
    ordering = ['name']
    
    def get_queryset(self):
        """Filter by current tenant and active products"""
        queryset = Product.objects.filter(
            tenant=self.request.user.tenant,
            status='active'
        ).select_related('category', 'unit')
        
        # Filter by barcode if provided
        barcode = self.request.query_params.get('barcode')
        if barcode:
            queryset = queryset.filter(sku=barcode)
        
        return queryset
    
    @extend_schema(
        tags=['POS - Products'],
        summary='Search by barcode',
        description='Search for a product by barcode/SKU',
        parameters=[
            OpenApiParameter(
                name='barcode',
                description='Product barcode/SKU',
                required=True,
                type=OpenApiTypes.STR
            ),
        ]
    )
    @action(detail=False, methods=['get'])
    def barcode(self, request):
        """Search product by barcode"""
        barcode = request.query_params.get('barcode')
        
        if not barcode:
            return Response(
                {'error': 'Barcode is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            product = Product.objects.get(
                tenant=request.user.tenant,
                sku=barcode,
                status='active'
            )
            serializer = self.get_serializer(product)
            return Response(serializer.data)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
