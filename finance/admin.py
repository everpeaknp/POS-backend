from django.contrib import admin
from .models import FinanceAccount, FinanceCategory, FinanceTransaction, FinanceBudget, FinanceBill, PartyLender

@admin.register(FinanceAccount)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'opening_balance', 'current_balance', 'tenant', 'created_at']
    list_filter = ['type', 'tenant']
    search_fields = ['name', 'description']

@admin.register(FinanceCategory)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'tenant', 'created_at']
    list_filter = ['type', 'tenant']
    search_fields = ['name', 'description']

@admin.register(FinanceTransaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_number', 'date', 'type', 'amount', 'category', 'account', 'tenant', 'created_at']
    list_filter = ['type', 'date', 'tenant']
    search_fields = ['transaction_number', 'description']
    date_hierarchy = 'date'

@admin.register(FinanceBudget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'amount', 'period', 'start_date', 'end_date', 'tenant']
    list_filter = ['period', 'tenant']
    search_fields = ['name']

@admin.register(FinanceBill)
class BillAdmin(admin.ModelAdmin):
    list_display = ['bill_number', 'name', 'amount', 'due_date', 'recurring', 'status', 'tenant', 'created_at']
    list_filter = ['recurring', 'status', 'tenant']
    search_fields = ['bill_number', 'name']
    date_hierarchy = 'due_date'

@admin.register(PartyLender)
class PartyLenderAdmin(admin.ModelAdmin):
    list_display = ['name', 'pan', 'mobile', 'email', 'tenant', 'created_at']
    list_filter = ['tenant']
    search_fields = ['name', 'pan', 'mobile', 'email']
