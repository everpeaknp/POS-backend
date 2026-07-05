from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from django.db.models import Sum, Count, F, Q, DecimalField, Value, Avg
from django.db.models.functions import Coalesce
from decimal import Decimal
from datetime import datetime, timedelta

from sales.models import SalesOrder, Invoice, Customer, PaymentReceived
from purchase.models import PurchaseInvoice
from construction.models import Site, MaterialConsumption, Attendance
from inventory.models import Product, Stock
from accounting.models import JournalEntry
from users.permissions import ReportsPermission, CanViewFinancials


@extend_schema_view(
    list=extend_schema(tags=['Reports'], summary='List available reports'),
)
class ReportViewSet(viewsets.ViewSet):
    """
    ViewSet for cross-module reporting and analytics.
    All reports use database-level aggregations for performance.
    
    Permissions:
    - Dashboard Summary: All authenticated users
    - Financial Reports: Admin, Manager, Accountant only
    """
    permission_classes = [IsAuthenticated, ReportsPermission]

    def get_permissions(self):
        """Main org dashboard is available to any authenticated tenant member."""
        if getattr(self, 'action', None) in ('main_dashboard', 'dashboard_summary'):
            return [IsAuthenticated()]
        return [IsAuthenticated(), ReportsPermission()]
    
    def get_tenant(self):
        """Get current user's tenant"""
        from tenants.utils import get_request_tenant
        return get_request_tenant(self.request.user)
    
    def parse_date_params(self, request):
        """Parse start_date and end_date from query params"""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        return start_date, end_date
    
    def list(self, request):
        """List available report endpoints"""
        reports = [
            {'name': 'dashboard-summary', 'description': 'Complete dashboard overview'},
            {'name': 'profit-and-loss', 'description': 'Detailed P&L statement'},
            {'name': 'summary', 'description': 'Executive dashboard summary'},
            {'name': 'construction-profitability', 'description': 'Construction site P&L'},
            {'name': 'inventory-valuation', 'description': 'Inventory value by product'},
            {'name': 'credit-summary', 'description': 'Customer credit exposure'},
            {'name': 'revenue-expense-trend', 'description': 'Monthly revenue vs expenses'},
            {'name': 'sales-performance', 'description': 'Sales metrics and top customers'},
        ]
        return Response(reports)
    
    @extend_schema(
        tags=['Reports'],
        summary='Dashboard Summary',
        description='Complete dashboard overview with financials, inventory alerts, and construction budget warnings',
    )
    @action(detail=False, methods=['get'], url_path='dashboard-summary')
    def dashboard_summary(self, request):
        """Complete dashboard summary for main dashboard page"""
        tenant = self.get_tenant()
        
        # ===== FINANCIALS =====
        # Total Receivables (Customer Credit Outstanding)
        total_receivables = Customer.objects.filter(tenant=tenant).aggregate(
            total=Coalesce(Sum('current_balance'), Value(Decimal('0.00')))
        )['total']
        
        # Total Payables (Supplier Credit Outstanding) - Import Supplier model
        try:
            from purchase.models import Supplier
            total_payables = Supplier.objects.filter(tenant=tenant).aggregate(
                total=Coalesce(Sum('current_balance'), Value(Decimal('0.00')))
            )['total']
        except:
            total_payables = Decimal('0.00')
        
        # Revenue calculation
        sales_revenue = SalesOrder.objects.filter(
            tenant=tenant, status='Delivered'
        ).aggregate(
            total=Coalesce(Sum('total'), Value(Decimal('0.00')))
        )['total']
        
        invoice_revenue = Invoice.objects.filter(tenant=tenant).exclude(
            status='Draft'
        ).aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
        )['total']
        
        total_revenue = sales_revenue + invoice_revenue
        
        # Expenses calculation
        purchase_expenses = PurchaseInvoice.objects.filter(
            tenant=tenant, status='Paid'
        ).aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
        )['total']
        
        material_expenses = MaterialConsumption.objects.filter(
            tenant=tenant
        ).aggregate(
            total=Coalesce(Sum(F('quantity') * F('unit_cost'), output_field=DecimalField()), Value(Decimal('0.00')))
        )['total']
        
        labor_expenses = Attendance.objects.filter(tenant=tenant).aggregate(
            total=Coalesce(Sum('wage_amount'), Value(Decimal('0.00')))
        )['total']
        
        total_expenses = purchase_expenses + material_expenses + labor_expenses
        net_profit = total_revenue - total_expenses
        profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')
        
        # ===== INVENTORY - LOW STOCK ALERTS =====
        low_stock_products = Product.objects.filter(tenant=tenant).annotate(
            total_stock=Coalesce(Sum('stocks__quantity'), Value(Decimal('0.00')))
        ).filter(
            total_stock__lt=F('reorder_level')
        ).order_by('total_stock')[:5]
        
        low_stock_items = []
        for product in low_stock_products:
            stock_deficit = product.reorder_level - product.total_stock
            urgency = 'critical' if product.total_stock < (product.reorder_level * Decimal('0.5')) else 'low'
            
            # Get warehouse breakdown
            warehouses = Stock.objects.filter(
                tenant=tenant, product=product
            ).values('warehouse__name').annotate(
                quantity=Sum('quantity')
            )
            
            low_stock_items.append({
                'product_id': str(product.id),
                'product_name': product.name,
                'sku': product.sku,
                'current_stock': float(product.total_stock),
                'reorder_level': float(product.reorder_level),
                'unit': product.unit.name if product.unit else 'unit',
                'stock_deficit': float(stock_deficit),
                'urgency': urgency,
                'warehouses': list(warehouses),
            })
        
        critical_items = sum(1 for item in low_stock_items if item['urgency'] == 'critical')
        
        # ===== CONSTRUCTION - BUDGET ALERTS =====
        sites = Site.objects.filter(tenant=tenant, status='active')
        budget_alert_sites = []
        
        for site in sites:
            # Calculate actual spend
            material_cost = MaterialConsumption.objects.filter(
                tenant=tenant, site=site
            ).aggregate(
                total=Coalesce(Sum(F('quantity') * F('unit_cost'), output_field=DecimalField()), Value(Decimal('0.00')))
            )['total']
            
            labor_cost = Attendance.objects.filter(
                tenant=tenant, site=site
            ).aggregate(
                total=Coalesce(Sum('wage_amount'), Value(Decimal('0.00')))
            )['total']
            
            other_expenses = site.dailylog_set.aggregate(
                total=Coalesce(Sum('other_expenses'), Value(Decimal('0.00')))
            )['total']
            
            actual_spend = material_cost + labor_cost + other_expenses
            budget_utilization = (actual_spend / site.allocated_budget * 100) if site.allocated_budget > 0 else Decimal('0.00')
            
            # Only include sites with >80% budget utilization
            if budget_utilization > 80:
                remaining_budget = site.allocated_budget - actual_spend
                
                if budget_utilization > 100:
                    alert_level = 'critical'
                elif budget_utilization > 95:
                    alert_level = 'high'
                else:
                    alert_level = 'warning'
                
                budget_alert_sites.append({
                    'site_id': str(site.id),
                    'site_name': site.name,
                    'location': site.location,
                    'status': site.status,
                    'allocated_budget': float(site.allocated_budget),
                    'actual_spend': float(actual_spend),
                    'budget_utilization_percentage': float(round(budget_utilization, 2)),
                    'remaining_budget': float(remaining_budget),
                    'alert_level': alert_level,
                    'breakdown': {
                        'material_cost': float(material_cost),
                        'labor_cost': float(labor_cost),
                        'other_expenses': float(other_expenses),
                    }
                })
        
        critical_sites = sum(1 for site in budget_alert_sites if site['alert_level'] == 'critical')
        total_active_sites = sites.count()
        
        return Response({
            'financials': {
                'total_receivables': float(total_receivables),
                'total_payables': float(total_payables),
                'total_revenue': float(total_revenue),
                'total_expenses': float(total_expenses),
                'net_profit': float(net_profit),
                'profit_margin_percentage': float(round(profit_margin, 2)),
                'breakdown': {
                    'sales_revenue': float(sales_revenue),
                    'invoice_revenue': float(invoice_revenue),
                    'purchase_expenses': float(purchase_expenses),
                    'material_expenses': float(material_expenses),
                    'labor_expenses': float(labor_expenses),
                }
            },
            'inventory': {
                'low_stock_items': low_stock_items,
                'total_low_stock_items': len(low_stock_items),
                'critical_items': critical_items,
            },
            'construction': {
                'budget_alert_sites': budget_alert_sites,
                'total_alert_sites': len(budget_alert_sites),
                'critical_sites': critical_sites,
                'total_active_sites': total_active_sites,
            },
            'generated_at': datetime.now().isoformat(),
        })
    
    @extend_schema(
        tags=['Reports'],
        summary='Main Dashboard Data',
        description='Dashboard data matching frontend structure with stats, revenue chart, recent orders, top products, customers, and inventory',
        parameters=[
            OpenApiParameter('period', str, description='Period for revenue chart: today, week, month, year (default: month)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='main-dashboard')
    def main_dashboard(self, request):
        """Main dashboard data for /dashboard page"""
        try:
            from reports.dashboard_modules import build_main_dashboard_response

            tenant = self.get_tenant()
            period = request.query_params.get('period', 'month')
            return Response(build_main_dashboard_response(tenant, period))
        except Exception as e:
            import traceback
            print(f"[Main Dashboard Error] {str(e)}")
            print(traceback.format_exc())
            return Response(
                {'error': str(e), 'detail': 'Failed to load dashboard data'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        tags=['Reports'],
        summary='Profit and Loss Statement',
        description='Detailed P&L report with date range filtering',
        parameters=[
            OpenApiParameter('start_date', str, description='Start date (YYYY-MM-DD)', required=True),
            OpenApiParameter('end_date', str, description='End date (YYYY-MM-DD)', required=True),
        ]
    )
    @action(detail=False, methods=['get'], url_path='profit-and-loss')
    def profit_and_loss(self, request):
        """Detailed Profit & Loss statement"""
        tenant = self.get_tenant()
        start_date, end_date = self.parse_date_params(request)
        
        if not start_date or not end_date:
            return Response(
                {'error': 'Both start_date and end_date are required (YYYY-MM-DD)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        days_in_period = (end_date - start_date).days + 1
        
        # ===== REVENUE =====
        sales_qs = SalesOrder.objects.filter(
            tenant=tenant, date__gte=start_date, date__lte=end_date, status='Delivered'
        )
        sales_revenue_amount = sales_qs.aggregate(
            total=Coalesce(Sum('total'), Value(Decimal('0.00')))
        )['total']
        sales_revenue_count = sales_qs.count()
        
        invoice_qs = Invoice.objects.filter(
            tenant=tenant, date__gte=start_date, date__lte=end_date
        ).exclude(status='Draft')
        invoice_revenue_amount = invoice_qs.aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
        )['total']
        invoice_revenue_count = invoice_qs.count()
        
        payments_qs = PaymentReceived.objects.filter(
            tenant=tenant, date__gte=start_date, date__lte=end_date
        )
        payments_received_amount = payments_qs.aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
        )['total']
        payments_received_count = payments_qs.count()
        
        total_revenue = sales_revenue_amount + invoice_revenue_amount
        
        # ===== EXPENSES =====
        purchase_qs = PurchaseInvoice.objects.filter(
            tenant=tenant, date__gte=start_date, date__lte=end_date, status='Paid'
        )
        purchase_expenses_amount = purchase_qs.aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
        )['total']
        purchase_expenses_count = purchase_qs.count()
        
        material_qs = MaterialConsumption.objects.filter(
            tenant=tenant, daily_log__date__gte=start_date, daily_log__date__lte=end_date
        )
        material_expenses_amount = material_qs.aggregate(
            total=Coalesce(Sum(F('quantity') * F('unit_cost'), output_field=DecimalField()), Value(Decimal('0.00')))
        )['total']
        material_expenses_count = material_qs.count()
        
        labor_qs = Attendance.objects.filter(
            tenant=tenant, date__gte=start_date, date__lte=end_date
        )
        labor_expenses_amount = labor_qs.aggregate(
            total=Coalesce(Sum('wage_amount'), Value(Decimal('0.00')))
        )['total']
        labor_expenses_count = labor_qs.count()
        
        # Other expenses from daily logs
        other_expenses_amount = Decimal('0.00')
        other_expenses_count = 0
        
        total_expenses = purchase_expenses_amount + material_expenses_amount + labor_expenses_amount + other_expenses_amount
        
        # ===== PROFIT METRICS =====
        gross_profit = total_revenue - total_expenses
        gross_profit_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')
        
        # EBITDA (simplified - same as gross profit for now)
        ebitda = gross_profit
        ebitda_margin = gross_profit_margin
        
        net_profit = gross_profit
        net_profit_margin = gross_profit_margin
        
        # ===== METRICS =====
        average_daily_revenue = total_revenue / days_in_period if days_in_period > 0 else Decimal('0.00')
        average_daily_expenses = total_expenses / days_in_period if days_in_period > 0 else Decimal('0.00')
        expense_ratio = (total_expenses / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')
        
        return Response({
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': days_in_period,
            },
            'revenue': {
                'sales_revenue': {
                    'amount': float(sales_revenue_amount),
                    'count': sales_revenue_count,
                },
                'invoice_revenue': {
                    'amount': float(invoice_revenue_amount),
                    'count': invoice_revenue_count,
                },
                'payments_received': {
                    'amount': float(payments_received_amount),
                    'count': payments_received_count,
                },
                'total_revenue': float(total_revenue),
            },
            'expenses': {
                'purchase_expenses': {
                    'amount': float(purchase_expenses_amount),
                    'count': purchase_expenses_count,
                },
                'material_expenses': {
                    'amount': float(material_expenses_amount),
                    'count': material_expenses_count,
                },
                'labor_expenses': {
                    'amount': float(labor_expenses_amount),
                    'count': labor_expenses_count,
                },
                'other_expenses': {
                    'amount': float(other_expenses_amount),
                    'count': other_expenses_count,
                },
                'total_expenses': float(total_expenses),
            },
            'profit': {
                'gross_profit': float(gross_profit),
                'gross_profit_margin_percentage': float(round(gross_profit_margin, 2)),
                'ebitda': float(ebitda),
                'ebitda_margin_percentage': float(round(ebitda_margin, 2)),
                'net_profit': float(net_profit),
                'net_profit_margin_percentage': float(round(net_profit_margin, 2)),
            },
            'metrics': {
                'days_in_period': days_in_period,
                'average_daily_revenue': float(round(average_daily_revenue, 2)),
                'average_daily_expenses': float(round(average_daily_expenses, 2)),
                'expense_ratio_percentage': float(round(expense_ratio, 2)),
            },
        })
    
    
    @extend_schema(
        tags=['Reports'],
        summary='Executive Dashboard Summary',
        description='High-level financial overview across all modules',
        parameters=[
            OpenApiParameter('start_date', str, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('end_date', str, description='End date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Executive dashboard summary with key financial metrics"""
        tenant = self.get_tenant()
        start_date, end_date = self.parse_date_params(request)
        
        # Base querysets
        sales_qs = SalesOrder.objects.filter(tenant=tenant)
        invoice_qs = Invoice.objects.filter(tenant=tenant)
        purchase_qs = PurchaseInvoice.objects.filter(tenant=tenant)
        
        # Apply date filters
        if start_date:
            sales_qs = sales_qs.filter(date__gte=start_date)
            invoice_qs = invoice_qs.filter(date__gte=start_date)
            purchase_qs = purchase_qs.filter(date__gte=start_date)
        if end_date:
            sales_qs = sales_qs.filter(date__lte=end_date)
            invoice_qs = invoice_qs.filter(date__lte=end_date)
            purchase_qs = purchase_qs.filter(date__lte=end_date)
        
        # Revenue calculation
        sales_revenue = sales_qs.filter(status='Delivered').aggregate(
            total=Coalesce(Sum('total'), Value(Decimal('0.00')))
        )['total']
        
        invoice_revenue = invoice_qs.exclude(status='Draft').aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
        )['total']
        
        total_revenue = sales_revenue + invoice_revenue
        
        # Expenses calculation
        purchase_expenses = purchase_qs.filter(status='Paid').aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
        )['total']
        
        # Material consumption expenses
        material_qs = MaterialConsumption.objects.filter(tenant=tenant)
        if start_date:
            material_qs = material_qs.filter(daily_log__date__gte=start_date)
        if end_date:
            material_qs = material_qs.filter(daily_log__date__lte=end_date)
        
        material_expenses = material_qs.aggregate(
            total=Coalesce(Sum(F('quantity') * F('unit_cost'), output_field=DecimalField()), Value(Decimal('0.00')))
        )['total']
        
        # Labor expenses
        attendance_qs = Attendance.objects.filter(tenant=tenant)
        if start_date:
            attendance_qs = attendance_qs.filter(date__gte=start_date)
        if end_date:
            attendance_qs = attendance_qs.filter(date__lte=end_date)
        
        labor_expenses = attendance_qs.aggregate(
            total=Coalesce(Sum('wage_amount'), Value(Decimal('0.00')))
        )['total']
        
        total_expenses = purchase_expenses + material_expenses + labor_expenses
        
        # Net profit
        net_profit = total_revenue - total_expenses
        
        # Cash on hand
        payment_qs = PaymentReceived.objects.filter(tenant=tenant)
        if start_date:
            payment_qs = payment_qs.filter(date__gte=start_date)
        if end_date:
            payment_qs = payment_qs.filter(date__lte=end_date)
        
        cash_on_hand = payment_qs.aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
        )['total']
        
        # Counts
        total_sales_orders = sales_qs.count()
        total_invoices = invoice_qs.count()
        total_customers = Customer.objects.filter(tenant=tenant).count()
        active_sites = Site.objects.filter(tenant=tenant, status='active').count()
        
        return Response({
            'total_revenue': total_revenue,
            'total_expenses': total_expenses,
            'net_profit': net_profit,
            'cash_on_hand': cash_on_hand,
            'total_sales_orders': total_sales_orders,
            'total_invoices': total_invoices,
            'total_customers': total_customers,
            'active_construction_sites': active_sites,
            'period': {
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
            }
        })

    @extend_schema(
        tags=['Reports'],
        summary='Construction Profitability Report',
        description='Multi-site P&L analysis for construction projects',
        parameters=[
            OpenApiParameter('status', str, description='Filter by site status'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='construction-profitability')
    def construction_profitability(self, request):
        """Construction site profitability analysis"""
        tenant = self.get_tenant()
        status_filter = request.query_params.get('status')
        
        sites_qs = Site.objects.filter(tenant=tenant)
        if status_filter:
            sites_qs = sites_qs.filter(status=status_filter)
        
        sites_data = []
        total_budget = Decimal('0.00')
        total_spent = Decimal('0.00')
        
        for site in sites_qs:
            # Material costs
            material_cost = MaterialConsumption.objects.filter(
                tenant=tenant, site=site
            ).aggregate(
                total=Coalesce(Sum(F('quantity') * F('unit_cost'), output_field=DecimalField()), Value(Decimal('0.00')))
            )['total']
            
            # Labor costs
            labor_cost = Attendance.objects.filter(
                tenant=tenant, site=site
            ).aggregate(
                total=Coalesce(Sum('wage_amount'), Value(Decimal('0.00')))
            )['total']
            
            # Other expenses from daily logs
            other_expenses = site.dailylog_set.aggregate(
                total=Coalesce(Sum('other_expenses'), Value(Decimal('0.00')))
            )['total']
            
            total_cost = material_cost + labor_cost + other_expenses
            budget_utilized = (total_cost / site.allocated_budget * 100) if site.allocated_budget > 0 else Decimal('0.00')
            remaining_budget = site.allocated_budget - total_cost
            
            # Budget health
            if budget_utilized < 80:
                budget_health = 'green'
            elif budget_utilized <= 100:
                budget_health = 'yellow'
            else:
                budget_health = 'red'
            
            sites_data.append({
                'site_id': str(site.id),
                'site_name': site.name,
                'location': site.location,
                'status': site.status,
                'allocated_budget': site.allocated_budget,
                'material_cost': material_cost,
                'labor_cost': labor_cost,
                'other_expenses': other_expenses,
                'total_cost': total_cost,
                'budget_utilized_percentage': round(budget_utilized, 2),
                'remaining_budget': remaining_budget,
                'budget_health': budget_health,
            })
            
            total_budget += site.allocated_budget
            total_spent += total_cost
        
        return Response({
            'sites': sites_data,
            'total_sites': len(sites_data),
            'total_budget': total_budget,
            'total_spent': total_spent,
        })
    
    @extend_schema(
        tags=['Reports'],
        summary='Inventory Valuation Report',
        description='Calculate total inventory value using cost price',
        parameters=[
            OpenApiParameter('warehouse', str, description='Filter by warehouse ID'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='inventory-valuation')
    def inventory_valuation(self, request):
        """Inventory valuation by product"""
        tenant = self.get_tenant()
        warehouse_id = request.query_params.get('warehouse')
        
        stocks_qs = Stock.objects.filter(tenant=tenant).select_related('product')
        if warehouse_id:
            stocks_qs = stocks_qs.filter(warehouse_id=warehouse_id)
        
        # Group by product and calculate total value
        product_valuations = stocks_qs.values(
            'product__id', 'product__name', 'product__sku', 'product__cost_price'
        ).annotate(
            total_quantity=Sum('quantity')
        ).annotate(
            total_value=F('total_quantity') * F('product__cost_price')
        )
        
        products_data = []
        total_inventory_value = Decimal('0.00')
        
        for item in product_valuations:
            products_data.append({
                'product_id': str(item['product__id']),
                'product_name': item['product__name'],
                'sku': item['product__sku'],
                'total_quantity': item['total_quantity'],
                'cost_price': item['product__cost_price'],
                'total_value': item['total_value'],
            })
            total_inventory_value += item['total_value'] or Decimal('0.00')
        
        return Response({
            'total_inventory_value': total_inventory_value,
            'products': products_data,
            'total_products': len(products_data),
        })
    
    @extend_schema(
        tags=['Reports'],
        summary='Credit Summary Report',
        description='Customer credit exposure and top debtors',
        parameters=[
            OpenApiParameter('limit', int, description='Number of top debtors (default: 5)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='credit-summary')
    def credit_summary(self, request):
        """Customer credit exposure summary"""
        tenant = self.get_tenant()
        limit = int(request.query_params.get('limit', 5))
        
        # Get customers with outstanding balance
        customers_with_credit = Customer.objects.filter(
            tenant=tenant,
            current_balance__gt=0
        ).order_by('-current_balance')
        
        total_outstanding = customers_with_credit.aggregate(
            total=Coalesce(Sum('current_balance'), Value(Decimal('0.00')))
        )['total']
        
        # Top debtors
        top_debtors = []
        for customer in customers_with_credit[:limit]:
            available_credit = customer.credit_limit - customer.current_balance
            top_debtors.append({
                'customer_id': str(customer.id),
                'customer_name': customer.name,
                'phone': customer.phone,
                'outstanding_balance': customer.current_balance,
                'credit_limit': customer.credit_limit,
                'is_over_limit': customer.current_balance > customer.credit_limit,
                'available_credit': available_credit,
            })
        
        return Response({
            'total_outstanding': total_outstanding,
            'total_customers_with_credit': customers_with_credit.count(),
            'top_debtors': top_debtors,
        })
    
    @extend_schema(
        tags=['Reports'],
        summary='Revenue vs Expense Trend',
        description='Monthly revenue and expense data for charts',
        parameters=[
            OpenApiParameter('months', int, description='Number of months (default: 6)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='revenue-expense-trend')
    def revenue_expense_trend(self, request):
        """Monthly revenue vs expense trend"""
        tenant = self.get_tenant()
        months = int(request.query_params.get('months', 6))
        
        monthly_data = []
        
        for i in range(months - 1, -1, -1):
            # Calculate month start and end
            month_end = datetime.now().date().replace(day=1) - timedelta(days=i * 30)
            month_start = month_end.replace(day=1)
            
            # Revenue for the month
            sales_revenue = SalesOrder.objects.filter(
                tenant=tenant,
                date__gte=month_start,
                date__lt=month_end,
                status='Delivered'
            ).aggregate(
                total=Coalesce(Sum('total'), Value(Decimal('0.00')))
            )['total']
            
            invoice_revenue = Invoice.objects.filter(
                tenant=tenant,
                date__gte=month_start,
                date__lt=month_end
            ).exclude(status='Draft').aggregate(
                total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
            )['total']
            
            revenue = sales_revenue + invoice_revenue
            
            # Expenses for the month
            purchase_expenses = PurchaseInvoice.objects.filter(
                tenant=tenant,
                date__gte=month_start,
                date__lt=month_end,
                status='Paid'
            ).aggregate(
                total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
            )['total']
            
            material_expenses = MaterialConsumption.objects.filter(
                tenant=tenant,
                daily_log__date__gte=month_start,
                daily_log__date__lt=month_end
            ).aggregate(
                total=Coalesce(Sum(F('quantity') * F('unit_cost'), output_field=DecimalField()), Value(Decimal('0.00')))
            )['total']
            
            labor_expenses = Attendance.objects.filter(
                tenant=tenant,
                date__gte=month_start,
                date__lt=month_end
            ).aggregate(
                total=Coalesce(Sum('wage_amount'), Value(Decimal('0.00')))
            )['total']
            
            expenses = purchase_expenses + material_expenses + labor_expenses
            profit = revenue - expenses
            
            monthly_data.append({
                'month': month_start.strftime('%b %Y'),
                'month_date': month_start.isoformat(),
                'revenue': revenue,
                'expenses': expenses,
                'profit': profit,
            })
        
        return Response({
            'monthly_data': monthly_data
        })
    
    @extend_schema(
        tags=['Reports'],
        summary='Sales Performance Report',
        description='Sales metrics and top customers',
        parameters=[
            OpenApiParameter('start_date', str, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('end_date', str, description='End date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='sales-performance')
    def sales_performance(self, request):
        """Sales performance metrics"""
        tenant = self.get_tenant()
        start_date, end_date = self.parse_date_params(request)
        
        # Base queryset
        sales_qs = SalesOrder.objects.filter(tenant=tenant)
        if start_date:
            sales_qs = sales_qs.filter(date__gte=start_date)
        if end_date:
            sales_qs = sales_qs.filter(date__lte=end_date)
        
        # Total sales and orders
        total_sales = sales_qs.aggregate(
            total=Coalesce(Sum('total'), Value(Decimal('0.00')))
        )['total']
        
        total_orders = sales_qs.count()
        average_order_value = (total_sales / total_orders) if total_orders > 0 else Decimal('0.00')
        
        # Top customers
        top_customers_data = sales_qs.values(
            'customer__id', 'customer__name'
        ).annotate(
            total_orders=Count('id'),
            total_amount=Sum('total')
        ).order_by('-total_amount')[:5]
        
        top_customers = []
        for item in top_customers_data:
            top_customers.append({
                'customer_id': str(item['customer__id']),
                'customer_name': item['customer__name'],
                'total_orders': item['total_orders'],
                'total_amount': item['total_amount'],
            })
        
        return Response({
            'total_sales': total_sales,
            'total_orders': total_orders,
            'average_order_value': round(average_order_value, 2),
            'top_customers': top_customers,
            'period': {
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
            }
        })
    
    @extend_schema(
        tags=['Reports'],
        summary='Purchase Reports',
        description='Purchase analytics including summary, by supplier, by product, and tax reports',
        parameters=[
            OpenApiParameter('date_range', str, description='Date range: week, month, quarter, year (default: month)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='purchase-reports')
    def purchase_reports(self, request):
        """Comprehensive purchase reports"""
        try:
            tenant = self.get_tenant()
            date_range = request.query_params.get('date_range', 'month')
            
            # Calculate date range
            from django.utils import timezone
            now = timezone.now().date()
            
            if date_range == 'week':
                start_date = now - timedelta(days=now.weekday() + 1)
            elif date_range == 'quarter':
                quarter_month = ((now.month - 1) // 3) * 3 + 1
                start_date = now.replace(month=quarter_month, day=1)
            elif date_range == 'year':
                start_date = now.replace(month=1, day=1)
            else:  # month
                start_date = now.replace(day=1)
            
            end_date = now
            
            # ===== PURCHASE SUMMARY =====
            invoices_qs = PurchaseInvoice.objects.filter(
                tenant=tenant,
                date__gte=start_date,
                date__lte=end_date
            )
            
            total_purchases = invoices_qs.aggregate(
                total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
            )['total']
            
            total_orders = invoices_qs.count()
            avg_order_value = (total_purchases / total_orders) if total_orders > 0 else Decimal('0.00')
            
            total_paid = invoices_qs.aggregate(
                total=Coalesce(Sum('paid_amount'), Value(Decimal('0.00')))
            )['total']
            
            payment_rate = (total_paid / total_purchases * 100) if total_purchases > 0 else Decimal('0.00')
            
            # ===== BY SUPPLIER =====
            by_supplier = []
            try:
                suppliers_data = invoices_qs.values(
                    'supplier__id', 'supplier__name'
                ).annotate(
                    total_orders=Count('id'),
                    total_amount=Sum('amount'),
                    outstanding=Sum(F('amount') - F('paid_amount'), output_field=DecimalField())
                ).order_by('-total_amount')
                
                for item in suppliers_data:
                    by_supplier.append({
                        'supplier_id': str(item['supplier__id']),
                        'supplier_name': item['supplier__name'] or 'Unknown',
                        'orders': item['total_orders'] or 0,
                        'amount': float(item['total_amount'] or 0),
                        'outstanding': float(item['outstanding'] or 0),
                        'status': 'active',
                    })
            except Exception as e:
                print(f"[Purchase Reports - By Supplier Error] {str(e)}")
            
            # ===== BY PRODUCT =====
            by_product = []
            try:
                from purchase.models import PurchaseOrderLine
                products_data = PurchaseOrderLine.objects.filter(
                    purchase_order__tenant=tenant,
                    purchase_order__date__gte=start_date,
                    purchase_order__date__lte=end_date
                ).values(
                    'product__id', 'product__name', 'product__unit'
                ).annotate(
                    total_qty=Sum('quantity'),
                    total_amount=Sum(F('quantity') * F('unit_price'), output_field=DecimalField()),
                    avg_price=Avg('unit_price')
                ).order_by('-total_amount')
                
                for item in products_data:
                    by_product.append({
                        'product_id': str(item['product__id']),
                        'product_name': item['product__name'] or 'Unknown',
                        'unit': item['product__unit'] or 'unit',
                        'qty': int(item['total_qty'] or 0),
                        'amount': float(item['total_amount'] or 0),
                        'avg_price': float(item['avg_price'] or 0),
                    })
            except Exception as e:
                print(f"[Purchase Reports - By Product Error] {str(e)}")
            
            # ===== TAX REPORT =====
            tax_data = []
            current = start_date
            while current <= end_date:
                # Calculate month end
                if current.month == 12:
                    month_end = current.replace(year=current.year + 1, month=1, day=1) - timedelta(days=1)
                else:
                    month_end = current.replace(month=current.month + 1, day=1) - timedelta(days=1)
                month_end = min(month_end, end_date)
                
                month_invoices = invoices_qs.filter(
                    date__gte=current,
                    date__lte=month_end
                )
                
                taxable_purchases = month_invoices.aggregate(
                    total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
                )['total']
                
                # Assuming 13% VAT
                vat_amount = taxable_purchases * Decimal('0.13')
                
                tax_data.append({
                    'month': current.strftime('%b'),
                    'taxable': float(taxable_purchases),
                    'vat': float(vat_amount),
                })
                
                # Move to next month
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1, day=1)
                else:
                    current = current.replace(month=current.month + 1, day=1)
            
            total_taxable = sum(item['taxable'] for item in tax_data)
            total_vat = sum(item['vat'] for item in tax_data)
            
            # ===== MONTHLY TREND =====
            monthly_trend = []
            current = start_date
            while current <= end_date:
                # Calculate month end
                if current.month == 12:
                    month_end = current.replace(year=current.year + 1, month=1, day=1) - timedelta(days=1)
                else:
                    month_end = current.replace(month=current.month + 1, day=1) - timedelta(days=1)
                month_end = min(month_end, end_date)
                
                month_purchases = invoices_qs.filter(
                    date__gte=current,
                    date__lte=month_end
                ).aggregate(
                    total=Coalesce(Sum('amount'), Value(Decimal('0.00')))
                )['total']
                
                monthly_trend.append({
                    'month': current.strftime('%b'),
                    'purchases': float(month_purchases),
                })
                
                # Move to next month
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1, day=1)
                else:
                    current = current.replace(month=current.month + 1, day=1)
            
            return Response({
                'summary': {
                    'total_purchases': float(total_purchases),
                    'total_orders': total_orders,
                    'avg_order_value': float(avg_order_value),
                    'total_paid': float(total_paid),
                    'payment_rate_percentage': float(round(payment_rate, 2)),
                },
                'by_supplier': by_supplier,
                'by_product': by_product,
                'tax_report': {
                    'total_taxable': float(total_taxable),
                    'total_vat': float(total_vat),
                    'monthly_data': tax_data,
                },
                'monthly_trend': monthly_trend,
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'range': date_range,
                }
            })
        except Exception as e:
            import traceback
            error_msg = str(e)
            tb = traceback.format_exc()
            print(f"[Purchase Reports Error] {error_msg}")
            print(tb)
            return Response(
                {'error': error_msg, 'traceback': tb, 'detail': 'Failed to load purchase reports'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @extend_schema(
        tags=['Reports'],
        summary='Financial Reports',
        description='Comprehensive financial reports including P&L, Balance Sheet, Trial Balance, and Cash Flow',
        parameters=[
            OpenApiParameter('from_date', str, description='Start date for P&L and Cash Flow (YYYY-MM-DD)'),
            OpenApiParameter('to_date', str, description='End date for P&L and Cash Flow (YYYY-MM-DD)'),
            OpenApiParameter('as_of_date', str, description='As of date for Balance Sheet and Trial Balance (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='financial-reports')
    def financial_reports(self, request):
        """Comprehensive financial reports combining P&L, Balance Sheet, Trial Balance, and Cash Flow"""
        try:
            from accounting.models import Account, JournalLine
            from django.utils import timezone
            
            tenant = self.get_tenant()
            
            # Parse date parameters
            from_date_str = request.query_params.get('from_date')
            to_date_str = request.query_params.get('to_date')
            as_of_date_str = request.query_params.get('as_of_date')
            
            # Default dates if not provided
            if not as_of_date_str:
                as_of_date = timezone.now().date()
            else:
                as_of_date = datetime.strptime(as_of_date_str, '%Y-%m-%d').date()
            
            if not from_date_str:
                from_date = as_of_date.replace(day=1)
            else:
                from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            
            if not to_date_str:
                to_date = as_of_date
            else:
                to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
            
            # ===== PROFIT & LOSS =====
            income_accounts = Account.objects.filter(tenant=tenant, type='Income', status='active')
            expense_accounts = Account.objects.filter(tenant=tenant, type='Expense', status='active')
            
            pnl_data = []
            total_income = Decimal('0.00')
            total_expenses = Decimal('0.00')
            
            # Income section
            for account in income_accounts:
                lines = JournalLine.objects.filter(
                    journal_entry__tenant=tenant,
                    journal_entry__status='posted',
                    journal_entry__date__gte=from_date,
                    journal_entry__date__lte=to_date,
                    account=account
                )
                credit_total = lines.aggregate(total=Coalesce(Sum('credit'), Value(Decimal('0.00'))))['total']
                debit_total = lines.aggregate(total=Coalesce(Sum('debit'), Value(Decimal('0.00'))))['total']
                balance = credit_total - debit_total
                
                if balance != 0:
                    total_income += balance
                    pnl_data.append({
                        'account': account.name,
                        'type': 'Income',
                        'amount': float(balance)
                    })
            
            # Expense section
            for account in expense_accounts:
                lines = JournalLine.objects.filter(
                    journal_entry__tenant=tenant,
                    journal_entry__status='posted',
                    journal_entry__date__gte=from_date,
                    journal_entry__date__lte=to_date,
                    account=account
                )
                debit_total = lines.aggregate(total=Coalesce(Sum('debit'), Value(Decimal('0.00'))))['total']
                credit_total = lines.aggregate(total=Coalesce(Sum('credit'), Value(Decimal('0.00'))))['total']
                balance = debit_total - credit_total
                
                if balance != 0:
                    total_expenses += balance
                    pnl_data.append({
                        'account': account.name,
                        'type': 'Expense',
                        'amount': float(balance)
                    })
            
            net_profit = total_income - total_expenses
            
            # ===== BALANCE SHEET =====
            asset_accounts = Account.objects.filter(tenant=tenant, type='Assets', status='active')
            liability_accounts = Account.objects.filter(tenant=tenant, type='Liabilities', status='active')
            equity_accounts = Account.objects.filter(tenant=tenant, type='Equity', status='active')
            
            balance_sheet_data = {
                'assets': [],
                'liabilities': [],
                'equity': []
            }
            total_assets = Decimal('0.00')
            total_liabilities = Decimal('0.00')
            total_equity = Decimal('0.00')
            
            # Assets
            for account in asset_accounts:
                lines = JournalLine.objects.filter(
                    journal_entry__tenant=tenant,
                    journal_entry__status='posted',
                    journal_entry__date__lte=as_of_date,
                    account=account
                )
                debit_total = lines.aggregate(total=Coalesce(Sum('debit'), Value(Decimal('0.00'))))['total']
                credit_total = lines.aggregate(total=Coalesce(Sum('credit'), Value(Decimal('0.00'))))['total']
                balance = debit_total - credit_total
                
                if balance != 0:
                    total_assets += balance
                    balance_sheet_data['assets'].append({
                        'account': account.name,
                        'amount': float(balance)
                    })
            
            # Liabilities
            for account in liability_accounts:
                lines = JournalLine.objects.filter(
                    journal_entry__tenant=tenant,
                    journal_entry__status='posted',
                    journal_entry__date__lte=as_of_date,
                    account=account
                )
                credit_total = lines.aggregate(total=Coalesce(Sum('credit'), Value(Decimal('0.00'))))['total']
                debit_total = lines.aggregate(total=Coalesce(Sum('debit'), Value(Decimal('0.00'))))['total']
                balance = credit_total - debit_total
                
                if balance != 0:
                    total_liabilities += balance
                    balance_sheet_data['liabilities'].append({
                        'account': account.name,
                        'amount': float(balance)
                    })
            
            # Equity
            for account in equity_accounts:
                lines = JournalLine.objects.filter(
                    journal_entry__tenant=tenant,
                    journal_entry__status='posted',
                    journal_entry__date__lte=as_of_date,
                    account=account
                )
                credit_total = lines.aggregate(total=Coalesce(Sum('credit'), Value(Decimal('0.00'))))['total']
                debit_total = lines.aggregate(total=Coalesce(Sum('debit'), Value(Decimal('0.00'))))['total']
                balance = credit_total - debit_total
                
                if balance != 0:
                    total_equity += balance
                    balance_sheet_data['equity'].append({
                        'account': account.name,
                        'amount': float(balance)
                    })
            
            # ===== TRIAL BALANCE =====
            all_accounts = Account.objects.filter(tenant=tenant, status='active', level__gt=0).order_by('type', 'code')
            trial_balance_data = []
            total_debit = Decimal('0.00')
            total_credit = Decimal('0.00')
            
            for account in all_accounts:
                lines = JournalLine.objects.filter(
                    journal_entry__tenant=tenant,
                    journal_entry__status='posted',
                    journal_entry__date__lte=as_of_date,
                    account=account
                )
                debit_sum = lines.aggregate(total=Coalesce(Sum('debit'), Value(Decimal('0.00'))))['total']
                credit_sum = lines.aggregate(total=Coalesce(Sum('credit'), Value(Decimal('0.00'))))['total']
                
                if debit_sum != 0 or credit_sum != 0:
                    total_debit += debit_sum
                    total_credit += credit_sum
                    trial_balance_data.append({
                        'account': account.name,
                        'debit': float(debit_sum),
                        'credit': float(credit_sum)
                    })
            
            # ===== CASH FLOW (Simplified) =====
            # Operating activities: Net profit + adjustments
            operating_cash = net_profit
            
            # Investing activities: Fixed asset purchases (simplified)
            investing_cash = Decimal('0.00')
            
            # Financing activities: Capital and loans (simplified)
            financing_cash = Decimal('0.00')
            
            # Get opening and closing cash balances
            cash_accounts = Account.objects.filter(
                tenant=tenant,
                status='active',
                name__icontains='cash'
            )
            
            opening_cash = Decimal('0.00')
            closing_cash = Decimal('0.00')
            
            for account in cash_accounts:
                # Opening balance (before from_date)
                opening_lines = JournalLine.objects.filter(
                    journal_entry__tenant=tenant,
                    journal_entry__status='posted',
                    journal_entry__date__lt=from_date,
                    account=account
                )
                opening_debit = opening_lines.aggregate(total=Coalesce(Sum('debit'), Value(Decimal('0.00'))))['total']
                opening_credit = opening_lines.aggregate(total=Coalesce(Sum('credit'), Value(Decimal('0.00'))))['total']
                opening_cash += (opening_debit - opening_credit)
                
                # Closing balance (up to to_date)
                closing_lines = JournalLine.objects.filter(
                    journal_entry__tenant=tenant,
                    journal_entry__status='posted',
                    journal_entry__date__lte=to_date,
                    account=account
                )
                closing_debit = closing_lines.aggregate(total=Coalesce(Sum('debit'), Value(Decimal('0.00'))))['total']
                closing_credit = closing_lines.aggregate(total=Coalesce(Sum('credit'), Value(Decimal('0.00'))))['total']
                closing_cash += (closing_debit - closing_credit)
            
            net_cash_change = closing_cash - opening_cash
            
            return Response({
                'profit_and_loss': {
                    'period': {
                        'from_date': from_date.isoformat(),
                        'to_date': to_date.isoformat()
                    },
                    'income': [item for item in pnl_data if item['type'] == 'Income'],
                    'expenses': [item for item in pnl_data if item['type'] == 'Expense'],
                    'total_income': float(total_income),
                    'total_expenses': float(total_expenses),
                    'net_profit': float(net_profit)
                },
                'balance_sheet': {
                    'as_of_date': as_of_date.isoformat(),
                    'assets': balance_sheet_data['assets'],
                    'liabilities': balance_sheet_data['liabilities'],
                    'equity': balance_sheet_data['equity'],
                    'total_assets': float(total_assets),
                    'total_liabilities': float(total_liabilities),
                    'total_equity': float(total_equity)
                },
                'trial_balance': {
                    'as_of_date': as_of_date.isoformat(),
                    'accounts': trial_balance_data,
                    'total_debit': float(total_debit),
                    'total_credit': float(total_credit)
                },
                'cash_flow': {
                    'period': {
                        'from_date': from_date.isoformat(),
                        'to_date': to_date.isoformat()
                    },
                    'operating_activities': float(operating_cash),
                    'investing_activities': float(investing_cash),
                    'financing_activities': float(financing_cash),
                    'net_cash_change': float(net_cash_change),
                    'opening_cash': float(opening_cash),
                    'closing_cash': float(closing_cash)
                }
            })
        except Exception as e:
            import traceback
            error_msg = str(e)
            tb = traceback.format_exc()
            print(f"[Financial Reports Error] {error_msg}")
            print(tb)
            return Response(
                {'error': error_msg, 'traceback': tb, 'detail': 'Failed to load financial reports'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @extend_schema(
        tags=['Reports'],
        summary='Tax Reports',
        description='Comprehensive tax reports including VAT, TDS, and Income Tax summaries',
        parameters=[
            OpenApiParameter('from_date', str, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('to_date', str, description='End date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='tax-reports')
    def tax_reports(self, request):
        """Comprehensive tax reports including VAT, TDS, and Income Tax"""
        try:
            tenant = self.get_tenant()
            
            # Parse date parameters
            from_date_str = request.query_params.get('from_date')
            to_date_str = request.query_params.get('to_date')
            
            # Default to current fiscal year if not provided
            if not from_date_str or not to_date_str:
                today = datetime.now().date()
                # Assuming fiscal year starts in July (Shrawan)
                if today.month >= 7:
                    from_date = today.replace(month=7, day=1)
                    to_date = today
                else:
                    from_date = today.replace(year=today.year - 1, month=7, day=1)
                    to_date = today
            else:
                from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
                to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
            
            # Return minimal working data structure
            return Response({
                'period': {
                    'from_date': from_date.isoformat(),
                    'to_date': to_date.isoformat()
                },
                'vat': {
                    'output_vat': 0.0,
                    'input_vat': 0.0,
                    'net_payable': 0.0,
                    'returns_filed': 0,
                    'monthly': []
                },
                'tds': {
                    'total_deducted': 0.0,
                    'on_services': 0.0,
                    'on_rent': 0.0,
                    'on_goods': 0.0,
                    'details': []
                },
                'income_tax': {
                    'employees': []
                }
            })
        except Exception as e:
            import traceback
            error_msg = str(e)
            tb = traceback.format_exc()
            print(f"[Tax Reports Error] {error_msg}")
            print(tb)
            return Response(
                {'error': error_msg, 'traceback': tb, 'detail': 'Failed to load tax reports'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @extend_schema(
        tags=['Reports'],
        summary='List custom reports',
        description='Get all custom reports for the current tenant',
        parameters=[
            OpenApiParameter('module', str, description='Filter by module (sales, purchase, etc.)'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='custom-reports')
    def custom_reports_list(self, request):
        """List all custom reports for the current tenant"""
        from .models import CustomReport
        from .serializers import CustomReportSerializer
        
        try:
            tenant = self.get_tenant()
            
            # Get all custom reports for this tenant
            reports = CustomReport.objects.filter(tenant=tenant)
            
            # Filter by module if provided
            module = request.query_params.get('module')
            if module:
                reports = reports.filter(module=module)
            
            # Filter by created_by if user wants only their reports
            only_mine = request.query_params.get('only_mine', 'false').lower() == 'true'
            if only_mine:
                reports = reports.filter(created_by=request.user)
            
            serializer = CustomReportSerializer(reports, many=True, context={'request': request})
            
            return Response({
                'count': reports.count(),
                'results': serializer.data
            })
        except Exception as e:
            import traceback
            print(f"[Custom Reports List Error] {str(e)}")
            print(traceback.format_exc())
            return Response(
                {'detail': 'Failed to load custom reports', 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        tags=['Reports'],
        summary='Create custom report',
        description='Create a new custom report configuration',
    )
    @action(detail=False, methods=['post'], url_path='custom-reports/create')
    def custom_reports_create(self, request):
        """Create a new custom report"""
        from .models import CustomReport
        from .serializers import CustomReportSerializer
        
        try:
            serializer = CustomReportSerializer(data=request.data, context={'request': request})
            
            if serializer.is_valid():
                report = serializer.save()
                return Response(
                    {
                        'message': 'Custom report created successfully',
                        'report': CustomReportSerializer(report, context={'request': request}).data
                    },
                    status=status.HTTP_201_CREATED
                )
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            import traceback
            print(f"[Custom Report Create Error] {str(e)}")
            print(traceback.format_exc())
            return Response(
                {'detail': 'Failed to create custom report', 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        tags=['Reports'],
        summary='Get custom report details',
        description='Get details of a specific custom report',
    )
    @action(detail=False, methods=['get'], url_path='custom-reports/(?P<report_id>[^/.]+)')
    def custom_reports_detail(self, request, report_id=None):
        """Get details of a specific custom report"""
        from .models import CustomReport
        from .serializers import CustomReportSerializer
        
        try:
            tenant = self.get_tenant()
            report = CustomReport.objects.get(id=report_id, tenant=tenant)
            serializer = CustomReportSerializer(report, context={'request': request})
            return Response(serializer.data)
        except CustomReport.DoesNotExist:
            return Response(
                {'detail': 'Custom report not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            import traceback
            print(f"[Custom Report Detail Error] {str(e)}")
            print(traceback.format_exc())
            return Response(
                {'detail': 'Failed to load custom report', 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        tags=['Reports'],
        summary='Update custom report',
        description='Update an existing custom report',
    )
    @action(detail=False, methods=['put', 'patch'], url_path='custom-reports/(?P<report_id>[^/.]+)/update')
    def custom_reports_update(self, request, report_id=None):
        """Update a custom report"""
        from .models import CustomReport
        from .serializers import CustomReportSerializer
        
        try:
            tenant = self.get_tenant()
            report = CustomReport.objects.get(id=report_id, tenant=tenant)
            
            # Check if user has permission to update (creator or admin)
            if report.created_by != request.user and not request.user.is_staff:
                return Response(
                    {'detail': 'You do not have permission to update this report'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            partial = request.method == 'PATCH'
            serializer = CustomReportSerializer(
                report, 
                data=request.data, 
                partial=partial,
                context={'request': request}
            )
            
            if serializer.is_valid():
                report = serializer.save()
                return Response({
                    'message': 'Custom report updated successfully',
                    'report': CustomReportSerializer(report, context={'request': request}).data
                })
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except CustomReport.DoesNotExist:
            return Response(
                {'detail': 'Custom report not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            import traceback
            print(f"[Custom Report Update Error] {str(e)}")
            print(traceback.format_exc())
            return Response(
                {'detail': 'Failed to update custom report', 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        tags=['Reports'],
        summary='Delete custom report',
        description='Delete a custom report',
    )
    @action(detail=False, methods=['delete'], url_path='custom-reports/(?P<report_id>[^/.]+)/delete')
    def custom_reports_delete(self, request, report_id=None):
        """Delete a custom report"""
        from .models import CustomReport
        
        try:
            tenant = self.get_tenant()
            report = CustomReport.objects.get(id=report_id, tenant=tenant)
            
            # Check if user has permission to delete (creator or admin)
            if report.created_by != request.user and not request.user.is_staff:
                return Response(
                    {'detail': 'You do not have permission to delete this report'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            report_name = report.name
            report.delete()
            
            return Response({
                'message': f'Custom report "{report_name}" deleted successfully'
            })
        except CustomReport.DoesNotExist:
            return Response(
                {'detail': 'Custom report not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            import traceback
            print(f"[Custom Report Delete Error] {str(e)}")
            print(traceback.format_exc())
            return Response(
                {'detail': 'Failed to delete custom report', 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        tags=['Reports'],
        summary='Run custom report',
        description='Execute a custom report and return results',
        parameters=[
            OpenApiParameter('from_date', str, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('to_date', str, description='End date (YYYY-MM-DD)'),
        ]
    )
    @action(detail=False, methods=['post'], url_path='custom-reports/(?P<report_id>[^/.]+)/run')
    def custom_reports_run(self, request, report_id=None):
        """Run a custom report and return results"""
        from .models import CustomReport
        from django.utils import timezone
        
        try:
            tenant = self.get_tenant()
            report = CustomReport.objects.get(id=report_id, tenant=tenant)
            
            # Update last_run timestamp
            report.last_run = timezone.now()
            report.save(update_fields=['last_run'])
            
            # Parse date parameters
            from_date_str = request.data.get('from_date') or request.query_params.get('from_date')
            to_date_str = request.data.get('to_date') or request.query_params.get('to_date')
            
            # For now, return mock data structure
            # In production, this would execute the actual query based on report configuration
            return Response({
                'report_name': report.name,
                'module': report.module,
                'executed_at': timezone.now().isoformat(),
                'parameters': {
                    'from_date': from_date_str,
                    'to_date': to_date_str,
                },
                'data': {
                    'columns': report.fields or ['Date', 'Amount', 'Status'],
                    'rows': [
                        {'Date': '2082-01-15', 'Amount': 50000, 'Status': 'Completed'},
                        {'Date': '2082-01-14', 'Amount': 35000, 'Status': 'Pending'},
                        {'Date': '2082-01-13', 'Amount': 42000, 'Status': 'Completed'},
                    ],
                    'summary': {
                        'total_rows': 3,
                        'total_amount': 127000,
                    }
                },
                'chart_data': report.chart_config if report.report_type in ['chart', 'both'] else None
            })
        except CustomReport.DoesNotExist:
            return Response(
                {'detail': 'Custom report not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            import traceback
            print(f"[Custom Report Run Error] {str(e)}")
            print(traceback.format_exc())
            return Response(
                {'detail': 'Failed to run custom report', 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        tags=['Reports'],
        summary='Duplicate custom report',
        description='Create a copy of an existing custom report',
    )
    @action(detail=False, methods=['post'], url_path='custom-reports/(?P<report_id>[^/.]+)/duplicate')
    def custom_reports_duplicate(self, request, report_id=None):
        """Duplicate a custom report"""
        from .models import CustomReport
        from .serializers import CustomReportSerializer
        
        try:
            tenant = self.get_tenant()
            original_report = CustomReport.objects.get(id=report_id, tenant=tenant)
            
            # Create a copy
            new_report = CustomReport.objects.create(
                tenant=tenant,
                name=f"{original_report.name} (Copy)",
                description=original_report.description,
                report_type=original_report.report_type,
                module=original_report.module,
                fields=original_report.fields,
                filters=original_report.filters,
                grouping=original_report.grouping,
                sorting=original_report.sorting,
                chart_config=original_report.chart_config,
                schedule=original_report.schedule,
                created_by=request.user,
                is_shared=False
            )
            
            serializer = CustomReportSerializer(new_report, context={'request': request})
            
            return Response({
                'message': 'Custom report duplicated successfully',
                'report': serializer.data
            }, status=status.HTTP_201_CREATED)
        except CustomReport.DoesNotExist:
            return Response(
                {'detail': 'Custom report not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            import traceback
            print(f"[Custom Report Duplicate Error] {str(e)}")
            print(traceback.format_exc())
            return Response(
                {'detail': 'Failed to duplicate custom report', 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
