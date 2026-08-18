from django.urls import path
from .views import (
    PartyLenderViewSet, AccountViewSet, CategoryViewSet,
    TransactionViewSet, BudgetViewSet, BillViewSet
)

urlpatterns = [
    # Parties/Lenders
    path('parties/', PartyLenderViewSet.as_view({'get': 'list', 'post': 'create'}), name='party-list'),
    path('parties/<int:pk>/', PartyLenderViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='party-detail'),
    
    # Accounts
    path('accounts/', AccountViewSet.as_view({'get': 'list', 'post': 'create'}), name='account-list'),
    path('accounts/<int:pk>/', AccountViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='account-detail'),
    
    # Categories
    path('categories/', CategoryViewSet.as_view({'get': 'list', 'post': 'create'}), name='category-list'),
    path('categories/<int:pk>/', CategoryViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='category-detail'),
    
    # Transactions
    path('transactions/', TransactionViewSet.as_view({'get': 'list', 'post': 'create'}), name='transaction-list'),
    path('transactions/<int:pk>/', TransactionViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='transaction-detail'),
    path('transactions/summary/', TransactionViewSet.as_view({'get': 'summary'}), name='transaction-summary'),
    
    # Budgets
    path('budgets/', BudgetViewSet.as_view({'get': 'list', 'post': 'create'}), name='budget-list'),
    path('budgets/<int:pk>/', BudgetViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='budget-detail'),
    
    # Bills
    path('bills/', BillViewSet.as_view({'get': 'list', 'post': 'create'}), name='bill-list'),
    path('bills/<int:pk>/', BillViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='bill-detail'),
    path('bills/upcoming/', BillViewSet.as_view({'get': 'upcoming'}), name='bill-upcoming'),
]
