from django.urls import path, include
from .views import (
    CategoryViewSet, UnitOfMeasureViewSet, WarehouseViewSet,
    ProductViewSet, StockViewSet, StockMovementViewSet, StockOperationsViewSet,
    InventoryReportsViewSet, BulkPricingViewSet
)
from .pricing_views import (
    CustomerSpecificPriceViewSet, PriceHistoryViewSet, ProductPricingViewSet
)

urlpatterns = [
    # Categories
    path('categories/', CategoryViewSet.as_view({'get': 'list', 'post': 'create'}), name='category-list'),
    path('categories/<int:pk>/', CategoryViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='category-detail'),
    path('categories/tree/', CategoryViewSet.as_view({'get': 'tree'}), name='category-tree'),
    
    # Units
    path('units/', UnitOfMeasureViewSet.as_view({'get': 'list', 'post': 'create'}), name='unit-list'),
    path('units/<int:pk>/', UnitOfMeasureViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='unit-detail'),
    
    # Warehouses
    path('warehouses/', WarehouseViewSet.as_view({'get': 'list', 'post': 'create'}), name='warehouse-list'),
    path('warehouses/<int:pk>/', WarehouseViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='warehouse-detail'),
    path('warehouses/<int:pk>/stock_summary/', WarehouseViewSet.as_view({'get': 'stock_summary'}), name='warehouse-stock-summary'),
    
    # Products
    path('products/', ProductViewSet.as_view({'get': 'list', 'post': 'create'}), name='product-list'),
    path('products/<int:pk>/', ProductViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='product-detail'),
    path('products/low_stock/', ProductViewSet.as_view({'get': 'low_stock'}), name='product-low-stock'),
    path('products/<int:pk>/stock_history/', ProductViewSet.as_view({'get': 'stock_history'}), name='product-stock-history'),
    
    # Stocks
    path('stocks/', StockViewSet.as_view({'get': 'list'}), name='stock-list'),
    path('stocks/<int:pk>/', StockViewSet.as_view({'get': 'retrieve'}), name='stock-detail'),
    
    # Movements
    path('movements/', StockMovementViewSet.as_view({'get': 'list'}), name='movement-list'),
    path('movements/<int:pk>/', StockMovementViewSet.as_view({'get': 'retrieve'}), name='movement-detail'),
    
    # Operations
    path('operations/stock_in/', StockOperationsViewSet.as_view({'post': 'stock_in'}), name='operations-stock-in'),
    path('operations/stock_out/', StockOperationsViewSet.as_view({'post': 'stock_out'}), name='operations-stock-out'),
    path('operations/transfer/', StockOperationsViewSet.as_view({'post': 'transfer'}), name='operations-transfer'),
    path('operations/adjustment/', StockOperationsViewSet.as_view({'post': 'adjustment'}), name='operations-adjustment'),
    
    # Reports
    path('reports/stock-summary/', InventoryReportsViewSet.as_view({'get': 'stock_summary'}), name='inventory-reports-stock-summary'),
    path('reports/low-stock/', InventoryReportsViewSet.as_view({'get': 'low_stock'}), name='inventory-reports-low-stock'),
    path('reports/valuation/', InventoryReportsViewSet.as_view({'get': 'valuation'}), name='inventory-reports-valuation'),
    path('reports/movement/', InventoryReportsViewSet.as_view({'get': 'movement'}), name='inventory-reports-movement'),
    
    # Bulk Pricing
    path('bulk-pricing/', BulkPricingViewSet.as_view({'get': 'list', 'post': 'create'}), name='bulk-pricing-list'),
    path('bulk-pricing/<int:pk>/', BulkPricingViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='bulk-pricing-detail'),
    path('bulk-pricing/by-product/<int:product_id>/', BulkPricingViewSet.as_view({'get': 'by_product'}), name='bulk-pricing-by-product'),
    path('bulk-pricing/get-price/', BulkPricingViewSet.as_view({'get': 'get_price'}), name='bulk-pricing-get-price'),
    
    # Customer-Specific Pricing
    path('customer-prices/', CustomerSpecificPriceViewSet.as_view({'get': 'list', 'post': 'create'}), name='customer-price-list'),
    path('customer-prices/<int:pk>/', CustomerSpecificPriceViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='customer-price-detail'),
    path('customer-prices/by_customer/<int:customer_id>/', CustomerSpecificPriceViewSet.as_view({'get': 'by_customer'}), name='customer-price-by-customer'),
    path('customer-prices/by_product/<int:product_id>/', CustomerSpecificPriceViewSet.as_view({'get': 'by_product'}), name='customer-price-by-product'),
    
    # Price History
    path('price-history/', PriceHistoryViewSet.as_view({'get': 'list'}), name='price-history-list'),
    path('price-history/<int:pk>/', PriceHistoryViewSet.as_view({'get': 'retrieve'}), name='price-history-detail'),
    path('price-history/by_product/<int:product_id>/', PriceHistoryViewSet.as_view({'get': 'by_product'}), name='price-history-by-product'),
    path('price-history/recent/', PriceHistoryViewSet.as_view({'get': 'recent'}), name='price-history-recent'),
    
    # Product Pricing (calculations)
    path('product-pricing/<int:product_id>/', ProductPricingViewSet.as_view({'get': 'get_pricing_detail'}), name='product-pricing-detail'),
    path('product-pricing/calculate/', ProductPricingViewSet.as_view({'post': 'calculate'}), name='product-pricing-calculate'),
    path('product-pricing/bulk_calculate/', ProductPricingViewSet.as_view({'post': 'bulk_calculate'}), name='product-pricing-bulk-calculate'),
]
