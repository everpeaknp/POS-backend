from tenants.utils import get_request_tenant

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from django.db.models import Sum, Q, F
from django.db import models
from django.utils import timezone
from datetime import timedelta, datetime as dt
from decimal import Decimal
from users.dynamic_permissions import DynamicModulePermission

from .models import (
    Customer, SalesOrder, SalesOrderLine, Quotation, Invoice, CreditNote,
    CustomerLedger, PaymentReceived
)
from .filters import SalesOrderFilterSet, QuotationFilterSet, InvoiceFilterSet
from .serializers import (
    CustomerSerializer, CustomerDetailSerializer, SalesOrderSerializer, SalesOrderCreateSerializer,
    QuotationSerializer, QuotationCreateSerializer, InvoiceSerializer, CreditNoteSerializer,
    CustomerLedgerSerializer, PaymentReceivedSerializer
)


@extend_schema_view(
    list=extend_schema(description="List all customers for the current tenant", tags=["Sales - Customers"]),
    retrieve=extend_schema(description="Get customer details", tags=["Sales - Customers"]),
    create=extend_schema(description="Create a new customer", tags=["Sales - Customers"]),
    update=extend_schema(description="Update customer details", tags=["Sales - Customers"]),
    partial_update=extend_schema(description="Partially update customer", tags=["Sales - Customers"]),
    destroy=extend_schema(description="Delete a customer", tags=["Sales - Customers"]),
)
class CustomerViewSet(viewsets.ModelViewSet):
    """ViewSet for Customer CRUD operations with credit management"""
    permission_classes = [DynamicModulePermission]
    permission_module = 'sales'
    filterset_fields = ['status', 'type', 'payment_terms']
    search_fields = ['name', 'phone', 'email', 'pan']
    ordering_fields = ['name', 'created_at', 'current_balance']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        return Customer.objects.filter(tenant=self.request.user.tenant)
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CustomerDetailSerializer
        return CustomerSerializer
    
    def perform_create(self, serializer):
        """Set tenant when creating customer"""
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['Sales - Customers'],
        summary='Get customer ledger',
        description='Returns complete ledger history for a customer'
    )
    @action(detail=True, methods=['get'])
    def ledger(self, request, pk=None):
        """Get customer ledger entries"""
        customer = self.get_object()
        ledger_entries = customer.ledger_entries.all()
        serializer = CustomerLedgerSerializer(ledger_entries, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        tags=['Sales - Customers'],
        summary='Get aging report',
        description='Returns outstanding balance by age buckets (30, 60, 90+ days)',
        responses={200: {
            'type': 'object',
            'properties': {
                'customer_id': {'type': 'string'},
                'customer_name': {'type': 'string'},
                'total_outstanding': {'type': 'number'},
                'current': {'type': 'number', 'description': '0-30 days'},
                'days_30_60': {'type': 'number', 'description': '30-60 days'},
                'days_60_90': {'type': 'number', 'description': '60-90 days'},
                'days_90_plus': {'type': 'number', 'description': '90+ days'},
                'overdue_invoices': {'type': 'array'},
            }
        }}
    )
    @action(detail=True, methods=['get'])
    def aging_report(self, request, pk=None):
        """
        Generate aging report for customer
        Shows outstanding balance by age buckets
        """
        customer = self.get_object()
        today = timezone.now().date()
        
        # Get all unpaid/partially paid invoices
        unpaid_invoices = customer.invoices.filter(
            Q(status='Sent') | Q(status='Partially Paid') | Q(status='Overdue')
        ).exclude(status='Paid')
        
        # Initialize buckets
        current = Decimal('0.00')  # 0-30 days
        days_30_60 = Decimal('0.00')
        days_60_90 = Decimal('0.00')
        days_90_plus = Decimal('0.00')
        
        overdue_invoices = []
        
        for invoice in unpaid_invoices:
            balance = invoice.balance
            days_overdue = (today - invoice.due_date).days
            
            # Categorize by age
            if days_overdue < 0:
                # Not yet due
                current += balance
            elif days_overdue <= 30:
                current += balance
            elif days_overdue <= 60:
                days_30_60 += balance
            elif days_overdue <= 90:
                days_60_90 += balance
            else:
                days_90_plus += balance
            
            # Add to overdue list if past due date
            if days_overdue > 0:
                overdue_invoices.append({
                    'invoice_number': invoice.invoice_number,
                    'date': invoice.date.isoformat(),
                    'due_date': invoice.due_date.isoformat(),
                    'amount': float(invoice.amount),
                    'paid_amount': float(invoice.paid_amount),
                    'balance': float(balance),
                    'days_overdue': days_overdue
                })
        
        report = {
            'customer_id': str(customer.id),
            'customer_name': customer.name,
            'total_outstanding': float(customer.current_balance),
            'current': float(current),
            'days_30_60': float(days_30_60),
            'days_60_90': float(days_60_90),
            'days_90_plus': float(days_90_plus),
            'overdue_invoices': overdue_invoices,
            'credit_limit': float(customer.credit_limit),
            'available_credit': float(customer.available_credit),
            'is_over_limit': customer.is_over_limit,
        }
        
        return Response(report)
    
    @extend_schema(
        tags=['Sales - Customers'],
        summary='Get customer credit summary',
        description='Returns credit summary for a specific customer including recent transactions',
        responses={200: {
            'type': 'object',
            'properties': {
                'customer_id': {'type': 'string'},
                'customer_name': {'type': 'string'},
                'credit_limit': {'type': 'number'},
                'current_balance': {'type': 'number'},
                'available_credit': {'type': 'number'},
                'is_over_limit': {'type': 'boolean'},
                'total_invoices': {'type': 'number'},
                'unpaid_invoices': {'type': 'number'},
                'recent_transactions': {'type': 'array'},
            }
        }}
    )
    @action(detail=True, methods=['get'])
    def credit_summary(self, request, pk=None):
        """
        Get credit summary for a specific customer
        Includes recent transactions and invoice counts
        """
        customer = self.get_object()
        
        # Get invoice counts
        total_invoices = customer.invoices.count()
        unpaid_invoices = customer.invoices.filter(
            Q(status='Sent') | Q(status='Partially Paid') | Q(status='Overdue')
        ).count()
        
        # Get recent ledger entries (last 10)
        recent_ledger = customer.ledger_entries.all()[:10]
        recent_transactions = CustomerLedgerSerializer(recent_ledger, many=True).data
        
        summary = {
            'customer_id': str(customer.id),
            'customer_name': customer.name,
            'credit_limit': float(customer.credit_limit),
            'current_balance': float(customer.current_balance),
            'available_credit': float(customer.available_credit),
            'is_over_limit': customer.is_over_limit,
            'total_invoices': total_invoices,
            'unpaid_invoices': unpaid_invoices,
            'recent_transactions': recent_transactions,
            'payment_terms': customer.payment_terms,
            'status': customer.status,
        }
        
        return Response(summary)
    
    @extend_schema(
        tags=['Sales - Customers'],
        summary='Get credit overview for all customers',
        description='Returns credit overview for all customers with outstanding balances',
        responses={200: {
            'type': 'object',
            'properties': {
                'total_outstanding': {'type': 'number'},
                'total_credit_limit': {'type': 'number'},
                'customers_with_balance': {'type': 'number'},
                'customers_over_limit': {'type': 'number'},
                'customers': {'type': 'array'},
            }
        }}
    )
    @action(detail=False, methods=['get'])
    def credit_overview(self, request):
        """
        Get credit overview for all customers
        Shows total outstanding, credit limits, and customers over limit
        """
        customers = self.get_queryset()
        
        # Calculate totals
        total_outstanding = customers.aggregate(
            total=Sum('current_balance')
        )['total'] or Decimal('0.00')
        
        total_credit_limit = customers.aggregate(
            total=Sum('credit_limit')
        )['total'] or Decimal('0.00')
        
        # Count customers with balance
        customers_with_balance = customers.filter(current_balance__gt=0).count()
        
        # Get customers over limit
        customers_over_limit_qs = customers.filter(
            current_balance__gt=models.F('credit_limit')
        )
        customers_over_limit_count = customers_over_limit_qs.count()
        
        # Get top customers by outstanding balance
        top_customers = customers.filter(
            current_balance__gt=0
        ).order_by('-current_balance')[:10]
        
        customers_data = [{
            'id': str(c.id),
            'name': c.name,
            'phone': c.phone,
            'current_balance': float(c.current_balance),
            'credit_limit': float(c.credit_limit),
            'available_credit': float(c.available_credit),
            'is_over_limit': c.is_over_limit,
            'payment_terms': c.payment_terms,
        } for c in top_customers]
        
        overview = {
            'total_outstanding': float(total_outstanding),
            'total_credit_limit': float(total_credit_limit),
            'customers_with_balance': customers_with_balance,
            'customers_over_limit': customers_over_limit_count,
            'customers': customers_data,
            'utilization_rate': float((total_outstanding / total_credit_limit * 100) if total_credit_limit > 0 else 0),
        }
        
        return Response(overview)


@extend_schema_view(
    list=extend_schema(description="List all sales orders for the current tenant", tags=["Sales - Orders"]),
    retrieve=extend_schema(description="Get sales order details with line items", tags=["Sales - Orders"]),
    create=extend_schema(
        description="Create a new sales order with line items",
        tags=["Sales - Orders"],
        request=SalesOrderCreateSerializer
    ),
    update=extend_schema(
        description="Update sales order",
        tags=["Sales - Orders"],
        request=SalesOrderCreateSerializer
    ),
    partial_update=extend_schema(description="Partially update sales order", tags=["Sales - Orders"]),
    destroy=extend_schema(description="Delete a sales order", tags=["Sales - Orders"]),
)
class SalesOrderViewSet(viewsets.ModelViewSet):
    """ViewSet for Sales Order CRUD operations"""
    permission_classes = [DynamicModulePermission]
    permission_module = 'sales'
    filterset_class = SalesOrderFilterSet
    search_fields = ['order_number', 'reference', 'customer__name']
    ordering_fields = ['date', 'created_at', 'total']
    ordering = ['-date', '-created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            return SalesOrder.objects.none()
        return SalesOrder.objects.filter(tenant=tenant).select_related('customer', 'created_by').prefetch_related('lines__product')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return SalesOrderCreateSerializer
        return SalesOrderSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if hasattr(self, 'request') and self.request is not None:
            context['warehouse_id'] = self.request.data.get('warehouse_id')
        return context
    
    def perform_create(self, serializer):
        from django.db import transaction
        from django.db.utils import IntegrityError
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                with transaction.atomic():
                    # Auto-generate order number (globally unique across all tenants due to DB constraint)
                    # Use _base_manager to bypass tenant filtering and get true last order number
                    last_order = SalesOrder._base_manager.select_for_update().all().order_by('-id').first()
                    if last_order and last_order.order_number.startswith('SO-'):
                        try:
                            last_num = int(last_order.order_number.split('-')[1])
                            order_number = f"SO-{str(last_num + 1).zfill(4)}"
                        except:
                            order_number = "SO-0001"
                    else:
                        order_number = "SO-0001"
                    
                    serializer.save(
                        tenant=get_request_tenant(self.request.user),
                        created_by=self.request.user, 
                        order_number=order_number
                    )
                    break  # Success, exit loop
            except IntegrityError as e:
                if attempt == max_retries - 1:
                    raise
                continue
    
    @extend_schema(
        description="Update sales order status",
        tags=["Sales - Orders"],
        request={'application/json': {'type': 'object', 'properties': {'status': {'type': 'string'}}}},
        responses={200: SalesOrderSerializer}
    )
    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """Update the status of a sales order"""
        sales_order = self.get_object()
        new_status = request.data.get('status')
        warehouse_id = request.data.get('warehouse_id')
        
        if new_status not in dict(SalesOrder.STATUS_CHOICES):
            return Response(
                {'error': 'Invalid status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = sales_order.status
        
        try:
            from django.db import transaction as db_transaction
            from sales.stock_integration import handle_sales_order_status_change

            with db_transaction.atomic():
                handle_sales_order_status_change(
                    sales_order,
                    old_status=old_status,
                    new_status=new_status,
                    performed_by=request.user,
                    warehouse_id=warehouse_id,
                )
                sales_order.status = new_status
                sales_order.save(update_fields=['status'])
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(sales_order)
        return Response(serializer.data)
    
    @extend_schema(
        description="Finalize sales order on credit - creates ledger entry and updates customer balance",
        tags=["Sales - Orders"],
        request=None,
        responses={200: SalesOrderSerializer}
    )
    @action(detail=True, methods=['post'])
    def finalize_on_credit(self, request, pk=None):
        """
        Finalize a sales order on credit
        Automatically creates ledger entry and updates customer balance
        """
        sales_order = self.get_object()
        
        try:
            sales_order.finalize_on_credit(
                performed_by=request.user,
                warehouse_id=request.data.get('warehouse_id'),
            )
            serializer = self.get_serializer(sales_order)
            return Response({
                'message': 'Sales order finalized on credit successfully',
                'order': serializer.data
            })
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to finalize order: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        tags=['Sales - Dashboard'],
        summary='Get sales dashboard data',
        description='Returns comprehensive sales dashboard data including stats, charts, recent orders, top products, and customers',
        parameters=[
            OpenApiParameter(
                name='period',
                description='Time period for revenue chart (today, week, month, year)',
                required=False,
                type=OpenApiTypes.STR,
                default='month'
            )
        ]
    )
    @action(detail=False, methods=['get'], url_path='dashboard')
    def sales_dashboard(self, request):
        """Sales Dashboard API endpoint - Returns dashboard data"""
        from django.db.models import Sum, Count, Q, F
        from django.utils import timezone
        from datetime import timedelta
        from inventory.models import Product, Stock
        
        period = request.query_params.get('period', 'month')
        tenant = request.user.tenant
        today = timezone.now().date()
        
        # Calculate date ranges (SalesOrder.date is a DateField)
        if period == 'today':
            start_date = today
            prev_start = today - timedelta(days=1)
            prev_end = today
        elif period == 'week':
            start_date = today - timedelta(days=6)
            prev_start = start_date - timedelta(days=7)
            prev_end = start_date
        elif period == 'year':
            start_date = today.replace(month=1, day=1)
            prev_start = start_date.replace(year=start_date.year - 1)
            prev_end = start_date
        else:  # month
            start_date = today - timedelta(days=29)
            prev_start = start_date - timedelta(days=30)
            prev_end = start_date
        
        # Get orders for current and previous period
        current_orders = SalesOrder.objects.filter(
            tenant=tenant,
            date__gte=start_date,
            status__in=['Confirmed', 'Delivered']
        )
        
        previous_orders = SalesOrder.objects.filter(
            tenant=tenant,
            date__gte=prev_start,
            date__lt=prev_end,
            status__in=['Confirmed', 'Delivered']
        )
        
        # Calculate stats
        current_revenue = current_orders.aggregate(total=Sum('total'))['total'] or 0
        previous_revenue = previous_orders.aggregate(total=Sum('total'))['total'] or 0
        revenue_change = ((current_revenue - previous_revenue) / previous_revenue * 100) if previous_revenue > 0 else 0
        
        current_order_count = current_orders.count()
        previous_order_count = previous_orders.count()
        orders_change = ((current_order_count - previous_order_count) / previous_order_count * 100) if previous_order_count > 0 else 0
        
        # Customer stats — new customers in period vs previous period
        new_customers_period = Customer.objects.filter(tenant=tenant, created_at__date__gte=start_date).count()
        new_customers_prev = Customer.objects.filter(
            tenant=tenant, created_at__date__gte=prev_start, created_at__date__lt=prev_end
        ).count()
        customers_change = (
            ((new_customers_period - new_customers_prev) / new_customers_prev * 100)
            if new_customers_prev > 0 else 0
        )
        total_customers = Customer.objects.filter(tenant=tenant).count()
        
        # Product stats
        current_products = Product.objects.filter(tenant=tenant, created_at__gte=start_date).count()
        previous_products = Product.objects.filter(tenant=tenant, created_at__gte=prev_start, created_at__lt=prev_end).count()
        products_change = ((current_products - previous_products) / previous_products * 100) if previous_products > 0 else 0
        total_products = Product.objects.filter(tenant=tenant).count()
        
        revenue_data = []
        if period == 'today':
            revenue_data.append({
                'time': 'Today',
                'value': float(current_revenue),
            })
        elif period == 'week':
            for day_offset in range(7):
                day = start_date + timedelta(days=day_offset)
                revenue = SalesOrder.objects.filter(
                    tenant=tenant,
                    date=day,
                    status__in=['Confirmed', 'Delivered'],
                ).aggregate(total=Sum('total'))['total'] or 0
                revenue_data.append({
                    'time': day.strftime('%a'),
                    'value': float(revenue),
                })
        elif period == 'year':
            month_cursor = start_date.replace(day=1)
            while month_cursor <= today:
                if month_cursor.month == 12:
                    next_month = month_cursor.replace(year=month_cursor.year + 1, month=1)
                else:
                    next_month = month_cursor.replace(month=month_cursor.month + 1)
                revenue = SalesOrder.objects.filter(
                    tenant=tenant,
                    date__gte=month_cursor,
                    date__lt=next_month,
                    status__in=['Confirmed', 'Delivered'],
                ).aggregate(total=Sum('total'))['total'] or 0
                revenue_data.append({
                    'time': month_cursor.strftime('%b'),
                    'value': float(revenue),
                })
                month_cursor = next_month
        else:  # month
            for day_offset in range(0, 30, 3):
                bucket_start = start_date + timedelta(days=day_offset)
                bucket_end = min(bucket_start + timedelta(days=3), today + timedelta(days=1))
                revenue = SalesOrder.objects.filter(
                    tenant=tenant,
                    date__gte=bucket_start,
                    date__lt=bucket_end,
                    status__in=['Confirmed', 'Delivered'],
                ).aggregate(total=Sum('total'))['total'] or 0
                revenue_data.append({
                    'time': bucket_start.strftime('%d %b'),
                    'value': float(revenue),
                })
        
        # Recent orders
        recent_orders_qs = SalesOrder.objects.filter(tenant=tenant).select_related('customer').order_by('-created_at')[:5]
        recent_orders = [{
            'id': str(order.id),
            'order_number': order.order_number,
            'customer': order.customer.name if order.customer else 'N/A',
            'amount': f"Rs. {order.total:,.0f}",
            'status': order.status
        } for order in recent_orders_qs]
        
        # Top products (by quantity sold)
        from sales.models import SalesOrderLine
        top_products_data = SalesOrderLine.objects.filter(
            sales_order__tenant=tenant,
            sales_order__status__in=['Confirmed', 'Delivered'],
            sales_order__date__gte=start_date
        ).values('product__name').annotate(
            total_qty=Sum('quantity')
        ).order_by('-total_qty')[:5]
        
        max_sales = top_products_data[0]['total_qty'] if top_products_data else 1
        top_products = [{
            'name': item['product__name'] or 'Unknown Product',
            'sales': int(item['total_qty']),
            'max': int(max_sales)
        } for item in top_products_data]
        
        # Recent customers
        recent_customers_qs = Customer.objects.filter(tenant=tenant).order_by('-created_at')[:5]
        recent_customers = [{
            'name': customer.name,
            'email': customer.email or 'No email',
            'initials': ''.join([word[0].upper() for word in customer.name.split()[:2]]),
            'joined': customer.created_at.strftime('%d %b')
        } for customer in recent_customers_qs]
        
        # Inventory summary
        # Note: Product model doesn't have stock_quantity field, it uses Stock model
        # We need to calculate stock status differently
        from inventory.models import Stock
        
        products_qs = Product.objects.filter(tenant=tenant)
        total_skus = products_qs.count()
        
        # Calculate stock status for each product
        in_stock = 0
        low_stock = 0
        out_of_stock = 0
        
        for product in products_qs:
            total_stock = Stock.objects.filter(
                tenant=tenant,
                product=product
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            if total_stock == 0:
                out_of_stock += 1
            elif total_stock <= product.reorder_level:
                low_stock += 1
            else:
                in_stock += 1
        
        return Response({
            'stats': {
                'revenue': f"Rs. {current_revenue:,.0f}",
                'revenueChange': round(revenue_change, 1),
                'orders': current_order_count,
                'ordersChange': round(orders_change, 1),
                'customers': total_customers,
                'customersChange': round(customers_change, 1),
                'newCustomers': new_customers_period,
                'products': total_products,
                'productsChange': round(products_change, 1),
            },
            'revenueData': revenue_data,
            'recentOrders': recent_orders,
            'topProducts': top_products,
            'recentCustomers': recent_customers,
            'inventorySummary': {
                'inStock': in_stock,
                'lowStock': low_stock,
                'outOfStock': out_of_stock,
                'totalSKUs': total_skus
            }
        })


@extend_schema_view(
    list=extend_schema(description="List all quotations for the current tenant", tags=["Sales - Quotations"]),
    retrieve=extend_schema(description="Get quotation details", tags=["Sales - Quotations"]),
    create=extend_schema(description="Create a new quotation", tags=["Sales - Quotations"]),
    update=extend_schema(description="Update quotation", tags=["Sales - Quotations"]),
    partial_update=extend_schema(description="Partially update quotation", tags=["Sales - Quotations"]),
    destroy=extend_schema(description="Delete a quotation", tags=["Sales - Quotations"]),
)
class QuotationViewSet(viewsets.ModelViewSet):
    """ViewSet for Quotation CRUD operations"""
    permission_classes = [DynamicModulePermission]
    permission_module = 'sales'
    filterset_class = QuotationFilterSet
    search_fields = ['quotation_number', 'customer__name']
    ordering_fields = ['date', 'created_at', 'valid_until']
    ordering = ['-date', '-created_at']
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return QuotationCreateSerializer
        return QuotationSerializer
    
    def get_queryset(self):
        """Filter by current tenant"""
        return Quotation.objects.filter(tenant=self.request.user.tenant).select_related('customer', 'created_by').prefetch_related('lines__product')
    
    def perform_create(self, serializer):
        from django.db import transaction
        from django.db.utils import IntegrityError
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                with transaction.atomic():
                    # Generate quotation number with row-level locking
                    # Get all quotations for this tenant and find the max number
                    quotations = Quotation.objects.filter(
                        tenant=self.request.user.tenant
                    ).select_for_update().values_list('quotation_number', flat=True)
                    
                    max_num = 0
                    for qn in quotations:
                        try:
                            num = int(qn.split('-')[1])
                            if num > max_num:
                                max_num = num
                        except (ValueError, IndexError, AttributeError):
                            continue
                    
                    quotation_number = f"QT-{str(max_num + 1).zfill(4)}"
                    
                    serializer.save(
                        created_by=self.request.user,
                        tenant=self.request.user.tenant,
                        quotation_number=quotation_number
                    )
                    break  # Success, exit loop
            except IntegrityError as e:
                if attempt == max_retries - 1:
                    # Last attempt failed, raise the error
                    raise
                # Retry with a new number
                continue

    
    @extend_schema(
        description="Convert quotation to sales order",
        tags=["Sales - Quotations"],
        request=None,
        responses={201: SalesOrderSerializer}
    )
    @action(detail=True, methods=['post'])
    def convert_to_order(self, request, pk=None):
        """Convert a quotation to a sales order"""
        quotation = self.get_object()
        
        if quotation.status == 'Expired':
            return Response(
                {'error': 'Cannot convert expired quotation'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate order number
        last_order = SalesOrder.objects.filter(tenant=request.user.tenant).order_by('-id').first()
        if last_order:
            last_num = int(last_order.order_number.split('-')[1])
            order_number = f"SO-{str(last_num + 1).zfill(4)}"
        else:
            order_number = "SO-0001"
        
        # Create sales order with line items
        # Infer payment type from customer terms
        payment_type = 'credit' if quotation.customer.payment_terms != 'Immediate' else 'cash'

        sales_order = SalesOrder.objects.create(
            tenant=request.user.tenant,
            order_number=order_number,
            date=quotation.date,
            customer=quotation.customer,
            reference=f"From {quotation.quotation_number}",
            status='Draft',
            payment_type=payment_type,
            subtotal=quotation.subtotal,
            discount=quotation.discount,
            tax=quotation.tax,
            total=quotation.total,
            notes=quotation.notes,
            created_by=request.user
        )
        
        # Copy line items from quotation to sales order
        for quote_line in quotation.lines.all():
            SalesOrderLine.objects.create(
                tenant=request.user.tenant,
                sales_order=sales_order,
                product=quote_line.product,
                description=quote_line.description,
                quantity=quote_line.quantity,
                unit_price=quote_line.unit_price,
                discount_percent=quote_line.discount_percent,
                tax_percent=quote_line.tax_percent,
                amount=quote_line.amount
            )
        
        quotation.status = 'Accepted'
        quotation.save()
        
        serializer = SalesOrderSerializer(sales_order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(description="List all invoices for the current tenant", tags=["Sales - Invoices"]),
    retrieve=extend_schema(description="Get invoice details", tags=["Sales - Invoices"]),
    create=extend_schema(description="Create a new invoice", tags=["Sales - Invoices"]),
    update=extend_schema(description="Update invoice", tags=["Sales - Invoices"]),
    partial_update=extend_schema(description="Partially update invoice", tags=["Sales - Invoices"]),
    destroy=extend_schema(description="Delete an invoice", tags=["Sales - Invoices"]),
)
class InvoiceViewSet(viewsets.ModelViewSet):
    """ViewSet for Invoice CRUD operations"""
    permission_classes = [DynamicModulePermission]
    permission_module = 'sales'
    serializer_class = InvoiceSerializer
    filterset_class = InvoiceFilterSet
    search_fields = ['invoice_number', 'customer__name']
    ordering_fields = ['date', 'due_date', 'created_at', 'amount']
    ordering = ['-date', '-created_at']
    
    def get_queryset(self):
        """Filter by current tenant and refresh overdue statuses."""
        from sales.credit_utils import mark_overdue_invoices

        qs = Invoice.objects.filter(tenant=self.request.user.tenant).select_related(
            'customer', 'sales_order', 'created_by'
        )
        mark_overdue_invoices(qs)
        return qs
    
    def perform_create(self, serializer):
        from django.db import transaction
        from django.db.utils import IntegrityError
        from rest_framework.exceptions import ValidationError
        import random
        
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            raise ValidationError({'detail': 'No tenant in context'})

        # Auto-generate invoice number if not provided
        if 'invoice_number' not in serializer.validated_data or not serializer.validated_data.get('invoice_number'):
            max_retries = 10
            last_attempt_number = None
            
            for attempt in range(max_retries):
                try:
                    with transaction.atomic():
                        # Get all invoices for this tenant with locking
                        invoices = Invoice.objects.filter(
                            tenant=self.request.user.tenant
                        ).select_for_update().values_list('invoice_number', flat=True)
                        
                        # Find the highest number
                        max_num = 0
                        for inv_num in invoices:
                            if inv_num and inv_num.startswith('INV-'):
                                try:
                                    num = int(inv_num.split('-')[1])
                                    if num > max_num:
                                        max_num = num
                                except (ValueError, IndexError):
                                    continue
                        
                        # Generate next number with small random offset to avoid collisions
                        if attempt > 0:
                            # Add small random offset on retry
                            invoice_number = f"INV-{str(max_num + 1 + random.randint(0, attempt)).zfill(4)}"
                        else:
                            invoice_number = f"INV-{str(max_num + 1).zfill(4)}"
                        
                        # Avoid using the same number twice in a row
                        if invoice_number == last_attempt_number:
                            invoice_number = f"INV-{str(max_num + 2).zfill(4)}"
                        
                        last_attempt_number = invoice_number
                        
                        serializer.save(
                            tenant=self.request.user.tenant,
                            created_by=self.request.user,
                            invoice_number=invoice_number
                        )
                        break  # Success, exit loop
                except IntegrityError as e:
                    if 'invoice_number' in str(e):
                        if attempt == max_retries - 1:
                            # Last attempt failed, raise a user-friendly error
                            from rest_framework.exceptions import ValidationError
                            raise ValidationError({
                                'invoice_number': 'Unable to generate unique invoice number. Please try again.'
                            })
                        # Retry with next attempt
                        continue
                    else:
                        # Different integrity error, don't retry
                        raise
        else:
            serializer.save(tenant=self.request.user.tenant, created_by=self.request.user)

    
    @extend_schema(
        description="Record payment for an invoice",
        tags=["Sales - Invoices"],
        request={'application/json': {'type': 'object', 'properties': {'amount': {'type': 'number'}}}},
        responses={200: InvoiceSerializer}
    )
    @action(detail=True, methods=['post'])
    def record_payment(self, request, pk=None):
        """Record a payment for an invoice via PaymentReceived (updates ledger + balance)."""
        from django.db import transaction

        invoice = self.get_object()
        payment_amount = request.data.get('amount')

        if not payment_amount:
            return Response(
                {'error': 'Payment amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            payment_amount = Decimal(str(payment_amount))
        except (ValueError, TypeError):
            return Response(
                {'error': 'Invalid payment amount'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if payment_amount <= 0:
            return Response(
                {'error': 'Payment amount must be positive'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if invoice.paid_amount + payment_amount > invoice.amount:
            return Response(
                {'error': 'Payment amount exceeds invoice balance'},
                status=status.HTTP_400_BAD_REQUEST
            )

        payment_date = request.data.get('date') or timezone.now().date()
        if isinstance(payment_date, str):
            try:
                payment_date = dt.strptime(payment_date, '%Y-%m-%d').date()
            except ValueError:
                payment_date = timezone.now().date()

        with transaction.atomic():
            PaymentReceived.objects.create(
                tenant=invoice.tenant,
                date=payment_date,
                customer=invoice.customer,
                amount=payment_amount,
                payment_method=request.data.get('payment_method', 'cash'),
                reference_number=request.data.get('reference_number', '') or '',
                bank_name=request.data.get('bank_name', '') or '',
                invoice=invoice,
                notes=request.data.get('notes', '') or '',
                received_by=request.user,
            )
            invoice.refresh_from_db()

        serializer = self.get_serializer(invoice)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(description="List all credit notes for the current tenant", tags=["Sales - Credit Notes"]),
    retrieve=extend_schema(description="Get credit note details", tags=["Sales - Credit Notes"]),
    create=extend_schema(description="Create a new credit note", tags=["Sales - Credit Notes"]),
    update=extend_schema(description="Update credit note", tags=["Sales - Credit Notes"]),
    partial_update=extend_schema(description="Partially update credit note", tags=["Sales - Credit Notes"]),
    destroy=extend_schema(description="Delete a credit note", tags=["Sales - Credit Notes"]),
)
class CreditNoteViewSet(viewsets.ModelViewSet):
    """ViewSet for Credit Note CRUD operations"""
    permission_classes = [DynamicModulePermission]
    permission_module = 'sales'
    serializer_class = CreditNoteSerializer
    filterset_fields = ['status', 'customer', 'invoice']
    search_fields = ['credit_note_number', 'customer__name']
    ordering_fields = ['date', 'created_at', 'amount']
    ordering = ['-date', '-created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        return CreditNote.objects.filter(tenant=self.request.user.tenant).select_related('customer', 'invoice', 'created_by')
    
    def perform_create(self, serializer):
        from django.db import transaction
        from django.db.utils import IntegrityError
        
        # Auto-generate credit note number if not provided
        if 'credit_note_number' not in serializer.validated_data or not serializer.validated_data.get('credit_note_number'):
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    with transaction.atomic():
                        last_credit_note = CreditNote.objects.filter(
                            tenant=self.request.user.tenant
                        ).select_for_update().order_by('-id').first()
                        
                        if last_credit_note and last_credit_note.credit_note_number.startswith('CN-'):
                            try:
                                last_num = int(last_credit_note.credit_note_number.split('-')[1])
                                credit_note_number = f"CN-{str(last_num + 1).zfill(4)}"
                            except:
                                credit_note_number = "CN-0001"
                        else:
                            credit_note_number = "CN-0001"
                        
                        serializer.save(
                            tenant=self.request.user.tenant,
                            created_by=self.request.user,
                            credit_note_number=credit_note_number
                        )
                        break  # Success, exit loop
                except IntegrityError as e:
                    if attempt == max_retries - 1:
                        raise
                    continue
        else:
            serializer.save(tenant=self.request.user.tenant, created_by=self.request.user)



@extend_schema_view(
    list=extend_schema(tags=['Sales - Ledger'], summary='List customer ledger entries'),
    retrieve=extend_schema(tags=['Sales - Ledger'], summary='Get ledger entry details'),
)
class CustomerLedgerViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Customer Ledger (Read-only)
    Ledger entries are immutable - created automatically by system
    """
    permission_classes = [DynamicModulePermission]
    permission_module = 'sales'
    serializer_class = CustomerLedgerSerializer
    filterset_fields = ['customer', 'transaction_type', 'date']
    search_fields = ['customer__name', 'reference_number', 'description']
    ordering_fields = ['date', 'created_at']
    ordering = ['-date', '-created_at']
    
    def get_queryset(self):
        return CustomerLedger.objects.filter(tenant=self.request.user.tenant).select_related('customer')


@extend_schema_view(
    list=extend_schema(tags=['Sales - Payments'], summary='List all payments received'),
    retrieve=extend_schema(tags=['Sales - Payments'], summary='Get payment details'),
    create=extend_schema(tags=['Sales - Payments'], summary='Record payment received'),
    update=extend_schema(tags=['Sales - Payments'], summary='Update payment'),
    partial_update=extend_schema(tags=['Sales - Payments'], summary='Partially update payment'),
    destroy=extend_schema(tags=['Sales - Payments'], summary='Delete payment'),
)
class PaymentReceivedViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Payment Received
    Automatically creates ledger entry and updates customer balance
    """
    permission_classes = [DynamicModulePermission]
    permission_module = 'sales'
    serializer_class = PaymentReceivedSerializer
    filterset_fields = ['customer', 'payment_method', 'date', 'invoice']
    search_fields = ['payment_number', 'customer__name', 'reference_number']
    ordering_fields = ['date', 'amount', 'created_at']
    ordering = ['-date', '-created_at']
    
    def get_queryset(self):
        tenant = get_request_tenant(self.request.user)
        if not tenant:
            return PaymentReceived.objects.none()
        return PaymentReceived.objects.filter(tenant=tenant).select_related(
            'customer', 'invoice', 'received_by'
        )

    def update(self, request, *args, **kwargs):
        return Response(
            {'error': 'Payments cannot be modified after recording. Create an adjustment instead.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'error': 'Payments cannot be deleted after recording.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )
    
    def perform_create(self, serializer):
        from django.db import transaction
        from django.db.utils import IntegrityError
        from rest_framework.exceptions import ValidationError

        tenant = get_request_tenant(self.request.user)
        if not tenant:
            raise ValidationError({'detail': 'No tenant in context'})

        max_retries = 5
        for attempt in range(max_retries):
            try:
                with transaction.atomic():
                    serializer.save(
                        tenant=tenant,
                        received_by=self.request.user,
                    )
                return
            except IntegrityError:
                if attempt == max_retries - 1:
                    raise ValidationError({'detail': 'Could not generate a unique payment number. Please try again.'})



