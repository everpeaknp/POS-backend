from django.urls import path
from .views import (
    AccountViewSet, JournalEntryViewSet, BankAccountViewSet,
    BankTransactionViewSet, TaxRuleViewSet, VATReturnViewSet
)

urlpatterns = [
    # Accounts
    path('accounts/', AccountViewSet.as_view({'get': 'list', 'post': 'create'}), name='account-list'),
    path('accounts/<int:pk>/', AccountViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='account-detail'),
    path('accounts/tree/', AccountViewSet.as_view({'get': 'tree'}), name='account-tree'),
    path('accounts/<int:pk>/ledger/', AccountViewSet.as_view({'get': 'ledger'}), name='account-ledger'),
    path('accounts/trial_balance/', AccountViewSet.as_view({'get': 'trial_balance'}), name='account-trial-balance'),
    path('accounts/profit_loss/', AccountViewSet.as_view({'get': 'profit_loss'}), name='account-profit-loss'),
    path('accounts/balance_sheet/', AccountViewSet.as_view({'get': 'balance_sheet'}), name='account-balance-sheet'),
    
    # Journal Entries
    path('journal-entries/', JournalEntryViewSet.as_view({'get': 'list', 'post': 'create'}), name='journal-entry-list'),
    path('journal-entries/<int:pk>/', JournalEntryViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='journal-entry-detail'),
    path('journal-entries/<int:pk>/post_entry/', JournalEntryViewSet.as_view({'post': 'post_entry'}), name='journal-entry-post'),
    path('journal-entries/<int:pk>/reverse/', JournalEntryViewSet.as_view({'post': 'reverse'}), name='journal-entry-reverse'),
    
    # Bank Accounts
    path('bank-accounts/', BankAccountViewSet.as_view({'get': 'list', 'post': 'create'}), name='bank-account-list'),
    path('bank-accounts/<int:pk>/', BankAccountViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='bank-account-detail'),
    path('bank-accounts/<int:pk>/statement/', BankAccountViewSet.as_view({'get': 'statement'}), name='bank-account-statement'),
    
    # Bank Transactions
    path('bank-transactions/', BankTransactionViewSet.as_view({'get': 'list', 'post': 'create'}), name='bank-transaction-list'),
    path('bank-transactions/<int:pk>/', BankTransactionViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='bank-transaction-detail'),
    path('bank-transactions/<int:pk>/reconcile/', BankTransactionViewSet.as_view({'post': 'reconcile'}), name='bank-transaction-reconcile'),
    
    # Tax Rules
    path('tax-rules/', TaxRuleViewSet.as_view({'get': 'list', 'post': 'create'}), name='tax-rule-list'),
    path('tax-rules/<int:pk>/', TaxRuleViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='tax-rule-detail'),
    
    # VAT Returns
    path('vat-returns/', VATReturnViewSet.as_view({'get': 'list', 'post': 'create'}), name='vat-return-list'),
    path('vat-returns/<int:pk>/', VATReturnViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='vat-return-detail'),
    path('vat-returns/<int:pk>/file/', VATReturnViewSet.as_view({'post': 'file'}), name='vat-return-file'),
    path('vat-returns/<int:pk>/mark_paid/', VATReturnViewSet.as_view({'post': 'mark_paid'}), name='vat-return-mark-paid'),
]
