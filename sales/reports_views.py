"""
Sales Reports ViewSet
Comprehensive sales reporting endpoints for analytics and insights
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from users.dynamic_permissions import DynamicModulePermission
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from django.db.models import Sum, Count, F, Q, Avg, DecimalField
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from datetime import timedelta, datetime
from decimal import Decimal

from .models import SalesOrder, Invoice, Customer, SalesOrderLine
from inventory.models import Product


class SalesReportsViewSet(viewsets.ViewSet):
    """
    Comprehensive Sales Reports API
    Provides various sales analytics and insights
    """
    permission_classes = [DynamicModulePermission]
    permission_module = 'sales'
    
    def get_tenant(self):
        """Get current user's tenant"""
        return self.request.user.tenant
    
    def parse_date_params(self, request):
        """Parse start_date and end_date from query params"""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                start_date = None
        
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                end_date = None
        
        return start_date, end_date
    
    @extend_schema(
        tags=['Sales - Reports'],
        summary='Sales Summary Report',
        description='Comprehensive sales summary with monthly trends, orders, revenue, and collection data',
        parameters=[
            OpenApiParameter('start_date', OpenApiTypes.DATE, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('end_date', OpenApiTypes.DATE, description='End date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='sales-summary')
    def sales_summary(self, request):
        """Sales summary report with monthly trends"""
        tenant = self.get_tenant()
        start_date, end_date = self.parse_date_params(request)
        
        # Default to last 6 months if no dates provided
        if not end_date:
            end_date = timezone.now().date()
        if not start_date:
            start_date = end_date - timedelta(days=180)
        
        # Get all delivered/confirmed orders in date range
        orders_qs = SalesOrder.objects.filter(
            tenant=tenant,
            status__in=['Confirmed', 'Delivered'],
            date__gte=start_date,
            date__lte=end_date
        )
        
        # Calculate totals
        total_sales = orders_qs.aggregate(
            total=Coalesce(Sum('total'), Decimal('0.00'))
        )['total']
        
        total_orders = orders_qs.count()
        avg_order_value = (total_sales / total_orders) if total_orders > 0 else Decimal('0.00')
        
        # Calculate cash collected (85% assumption for demo)
        cash_collected = total_sales * Decimal('0.85')
        collection_rate = 85.0
        
        # Monthly sales trend (last 6 months)
        monthly_data = []
        current_month = start_date.replace(day=1)
        end_month = end_date.replace(day=1)
        
        while current_month <= end_month:
            # Calculate next month
            if current_month.month == 12:
                next_month = current_month.replace(year=current_month.year + 1, month=1)
            else:
                next_month = current_month.replace(month=current_month.month + 1)
            
            month_orders = orders_qs.filter(
                date__gte=current_month,
                date__lt=next_month
            )
            
            month_sales = month_orders.aggregate(
                total=Coalesce(Sum('total'), Decimal('0.00'))
            )['total']
            
            month_count = month_orders.count()
            month_collected = month_sales * Decimal('0.85')
            month_outstanding = month_sales * Decimal('0.15')
            
            monthly_data.append({
                'month': current_month.strftime('%b'),
                'sales': float(month_sales),
                'orders': month_count,
                'collected': float(month_collected),
                'outstanding': float(month_outstanding),
            })
            
            current_month = next_month
        
        return Response({
            'summary': {
                'total_sales': float(total_sales),
                'total_orders': total_orders,
                'avg_order_value': float(avg_order_value),
                'cash_collected': float(cash_collected),
                'collection_rate': collection_rate,
            },
            'monthly_trend': monthly_data[-6:],  # Last 6 months
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
            }
        })
    
    @extend_schema(
        tags=['Sales - Reports'],
        summary='Sales by Customer Report',
        description='Revenue and order analysis by customer',
        parameters=[
            OpenApiParameter('start_date', OpenApiTypes.DATE, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('end_date', OpenApiTypes.DATE, description='End date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='by-customer')
    def by_customer(self, request):
        """Sales analysis by customer"""
        tenant = self.get_tenant()
        start_date, end_date = self.parse_date_params(request)
        
        # Base queryset
        orders_qs = SalesOrder.objects.filter(
            tenant=tenant,
            status__in=['Confirmed', 'Delivered']
        )
        
        if start_date:
            orders_qs = orders_qs.filter(date__gte=start_date)
        if end_date:
            orders_qs = orders_qs.filter(date__lte=end_date)
        
        # Aggregate by customer
        customer_data = orders_qs.values(
            'customer__id',
            'customer__name',
            'customer__status'
        ).annotate(
            total_orders=Count('id'),
            total_revenue=Sum('total'),
            avg_order=Avg('total')
        ).order_by('-total_revenue')
        
        customers = []
        for item in customer_data:
            customers.append({
                'customer_id': str(item['customer__id']),
                'customer_name': item['customer__name'],
                'orders': item['total_orders'],
                'revenue': float(item['total_revenue'] or 0),
                'avg_order': float(item['avg_order'] or 0),
                'status': item['customer__status'] or 'active',
            })
        
        return Response({
            'customers': customers,
            'period': {
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
            }
        })
    
    @extend_schema(
        tags=['Sales - Reports'],
        summary='Sales by Product Report',
        description='Revenue and quantity analysis by product',
        parameters=[
            OpenApiParameter('start_date', OpenApiTypes.DATE, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('end_date', OpenApiTypes.DATE, description='End date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='by-product')
    def by_product(self, request):
        """Sales analysis by product"""
        tenant = self.get_tenant()
        start_date, end_date = self.parse_date_params(request)
        
        # Base queryset for order lines
        lines_qs = SalesOrderLine.objects.filter(
            tenant=tenant,
            sales_order__status__in=['Confirmed', 'Delivered']
        )
        
        if start_date:
            lines_qs = lines_qs.filter(sales_order__date__gte=start_date)
        if end_date:
            lines_qs = lines_qs.filter(sales_order__date__lte=end_date)
        
        # Aggregate by product
        product_data = lines_qs.values(
            'product__id',
            'product__name',
            'product__unit'
        ).annotate(
            qty_sold=Sum('quantity'),
            total_revenue=Sum('amount'),
            avg_unit_price=Avg('unit_price')
        ).order_by('-total_revenue')
        
        # Calculate total for percentage
        total_revenue = sum(float(item['total_revenue'] or 0) for item in product_data)
        
        products = []
        for item in product_data:
            revenue = float(item['total_revenue'] or 0)
            percentage = (revenue / total_revenue * 100) if total_revenue > 0 else 0
            
            products.append({
                'product_id': str(item['product__id']),
                'product_name': item['product__name'],
                'unit': item['product__unit'] or 'Pcs',
                'unit_price': float(item['avg_unit_price'] or 0),
                'qty_sold': float(item['qty_sold'] or 0),
                'revenue': revenue,
                'percentage': round(percentage, 2),
            })
        
        return Response({
            'products': products,
            'total_revenue': total_revenue,
            'period': {
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
            }
        })
    
    @extend_schema(
        tags=['Sales - Reports'],
        summary='Sales by Category Report',
        description='Revenue analysis by product category',
        parameters=[
            OpenApiParameter('start_date', OpenApiTypes.DATE, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('end_date', OpenApiTypes.DATE, description='End date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='by-category')
    def by_category(self, request):
        """Sales analysis by product category"""
        tenant = self.get_tenant()
        start_date, end_date = self.parse_date_params(request)
        
        # Base queryset for order lines
        lines_qs = SalesOrderLine.objects.filter(
            tenant=tenant,
            sales_order__status__in=['Confirmed', 'Delivered']
        )
        
        if start_date:
            lines_qs = lines_qs.filter(sales_order__date__gte=start_date)
        if end_date:
            lines_qs = lines_qs.filter(sales_order__date__lte=end_date)
        
        # Aggregate by category
        category_data = lines_qs.values(
            'product__category__id',
            'product__category__name'
        ).annotate(
            total_revenue=Sum('amount'),
            total_orders=Count('sales_order', distinct=True)
        ).order_by('-total_revenue')
        
        # Calculate total for percentage
        total_revenue = float(sum(item['total_revenue'] or 0 for item in category_data))
        
        categories = []
        for item in category_data:
            revenue = float(item['total_revenue'] or 0)
            percentage = (revenue / total_revenue * 100) if total_revenue > 0 else 0
            
            categories.append({
                'category_id': str(item['product__category__id']) if item['product__category__id'] else None,
                'category_name': item['product__category__name'] or 'Uncategorized',
                'revenue': revenue,
                'percentage': round(percentage, 2),
                'orders': item['total_orders'],
            })
        
        return Response({
            'categories': categories,
            'total_revenue': total_revenue,
            'period': {
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
            }
        })
    
    @extend_schema(
        tags=['Sales - Reports'],
        summary='Tax Report',
        description='VAT/Tax collection report by month',
        parameters=[
            OpenApiParameter('start_date', OpenApiTypes.DATE, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('end_date', OpenApiTypes.DATE, description='End date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='tax-report')
    def tax_report(self, request):
        """Tax/VAT collection report"""
        tenant = self.get_tenant()
        start_date, end_date = self.parse_date_params(request)
        
        # Default to last 4 months if no dates provided
        if not end_date:
            end_date = timezone.now().date()
        if not start_date:
            start_date = end_date - timedelta(days=120)
        
        # Get all delivered/confirmed orders in date range
        orders_qs = SalesOrder.objects.filter(
            tenant=tenant,
            status__in=['Confirmed', 'Delivered'],
            date__gte=start_date,
            date__lte=end_date
        )
        
        # Monthly tax data
        monthly_tax = []
        current_month = start_date.replace(day=1)
        end_month = end_date.replace(day=1)
        
        while current_month <= end_month:
            # Calculate next month
            if current_month.month == 12:
                next_month = current_month.replace(year=current_month.year + 1, month=1)
            else:
                next_month = current_month.replace(month=current_month.month + 1)
            
            month_orders = orders_qs.filter(
                date__gte=current_month,
                date__lt=next_month
            )
            
            # Calculate taxable sales (subtotal before tax)
            month_subtotal = month_orders.aggregate(
                total=Coalesce(Sum('subtotal'), Decimal('0.00'))
            )['total']
            
            # Calculate VAT collected (13%)
            month_vat = month_orders.aggregate(
                total=Coalesce(Sum('tax'), Decimal('0.00'))
            )['total']
            
            monthly_tax.append({
                'month': current_month.strftime('%b'),
                'year': current_month.year,
                'taxable_sales': float(month_subtotal),
                'vat_collected': float(month_vat),
                'vat_rate': 13.0,
                'status': 'Filed',
            })
            
            current_month = next_month
        
        # Calculate totals
        total_taxable = sum(item['taxable_sales'] for item in monthly_tax)
        total_vat = sum(item['vat_collected'] for item in monthly_tax)
        
        return Response({
            'summary': {
                'total_taxable_sales': total_taxable,
                'total_vat_collected': total_vat,
                'net_vat_payable': total_vat,
                'vat_rate': 13.0,
            },
            'monthly_data': monthly_tax,
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
            }
        })
