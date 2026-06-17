"""
POS Admin Configuration
"""

from django.contrib import admin
from .models import POSSession, POSDiscount, POSTransaction, POSTransactionLine, POSDailySalesReport


@admin.register(POSSession)
class POSSessionAdmin(admin.ModelAdmin):
    list_display = ['session_number', 'cashier', 'opened_at', 'closed_at', 'status', 'total_sales', 'cash_variance', 'tenant']
    list_filter = ['status', 'cashier', 'opened_at', 'tenant']
    search_fields = ['session_number', 'cashier__username']
    readonly_fields = ['session_number', 'opened_at', 'closed_at', 'expected_cash', 'cash_variance', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Session Details', {
            'fields': ('tenant', 'session_number', 'cashier', 'warehouse', 'status')
        }),
        ('Timing', {
            'fields': ('opened_at', 'closed_at')
        }),
        ('Cash Management', {
            'fields': ('opening_cash', 'closing_cash', 'expected_cash', 'cash_variance')
        }),
        ('Session Summary', {
            'fields': ('total_transactions', 'total_sales', 'cash_sales', 'card_sales', 'upi_sales', 'credit_sales')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(POSDiscount)
class POSDiscountAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'discount_type', 'discount_value', 'apply_to', 'is_active', 'tenant']
    list_filter = ['discount_type', 'apply_to', 'is_active', 'tenant']
    search_fields = ['name', 'code', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('tenant', 'name', 'code', 'description')
        }),
        ('Discount Configuration', {
            'fields': ('discount_type', 'discount_value', 'apply_to', 'category', 'product')
        }),
        ('Validity', {
            'fields': ('start_date', 'end_date', 'is_active')
        }),
        ('Requirements', {
            'fields': ('min_quantity', 'min_amount')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


class POSTransactionLineInline(admin.TabularInline):
    model = POSTransactionLine
    extra = 0
    readonly_fields = ['product_name', 'product_sku', 'line_total']
    fields = ['product', 'product_name', 'product_sku', 'quantity', 'unit_price', 'discount_amount', 'line_total']


@admin.register(POSTransaction)
class POSTransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_number', 'date', 'customer_display', 'total', 'payment_method', 'status', 'cashier', 'tenant']
    list_filter = ['status', 'payment_method', 'date', 'tenant']
    search_fields = ['transaction_number', 'customer__name', 'customer_name']
    readonly_fields = ['transaction_number', 'date', 'created_at', 'updated_at']
    inlines = [POSTransactionLineInline]
    
    fieldsets = (
        ('Transaction Details', {
            'fields': ('tenant', 'transaction_number', 'date', 'status')
        }),
        ('Customer', {
            'fields': ('customer', 'customer_name')
        }),
        ('Amounts', {
            'fields': ('subtotal', 'discount_amount', 'tax_amount', 'total')
        }),
        ('Payment', {
            'fields': ('payment_method', 'amount_paid', 'change_given')
        }),
        ('Location & Staff', {
            'fields': ('warehouse', 'cashier')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def customer_display(self, obj):
        if obj.customer:
            return obj.customer.name
        return obj.customer_name or 'Walk-in'
    customer_display.short_description = 'Customer'


@admin.register(POSDailySalesReport)
class POSDailySalesReportAdmin(admin.ModelAdmin):
    list_display = ['date', 'cashier', 'warehouse', 'total_transactions', 'net_sales', 'tenant']
    list_filter = ['date', 'cashier', 'warehouse', 'tenant']
    search_fields = ['cashier__username', 'warehouse__name']
    readonly_fields = ['generated_at', 'generated_by']
    
    fieldsets = (
        ('Report Details', {
            'fields': ('tenant', 'date', 'cashier', 'warehouse')
        }),
        ('Transaction Summary', {
            'fields': ('total_transactions', 'total_items_sold', 'cancelled_transactions')
        }),
        ('Revenue', {
            'fields': ('gross_sales', 'total_discounts', 'total_tax', 'net_sales')
        }),
        ('Payment Methods', {
            'fields': ('cash_sales', 'card_sales', 'upi_sales', 'credit_sales')
        }),
        ('Refunds', {
            'fields': ('refunded_amount',)
        }),
        ('Metadata', {
            'fields': ('generated_at', 'generated_by'),
            'classes': ('collapse',)
        }),
    )
