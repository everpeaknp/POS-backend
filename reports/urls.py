from django.urls import path
from .views import ReportViewSet

urlpatterns = [
    # Reports - ViewSet with specific report actions only
    path('', ReportViewSet.as_view({'get': 'list'}), name='report-list'),
    
    # Dashboard & Summary Reports
    path('dashboard-summary/', ReportViewSet.as_view({'get': 'dashboard_summary'}), name='report-dashboard-summary'),
    path('main-dashboard/', ReportViewSet.as_view({'get': 'main_dashboard'}), name='report-main-dashboard'),
    path('summary/', ReportViewSet.as_view({'get': 'summary'}), name='report-summary'),
    
    # Financial Reports
    path('financial-reports/', ReportViewSet.as_view({'get': 'financial_reports'}), name='report-financial-reports'),
    path('profit-and-loss/', ReportViewSet.as_view({'get': 'profit_and_loss'}), name='report-profit-loss'),
    path('revenue-expense-trend/', ReportViewSet.as_view({'get': 'revenue_expense_trend'}), name='report-revenue-expense-trend'),
    
    # Module-Specific Reports
    path('inventory/', ReportViewSet.as_view({'get': 'inventory_valuation'}), name='report-inventory'),
    path('inventory-valuation/', ReportViewSet.as_view({'get': 'inventory_valuation'}), name='report-inventory-valuation'),
    path('sales/', ReportViewSet.as_view({'get': 'sales_performance'}), name='report-sales'),
    path('sales-performance/', ReportViewSet.as_view({'get': 'sales_performance'}), name='report-sales-performance'),
    path('purchase/', ReportViewSet.as_view({'get': 'purchase_reports'}), name='report-purchase'),
    path('purchase-reports/', ReportViewSet.as_view({'get': 'purchase_reports'}), name='report-purchase-reports'),
    path('construction-profitability/', ReportViewSet.as_view({'get': 'construction_profitability'}), name='report-construction-profitability'),
    path('credit-summary/', ReportViewSet.as_view({'get': 'credit_summary'}), name='report-credit-summary'),
    path('tax/', ReportViewSet.as_view({'get': 'tax_reports'}), name='report-tax'),
    path('tax-reports/', ReportViewSet.as_view({'get': 'tax_reports'}), name='report-tax-reports'),
    
    # Custom Reports
    path('custom-reports/fields/', ReportViewSet.as_view({'get': 'custom_reports_fields'}), name='report-custom-reports-fields'),
    path('custom-reports/', ReportViewSet.as_view({'get': 'custom_reports_list'}), name='report-custom-reports-list'),
    path('custom-reports/create/', ReportViewSet.as_view({'post': 'custom_reports_create'}), name='report-custom-reports-create'),
    path('custom-reports/<int:report_id>/', ReportViewSet.as_view({'get': 'custom_reports_detail'}), name='report-custom-reports-detail'),
    path('custom-reports/<int:report_id>/update/', ReportViewSet.as_view({'put': 'custom_reports_update', 'patch': 'custom_reports_update'}), name='report-custom-reports-update'),
    path('custom-reports/<int:report_id>/delete/', ReportViewSet.as_view({'delete': 'custom_reports_delete'}), name='report-custom-reports-delete'),
    path('custom-reports/<int:report_id>/run/', ReportViewSet.as_view({'post': 'custom_reports_run'}), name='report-custom-reports-run'),
    path('custom-reports/<int:report_id>/duplicate/', ReportViewSet.as_view({'post': 'custom_reports_duplicate'}), name='report-custom-reports-duplicate'),
]
