from django.urls import path
from .views import (
    SupplierViewSet, PurchaseRequestViewSet, PurchaseOrderViewSet,
    PurchaseInvoiceViewSet, DebitNoteViewSet
)

urlpatterns = [
    # Suppliers
    path('suppliers/', SupplierViewSet.as_view({'get': 'list', 'post': 'create'}), name='supplier-list'),
    path('suppliers/<int:pk>/', SupplierViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='supplier-detail'),
    
    # Purchase Requests
    path('requests/', PurchaseRequestViewSet.as_view({'get': 'list', 'post': 'create'}), name='purchaserequest-list'),
    path('requests/<int:pk>/', PurchaseRequestViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='purchaserequest-detail'),
    path('requests/<int:pk>/approve/', PurchaseRequestViewSet.as_view({'post': 'approve'}), name='purchaserequest-approve'),
    path('requests/<int:pk>/reject/', PurchaseRequestViewSet.as_view({'post': 'reject'}), name='purchaserequest-reject'),
    path('requests/<int:pk>/convert_to_po/', PurchaseRequestViewSet.as_view({'post': 'convert_to_po'}), name='purchaserequest-convert-to-po'),
    
    # Purchase Orders
    path('orders/', PurchaseOrderViewSet.as_view({'get': 'list', 'post': 'create'}), name='purchaseorder-list'),
    path('orders/<int:pk>/', PurchaseOrderViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='purchaseorder-detail'),
    path('orders/<int:pk>/update_status/', PurchaseOrderViewSet.as_view({'patch': 'update_status'}), name='purchaseorder-update-status'),
    path('orders/<int:pk>/receive/', PurchaseOrderViewSet.as_view({'post': 'receive_items'}), name='purchaseorder-receive'),
    
    # Purchase Invoices
    path('invoices/', PurchaseInvoiceViewSet.as_view({'get': 'list', 'post': 'create'}), name='purchaseinvoice-list'),
    path('invoices/<int:pk>/', PurchaseInvoiceViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='purchaseinvoice-detail'),
    path('invoices/<int:pk>/record_payment/', PurchaseInvoiceViewSet.as_view({'post': 'record_payment'}), name='purchaseinvoice-record-payment'),
    
    # Debit Notes
    path('debit-notes/', DebitNoteViewSet.as_view({'get': 'list', 'post': 'create'}), name='debitnote-list'),
    path('debit-notes/<int:pk>/', DebitNoteViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='debitnote-detail'),
]
