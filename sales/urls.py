from django.urls import path
from .views import (
    CustomerViewSet, SalesOrderViewSet, QuotationViewSet,
    InvoiceViewSet, CreditNoteViewSet, CustomerLedgerViewSet, PaymentReceivedViewSet
)
from .reports_views import SalesReportsViewSet

urlpatterns = [
    # Customers
    path('customers/', CustomerViewSet.as_view({'get': 'list', 'post': 'create'}), name='customer-list'),
    path('customers/<int:pk>/', CustomerViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='customer-detail'),
    path('customers/<int:pk>/ledger/', CustomerViewSet.as_view({'get': 'ledger'}), name='customer-ledger'),
    path('customers/<int:pk>/credit_summary/', CustomerViewSet.as_view({'get': 'credit_summary'}), name='customer-credit-summary'),
    path('customers/<int:pk>/aging_report/', CustomerViewSet.as_view({'get': 'aging_report'}), name='customer-aging-report'),
    path('customers/credit_overview/', CustomerViewSet.as_view({'get': 'credit_overview'}), name='customer-credit-overview'),
    
    # Sales Orders
    path('orders/', SalesOrderViewSet.as_view({'get': 'list', 'post': 'create'}), name='salesorder-list'),
    path('orders/<int:pk>/', SalesOrderViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='salesorder-detail'),
    path('orders/dashboard/', SalesOrderViewSet.as_view({'get': 'sales_dashboard'}), name='salesorder-dashboard'),
    path('orders/<int:pk>/update_status/', SalesOrderViewSet.as_view({'patch': 'update_status'}), name='salesorder-update-status'),
    path('orders/<int:pk>/finalize_on_credit/', SalesOrderViewSet.as_view({'post': 'finalize_on_credit'}), name='salesorder-finalize-on-credit'),
    
    # Quotations
    path('quotations/', QuotationViewSet.as_view({'get': 'list', 'post': 'create'}), name='quotation-list'),
    path('quotations/<int:pk>/', QuotationViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='quotation-detail'),
    path('quotations/<int:pk>/convert_to_order/', QuotationViewSet.as_view({'post': 'convert_to_order'}), name='quotation-convert-to-order'),
    
    # Invoices
    path('invoices/', InvoiceViewSet.as_view({'get': 'list', 'post': 'create'}), name='invoice-list'),
    path('invoices/<int:pk>/', InvoiceViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='invoice-detail'),
    path('invoices/<int:pk>/record_payment/', InvoiceViewSet.as_view({'post': 'record_payment'}), name='invoice-record-payment'),
    
    # Credit Notes
    path('credit-notes/', CreditNoteViewSet.as_view({'get': 'list', 'post': 'create'}), name='creditnote-list'),
    path('credit-notes/<int:pk>/', CreditNoteViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='creditnote-detail'),
    
    # Customer Ledger
    path('ledger/', CustomerLedgerViewSet.as_view({'get': 'list'}), name='customer-ledger-list'),
    path('ledger/<int:pk>/', CustomerLedgerViewSet.as_view({'get': 'retrieve'}), name='customer-ledger-detail'),
    
    # Payments
    path('payments/', PaymentReceivedViewSet.as_view({'get': 'list', 'post': 'create'}), name='payment-received-list'),
    path('payments/<int:pk>/', PaymentReceivedViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='payment-received-detail'),
    
    # Reports
    path('reports/summary/', SalesReportsViewSet.as_view({'get': 'sales_summary'}), name='sales-reports-summary'),
    path('reports/by_customer/', SalesReportsViewSet.as_view({'get': 'by_customer'}), name='sales-reports-by-customer'),
    path('reports/by_product/', SalesReportsViewSet.as_view({'get': 'by_product'}), name='sales-reports-by-product'),
    path('reports/by_category/', SalesReportsViewSet.as_view({'get': 'by_category'}), name='sales-reports-by-category'),
    path('reports/tax_report/', SalesReportsViewSet.as_view({'get': 'tax_report'}), name='sales-reports-tax'),
]
