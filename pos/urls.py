"""
POS URL Configuration
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    POSSessionViewSet,
    POSDiscountViewSet,
    POSTransactionViewSet,
    POSDailySalesReportViewSet,
    POSProductSearchViewSet,
    POSHeldOrderViewSet,
    POSCashMovementViewSet,
    POSSettingsViewSet,
    POSRefundViewSet,
    LoyaltyProgramViewSet,
    CustomerLoyaltyViewSet,
    ZReportViewSet,
)

router = DefaultRouter()
router.register(r'sessions', POSSessionViewSet, basename='pos-session')
router.register(r'discounts', POSDiscountViewSet, basename='pos-discount')
router.register(r'transactions', POSTransactionViewSet, basename='pos-transaction')
router.register(r'reports', POSDailySalesReportViewSet, basename='pos-report')
router.register(r'products', POSProductSearchViewSet, basename='pos-product')
router.register(r'held-orders', POSHeldOrderViewSet, basename='pos-held-order')
router.register(r'cash-movements', POSCashMovementViewSet, basename='pos-cash-movement')
router.register(r'settings', POSSettingsViewSet, basename='pos-settings')
router.register(r'refunds', POSRefundViewSet, basename='pos-refund')
router.register(r'loyalty-program', LoyaltyProgramViewSet, basename='pos-loyalty-program')
router.register(r'loyalty', CustomerLoyaltyViewSet, basename='pos-loyalty')
router.register(r'z-report', ZReportViewSet, basename='pos-z-report')

urlpatterns = [
    path('', include(router.urls)),
]
