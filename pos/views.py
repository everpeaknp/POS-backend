"""
POS Views for API endpoints
"""

from rest_framework import viewsets, status, parsers
from rest_framework.decorators import action
from rest_framework.response import Response
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
from .models import (
    POSSession, POSDiscount, POSTransaction, POSTransactionLine,
    POSDailySalesReport, POSHeldOrder, POSCashMovement, POSSettings, POSPayment,
)
from .serializers import (
    POSSessionSerializer, POSDiscountSerializer, POSTransactionSerializer,
    POSTransactionCreateSerializer, POSDailySalesReportSerializer,
    ProductSearchSerializer, POSHeldOrderSerializer, POSCashMovementSerializer,
    POSSettingsSerializer,
)
from inventory.models import Product


# ============================================================================
# POS Sessions
# ============================================================================

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
        """Close a session — accounts for split payments and cash movements."""
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

        # ---- Check if any transaction uses split payments ----
        has_split = POSPayment.objects.filter(
            transaction__in=transactions,
        ).exists()

        if has_split:
            # Aggregate from POSPayment rows for accuracy
            payment_agg = POSPayment.objects.filter(
                transaction__in=transactions,
            ).values('payment_method').annotate(total=Sum('amount'))
            method_totals = {row['payment_method']: row['total'] for row in payment_agg}

            # Transactions without split-payment entries — fall back to legacy field
            txn_ids_with_payments = POSPayment.objects.filter(
                transaction__in=transactions,
            ).values_list('transaction_id', flat=True).distinct()
            legacy_txns = transactions.exclude(id__in=txn_ids_with_payments)
            legacy_agg = legacy_txns.values('payment_method').annotate(total=Sum('total'))
            for row in legacy_agg:
                method_totals[row['payment_method']] = (
                    method_totals.get(row['payment_method'], Decimal('0')) + row['total']
                )
        else:
            # No split payments at all — simple aggregation
            aggregates = transactions.aggregate(
                cash_sales=Sum('total', filter=Q(payment_method='cash')),
                card_sales=Sum('total', filter=Q(payment_method='card')),
                esewa_sales=Sum('total', filter=Q(payment_method='esewa')),
                khalti_sales=Sum('total', filter=Q(payment_method='khalti')),
                fonepay_sales=Sum('total', filter=Q(payment_method='fonepay')),
                credit_sales=Sum('total', filter=Q(payment_method='credit')),
            )
            method_totals = {
                'cash': aggregates['cash_sales'] or Decimal('0'),
                'card': aggregates['card_sales'] or Decimal('0'),
                'esewa': aggregates['esewa_sales'] or Decimal('0'),
                'khalti': aggregates['khalti_sales'] or Decimal('0'),
                'fonepay': aggregates['fonepay_sales'] or Decimal('0'),
                'credit': aggregates['credit_sales'] or Decimal('0'),
            }

        # Update session
        session.total_transactions = transactions.count()
        session.total_sales = transactions.aggregate(t=Sum('total'))['t'] or Decimal('0.00')
        session.cash_sales = method_totals.get('cash', Decimal('0'))
        session.card_sales = method_totals.get('card', Decimal('0'))
        session.esewa_sales = method_totals.get('esewa', Decimal('0'))
        session.khalti_sales = method_totals.get('khalti', Decimal('0'))
        session.fonepay_sales = method_totals.get('fonepay', Decimal('0'))
        session.credit_sales = method_totals.get('credit', Decimal('0'))
        
        # Include cash movements in expected_cash
        cash_in = session.cash_movements.filter(
            movement_type='in'
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        cash_out = session.cash_movements.filter(
            movement_type='out'
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

        session.expected_cash = session.opening_cash + session.cash_sales + cash_in - cash_out
        session.closing_cash = closing_cash
        session.cash_variance = closing_cash - session.expected_cash
        session.closed_at = timezone.now()
        session.status = 'closed'
        notes = request.data.get('notes')
        if notes:
            session.notes = notes
        session.save()
        
        serializer = self.get_serializer(session)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """Prevent deleting sessions that have transactions."""
        session = self.get_object()
        if session.transactions.exists():
            return Response(
                {'detail': 'Cannot delete a session that has transactions.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        tags=['POS - Sessions'],
        summary='Get current user open session',
        description='Returns the open POS session for the authenticated cashier',
    )
    @action(detail=False, methods=['get'], url_path='my-open')
    def my_open(self, request):
        tenant = get_request_tenant(request.user)
        session = POSSession.objects.filter(
            tenant=tenant,
            cashier=request.user,
            status='open',
        ).select_related('cashier', 'warehouse').first()
        if not session:
            return Response(
                {'detail': 'No open POS session.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(session)
        return Response(serializer.data)


# ============================================================================
# POS Discounts
# ============================================================================

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


# ============================================================================
# POS Transactions
# ============================================================================

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
        ).select_related('customer', 'cashier', 'warehouse').prefetch_related('lines__product', 'payments')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return POSTransactionCreateSerializer
        return POSTransactionSerializer

    def create(self, request, *args, **kwargs):
        """Override to include reorder alerts in response."""
        import logging
        import json
        logger = logging.getLogger(__name__)
        logger.info(f"POS Transaction create request data: {json.dumps(request.data, indent=2)}")
        logger.info(f"Request user: {request.user}, tenant: {request.user.tenant}")
        
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            logger.error(f"POS Transaction validation errors: {json.dumps(serializer.errors, indent=2)}")
            # Return detailed errors with better structure
            error_response = {
                'status': 'error',
                'message': 'Validation failed',
                'errors': serializer.errors,
                'detail': str(serializer.errors),
            }
            logger.error(f"Returning error response: {json.dumps(error_response, indent=2)}")
            return Response(
                error_response,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            instance = serializer.save()
            out = POSTransactionSerializer(instance, context={'request': request})
            response_data = out.data
            # Attach reorder alerts if any
            alerts = getattr(instance, '_reorder_alerts', [])
            if alerts:
                response_data = dict(response_data)
                response_data['reorder_alerts'] = alerts
            from rest_framework import status as drf_status
            return Response(response_data, status=drf_status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"POS Transaction creation failed: {str(e)}", exc_info=True)
            error_response = {
                'status': 'error',
                'message': str(e),
                'detail': 'Failed to create transaction',
                'error_type': type(e).__name__
            }
            return Response(
                error_response,
                status=status.HTTP_400_BAD_REQUEST
            )
    
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
            from inventory.models import Stock, StockMovement
            from sales.models import Customer
            from sales.accounting_integration import reverse_pos_sale

            lines = list(pos_transaction.lines.select_related('product'))
            
            for line in lines:
                if pos_transaction.warehouse:
                    stock, _created = Stock.objects.get_or_create(
                        tenant=request.user.tenant,
                        product=line.product,
                        warehouse=pos_transaction.warehouse,
                        defaults={'quantity': Decimal('0.00')}
                    )
                    stock.quantity += line.quantity
                    stock.save()
                    
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
            
            if pos_transaction.payment_method == 'credit' and pos_transaction.customer:
                customer = Customer.objects.select_for_update().get(pk=pos_transaction.customer_id)
                customer.current_balance -= pos_transaction.total
                customer.save(update_fields=['current_balance', 'updated_at'])
                
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

            reverse_pos_sale(pos_transaction, lines)
            
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
    
    @extend_schema(
        tags=['POS - Transactions'],
        summary='Get transaction by number',
        description='Retrieve a transaction by its transaction number (e.g., POS-000029)'
    )
    @action(detail=False, methods=['get'], url_path='by-number/(?P<transaction_number>[^/.]+)')
    def by_number(self, request, transaction_number=None):
        """Get transaction by transaction number"""
        try:
            transaction = self.get_queryset().get(transaction_number=transaction_number)
            serializer = self.get_serializer(transaction)
            return Response(serializer.data)
        except POSTransaction.DoesNotExist:
            return Response(
                {'detail': f'Transaction {transaction_number} not found'},
                status=status.HTTP_404_NOT_FOUND
            )


# ============================================================================
# POS Daily Reports
# ============================================================================

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
            esewa_sales=Sum('total', filter=Q(payment_method='esewa')),
            khalti_sales=Sum('total', filter=Q(payment_method='khalti')),
            fonepay_sales=Sum('total', filter=Q(payment_method='fonepay')),
            credit_sales=Sum('total', filter=Q(payment_method='credit')),
        )
        
        # Cancelled transactions (separate query — completed filter is on main aggregates)
        cancelled_filters = {
            'tenant': request.user.tenant,
            'date__date': report_date,
            'status': 'cancelled',
        }
        if cashier_id:
            cancelled_filters['cashier_id'] = cashier_id
        if warehouse_id:
            cancelled_filters['warehouse_id'] = warehouse_id

        cancelled_count = POSTransaction.objects.filter(**cancelled_filters).count()
        
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
                'esewa_sales': aggregates['esewa_sales'] or Decimal('0.00'),
                'khalti_sales': aggregates['khalti_sales'] or Decimal('0.00'),
                'fonepay_sales': aggregates['fonepay_sales'] or Decimal('0.00'),
                'credit_sales': aggregates['credit_sales'] or Decimal('0.00'),
                'cancelled_transactions': cancelled_count,
                'refunded_amount': refunded_amount,
                'generated_by': request.user
            }
        )
        
        serializer = self.get_serializer(report)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


# ============================================================================
# POS Product Search
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="Search products for POS", tags=["POS - Products"]),
)
class POSProductSearchViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for product search in POS"""
    permission_classes = [DynamicModulePermission]
    permission_module = 'pos'
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


# ============================================================================
# POS Held Orders
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="List held/parked orders", tags=["POS - Held Orders"]),
    retrieve=extend_schema(description="Get held order details", tags=["POS - Held Orders"]),
    create=extend_schema(description="Create a held order (park cart)", tags=["POS - Held Orders"]),
    destroy=extend_schema(description="Delete a held order", tags=["POS - Held Orders"]),
)
class POSHeldOrderViewSet(viewsets.ModelViewSet):
    """ViewSet for holding/parking orders."""
    permission_classes = [DynamicModulePermission]
    permission_module = 'pos'
    serializer_class = POSHeldOrderSerializer
    http_method_names = ['get', 'post', 'delete']
    ordering = ['-held_at']

    def get_queryset(self):
        qs = POSHeldOrder.objects.filter(tenant=self.request.user.tenant)
        session_id = self.request.query_params.get('session')
        if session_id:
            qs = qs.filter(session_id=session_id)
        # By default only show non-resumed orders
        show_all = self.request.query_params.get('all')
        if not show_all:
            qs = qs.filter(is_resumed=False)
        return qs.select_related('held_by', 'customer')

    def perform_create(self, serializer):
        serializer.save(
            tenant=self.request.user.tenant,
            held_by=self.request.user,
        )

    @extend_schema(
        tags=['POS - Held Orders'],
        summary='Resume a held order',
        description='Mark a held order as resumed (client should populate the cart from the items JSON)',
    )
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """Mark a held order as resumed."""
        held_order = self.get_object()
        if held_order.is_resumed:
            return Response(
                {'error': 'This order has already been resumed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        held_order.is_resumed = True
        held_order.resumed_at = timezone.now()
        held_order.save(update_fields=['is_resumed', 'resumed_at', 'updated_at'])
        serializer = self.get_serializer(held_order)
        return Response(serializer.data)


# ============================================================================
# POS Cash Movements
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="List cash movements for a session", tags=["POS - Cash"]),
    create=extend_schema(description="Record a cash in/out movement", tags=["POS - Cash"]),
)
class POSCashMovementViewSet(viewsets.ModelViewSet):
    """ViewSet for cash-in / cash-out operations during a session."""
    permission_classes = [DynamicModulePermission]
    permission_module = 'pos'
    serializer_class = POSCashMovementSerializer
    http_method_names = ['get', 'post', 'delete']
    ordering = ['-performed_at']

    def get_queryset(self):
        qs = POSCashMovement.objects.filter(tenant=self.request.user.tenant)
        session_id = self.request.query_params.get('session')
        if session_id:
            qs = qs.filter(session_id=session_id)
        return qs.select_related('performed_by', 'session')

    def perform_create(self, serializer):
        session = serializer.validated_data.get('session')
        if session and session.status != 'open':
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'session': 'Cash movements can only be added to open sessions.'})
        serializer.save(
            tenant=self.request.user.tenant,
            performed_by=self.request.user,
        )


# ============================================================================
# POS Settings (single-object per tenant)
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="Get POS settings", tags=["POS - Settings"]),
)
class POSSettingsViewSet(viewsets.ViewSet):
    """Single-object viewset for per-tenant POS settings (get-or-create)."""
    permission_classes = [DynamicModulePermission]
    permission_module = 'pos'
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    @extend_schema(tags=['POS - Settings'], summary='Get POS settings')
    def list(self, request):
        """Return the current tenant's POS settings."""
        tenant = get_request_tenant(request.user)
        settings = POSSettings.get_for_tenant(tenant)
        serializer = POSSettingsSerializer(settings)
        return Response(serializer.data)

    @extend_schema(tags=['POS - Settings'], summary='Update POS settings')
    @action(detail=False, methods=['patch', 'put'], url_path='update')
    def update_settings(self, request):
        """Update POS settings for the current tenant. Supports file uploads."""
        tenant = get_request_tenant(request.user)
        settings = POSSettings.get_for_tenant(tenant)
        
        # Merge request.data and request.FILES for proper file handling
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        # Add files from request.FILES if present
        if request.FILES:
            for key, file in request.FILES.items():
                data[key] = file
        
        serializer = POSSettingsSerializer(settings, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ============================================================================
# Feature 1: Return / Refund with Stock Restore
# ============================================================================

class POSRefundViewSet(viewsets.ModelViewSet):
    """
    Partial or full refund for a completed POS transaction.
    Restores stock, reverses GL, and optionally adjusts customer ledger.
    """
    permission_classes = [DynamicModulePermission]
    permission_module = 'pos'
    http_method_names = ['get', 'post']
    ordering = ['-refunded_at']

    def get_queryset(self):
        from .models import POSRefund
        qs = POSRefund.objects.filter(tenant=self.request.user.tenant)
        txn_id = self.request.query_params.get('transaction')
        if txn_id:
            qs = qs.filter(original_transaction_id=txn_id)
        return qs.select_related('original_transaction', 'refunded_by')

    def get_serializer_class(self):
        from .serializers import POSRefundSerializer, POSRefundCreateSerializer
        if self.action == 'create':
            return POSRefundCreateSerializer
        return POSRefundSerializer

    def create(self, request, *args, **kwargs):
        from django.db import transaction as db_txn
        from .models import POSRefund, POSRefundLine
        from .serializers import POSRefundCreateSerializer, POSRefundSerializer
        from inventory.models import Stock, StockMovement
        from sales.accounting_integration import reverse_pos_sale

        serializer = POSRefundCreateSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        original = data['original_transaction']
        refund_lines_data = data['lines']  # [{original_line, quantity}]
        reason = data.get('reason', '')
        refund_method = data['refund_method']
        tenant = request.user.tenant

        with db_txn.atomic():
            # Create the refund record
            refund = POSRefund.objects.create(
                tenant=tenant,
                original_transaction=original,
                reason=reason,
                refund_method=refund_method,
                refunded_by=request.user,
            )

            refund_total = Decimal('0.00')

            for rline_data in refund_lines_data:
                orig_line = rline_data['original_line']
                qty = Decimal(str(rline_data['quantity']))

                # Validate not over-refunding
                already_refunded = POSRefundLine.objects.filter(
                    original_line=orig_line
                ).aggregate(t=Sum('quantity'))['t'] or Decimal('0')
                if already_refunded + qty > orig_line.quantity:
                    return Response(
                        {
                            'error': (
                                f'Cannot refund {qty} of {orig_line.product_name}. '
                                f'Sold: {orig_line.quantity}, '
                                f'Already refunded: {already_refunded}'
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                refund_amount = orig_line.get_refund_amount(qty)
                POSRefundLine.objects.create(
                    tenant=tenant,
                    refund=refund,
                    original_line=orig_line,
                    quantity=qty,
                    refund_amount=refund_amount,
                )
                refund_total += refund_amount

                # Restore stock
                if original.warehouse:
                    stock, _ = Stock.objects.get_or_create(
                        tenant=tenant,
                        product=orig_line.product,
                        warehouse=original.warehouse,
                        defaults={'quantity': Decimal('0.00')},
                    )
                    stock.quantity += qty
                    stock.save()

                    StockMovement.objects.create(
                        tenant=tenant,
                        product=orig_line.product,
                        warehouse=original.warehouse,
                        movement_type='in',
                        quantity=qty,
                        reference_type='POSRefund',
                        reference_id=refund.id,
                        reason=f'POS Refund - {original.transaction_number}',
                        performed_by=request.user,
                    )

            # Mark original transaction as refunded if fully returned
            all_refunded = True
            for line in original.lines.all():
                total_refunded = POSRefundLine.objects.filter(
                    original_line=line
                ).aggregate(t=Sum('quantity'))['t'] or Decimal('0')
                if total_refunded < line.quantity:
                    all_refunded = False
                    break
            if all_refunded:
                original.status = 'refunded'
                original.save(update_fields=['status', 'updated_at'])

            # GL reversal (proportional)
            try:
                from sales.accounting_integration import record_pos_refund
                record_pos_refund(original, refund_total, refund.id, tenant)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error(f'POS refund GL failed: {exc}')

        out = POSRefundSerializer(refund)
        return Response(out.data, status=status.HTTP_201_CREATED)


# ============================================================================
# Feature 2: Customer Loyalty / Points
# ============================================================================

class LoyaltyProgramViewSet(viewsets.ViewSet):
    """Get/update the tenant loyalty program configuration."""
    permission_classes = [DynamicModulePermission]
    permission_module = 'pos'

    def list(self, request):
        from .models import LoyaltyProgram
        from .serializers import LoyaltyProgramSerializer
        tenant = get_request_tenant(request.user)
        program = LoyaltyProgram.get_for_tenant(tenant)
        return Response(LoyaltyProgramSerializer(program).data)

    @action(detail=False, methods=['patch', 'put'], url_path='update')
    def update_program(self, request):
        from .models import LoyaltyProgram
        from .serializers import LoyaltyProgramSerializer
        tenant = get_request_tenant(request.user)
        program = LoyaltyProgram.get_for_tenant(tenant)
        serializer = LoyaltyProgramSerializer(program, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CustomerLoyaltyViewSet(viewsets.ViewSet):
    """Get loyalty balance and history for a customer, and redeem points."""
    permission_classes = [DynamicModulePermission]
    permission_module = 'pos'

    def retrieve(self, request, pk=None):
        from .models import CustomerLoyaltyPoints, LoyaltyTransaction
        from .serializers import CustomerLoyaltySerializer
        tenant = get_request_tenant(request.user)
        try:
            points_obj, _ = CustomerLoyaltyPoints._base_manager.get_or_create(
                tenant=tenant,
                customer_id=pk,
            )
        except Exception:
            return Response({'error': 'Customer not found.'}, status=404)
        history = LoyaltyTransaction.objects.filter(
            customer_points=points_obj
        ).order_by('-created_at')[:50]
        data = CustomerLoyaltySerializer(points_obj).data
        data['history'] = [
            {
                'type': t.transaction_type,
                'points': t.points,
                'reference': t.reference,
                'description': t.description,
                'date': t.created_at,
            }
            for t in history
        ]
        return Response(data)

    @action(detail=True, methods=['post'])
    def redeem(self, request, pk=None):
        """Redeem loyalty points as a discount."""
        from .models import CustomerLoyaltyPoints, LoyaltyTransaction, LoyaltyProgram
        from django.db import transaction as db_txn

        tenant = get_request_tenant(request.user)
        points_to_redeem = int(request.data.get('points', 0))
        if points_to_redeem <= 0:
            return Response({'error': 'Points must be > 0.'}, status=400)

        program = LoyaltyProgram.get_for_tenant(tenant)
        if not program.is_active:
            return Response({'error': 'Loyalty program is not active.'}, status=400)

        with db_txn.atomic():
            pts, _ = CustomerLoyaltyPoints._base_manager.select_for_update().get_or_create(
                tenant=tenant, customer_id=pk
            )
            if pts.points_balance < points_to_redeem:
                return Response(
                    {'error': f'Insufficient points. Balance: {pts.points_balance}'},
                    status=400,
                )
            if points_to_redeem < program.min_redemption_points:
                return Response(
                    {'error': f'Minimum redemption is {program.min_redemption_points} points.'},
                    status=400,
                )

            discount_amount = Decimal(str(points_to_redeem)) * program.rupees_per_point
            pts.points_balance -= points_to_redeem
            pts.total_redeemed += points_to_redeem
            pts.save()

            LoyaltyTransaction.objects.create(
                tenant=tenant,
                customer_points=pts,
                transaction_type='redeem',
                points=-points_to_redeem,
                reference=request.data.get('transaction_number', ''),
                description=f'Redeemed {points_to_redeem} pts = Rs. {discount_amount}',
            )

        return Response({
            'points_redeemed': points_to_redeem,
            'discount_amount': float(discount_amount),
            'remaining_balance': pts.points_balance,
        })


# ============================================================================
# Feature 4: Z-Report (End of Day)
# ============================================================================

class ZReportViewSet(viewsets.ViewSet):
    """Generate and retrieve Z-Reports (end-of-day register summaries)."""
    permission_classes = [DynamicModulePermission]
    permission_module = 'pos'

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Generate Z-Report for a session."""
        from .models import POSRefund
        session_id = request.data.get('session_id')
        if not session_id:
            return Response({'error': 'session_id is required.'}, status=400)

        tenant = get_request_tenant(request.user)
        try:
            session = POSSession._base_manager.get(id=session_id, tenant=tenant)
        except POSSession.DoesNotExist:
            return Response({'error': 'Session not found.'}, status=404)

        transactions = POSTransaction.objects.filter(
            tenant=tenant, session=session, status='completed'
        )
        refunded = POSTransaction.objects.filter(
            tenant=tenant, session=session, status='refunded'
        )

        agg = transactions.aggregate(
            total_txns=Count('id'),
            gross_sales=Sum('subtotal'),
            total_discounts=Sum('discount_amount'),
            total_tax=Sum('tax_amount'),
            net_sales=Sum('total'),
            items_sold=Sum('lines__quantity'),
            cash=Sum('total', filter=Q(payment_method='cash')),
            card=Sum('total', filter=Q(payment_method='card')),
            esewa=Sum('total', filter=Q(payment_method='esewa')),
            khalti=Sum('total', filter=Q(payment_method='khalti')),
            fonepay=Sum('total', filter=Q(payment_method='fonepay')),
            credit=Sum('total', filter=Q(payment_method='credit')),
        )

        refund_agg = refunded.aggregate(refunded_total=Sum('total'))

        # Cash movements
        cash_in = session.cash_movements.filter(movement_type='in').aggregate(
            t=Sum('amount'))['t'] or Decimal('0')
        cash_out = session.cash_movements.filter(movement_type='out').aggregate(
            t=Sum('amount'))['t'] or Decimal('0')

        cash_sales = agg['cash'] or Decimal('0')
        expected_cash = session.opening_cash + cash_sales + cash_in - cash_out

        def d(val):
            return float(val or 0)

        report = {
            'session_number': session.session_number,
            'cashier': session.cashier.get_full_name() or session.cashier.username,
            'warehouse': session.warehouse_name if hasattr(session, 'warehouse_name') else (
                session.warehouse.name if session.warehouse else None
            ),
            'opened_at': session.opened_at,
            'closed_at': session.closed_at,
            'report_generated_at': timezone.now(),

            # Cash drawer
            'opening_cash': d(session.opening_cash),
            'cash_in': d(cash_in),
            'cash_out': d(cash_out),
            'expected_cash': d(expected_cash),
            'closing_cash': d(session.closing_cash) if session.closing_cash is not None else None,
            'cash_variance': d(session.cash_variance),

            # Sales
            'total_transactions': agg['total_txns'] or 0,
            'total_items_sold': d(agg['items_sold']),
            'gross_sales': d(agg['gross_sales']),
            'total_discounts': d(agg['total_discounts']),
            'tax_collected': d(agg['total_tax']),
            'net_sales': d(agg['net_sales']),

            # By payment method
            'cash_sales': d(cash_sales),
            'card_sales': d(agg['card']),
            'esewa_sales': d(agg['esewa']),
            'khalti_sales': d(agg['khalti']),
            'fonepay_sales': d(agg['fonepay']),
            'credit_sales': d(agg['credit']),
            'digital_wallet_sales': d(agg['esewa']) + d(agg['khalti']) + d(agg['fonepay']),

            # Refunds
            'refunded_transactions': refunded.count(),
            'refunded_amount': d(refund_agg['refunded_total']),
            'cancelled_transactions': POSTransaction.objects.filter(
                tenant=tenant, session=session, status='cancelled'
            ).count(),
        }
        return Response(report)
