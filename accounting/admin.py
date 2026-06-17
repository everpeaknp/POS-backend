from django.contrib import admin
from .models import Account, JournalEntry, JournalLine, BankAccount, BankTransaction, TaxRule, VATReturn


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'type', 'sub_type', 'balance', 'status', 'tenant']
    list_filter = ['type', 'sub_type', 'status', 'tenant']
    search_fields = ['code', 'name']
    ordering = ['code']


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 2
    fields = ['account', 'description', 'debit', 'credit']


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ['entry_number', 'date', 'description', 'type', 'total_debit', 'total_credit', 'status', 'tenant']
    list_filter = ['status', 'type', 'date', 'tenant']
    search_fields = ['entry_number', 'reference', 'description']
    ordering = ['-date', '-entry_number']
    inlines = [JournalLineInline]
    readonly_fields = ['entry_number', 'total_debit', 'total_credit', 'posted_by', 'posted_date']


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['bank_name', 'account_number', 'type', 'balance', 'status', 'tenant']
    list_filter = ['type', 'status', 'tenant']
    search_fields = ['bank_name', 'account_number', 'account_name']
    ordering = ['bank_name']


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ['bank_account', 'date', 'reference', 'type', 'debit', 'credit', 'balance', 'reconciled', 'tenant']
    list_filter = ['type', 'reconciled', 'date', 'tenant']
    search_fields = ['reference', 'description']
    ordering = ['-date']


@admin.register(TaxRule)
class TaxRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'rate', 'applicable_on', 'status', 'tenant']
    list_filter = ['type', 'applicable_on', 'status', 'tenant']
    search_fields = ['name']
    ordering = ['name']


@admin.register(VATReturn)
class VATReturnAdmin(admin.ModelAdmin):
    list_display = ['return_number', 'period', 'from_date', 'to_date', 'net_payable', 'status', 'tenant']
    list_filter = ['status', 'tenant']
    search_fields = ['return_number', 'period']
    ordering = ['-from_date']
    readonly_fields = ['return_number', 'net_payable']
