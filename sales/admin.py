from django.contrib import admin
from .models import (
    Customer, SalesOrder, SalesOrderLine, Quotation, QuotationLine, Invoice, CreditNote,
    CustomerLedger, PaymentReceived
)


class CustomerLedgerInline(admin.TabularInline):
    """Inline display of customer ledger entries (read-only)"""
    model = CustomerLedger
    extra = 0
    can_delete = False
    max_num = 10
    fields = ['date', 'transaction_type', 'reference_number', 'debit_amount', 'credit_amount', 'running_balance', 'description']
    readonly_fields = ['date', 'transaction_type', 'reference_number', 'debit_amount', 'credit_amount', 'running_balance', 'description']
    
    def has_add_permission(self, request, obj=None):
        return False


class PaymentReceivedInline(admin.TabularInline):
    """Inline display of payments received from customer"""
    model = PaymentReceived
    extra = 0
    fields = ['payment_number', 'date', 'amount', 'payment_method', 'reference_number', 'received_by']
    readonly_fields = ['payment_number', 'received_by']
    autocomplete_fields = ['invoice']


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'phone', 'email', 'type', 'status_badge', 
        'credit_limit', 'current_balance', 'outstanding_balance', 
        'total_paid', 'created_at'
    ]
    list_filter = ['status', 'type', 'payment_terms', 'tenant', 'created_at']
    search_fields = ['name', 'phone', 'email', 'pan', 'address']
    ordering = ['-created_at']
    readonly_fields = ['current_balance', 'outstanding_balance', 'total_paid', 'available_credit', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    list_per_page = 25
    actions = ['activate_customers', 'deactivate_customers', 'export_to_csv']
    inlines = [CustomerLedgerInline, PaymentReceivedInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'type', 'status')
        }),
        ('Contact Details', {
            'fields': ('phone', 'email', 'address')
        }),
        ('Business Details', {
            'fields': ('pan', 'payment_terms')
        }),
        ('Credit Management', {
            'fields': ('credit_limit', 'current_balance', 'outstanding_balance', 'available_credit'),
            'description': 'Credit limit and balance information for this customer'
        }),
        ('Audit Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        """Display status with color coding"""
        if obj.status == 'active':
            color = 'green'
            icon = '✓'
        else:
            color = 'red'
            icon = '✗'
        return f'<span style="color: {color}; font-weight: bold;">{icon} {obj.get_status_display()}</span>'
    status_badge.short_description = 'Status'
    status_badge.allow_tags = True
    
    def outstanding_balance(self, obj):
        """Display outstanding balance (same as current_balance)"""
        return f"Rs. {obj.current_balance:,.2f}"
    outstanding_balance.short_description = 'Outstanding'
    outstanding_balance.admin_order_field = 'current_balance'
    
    def total_paid(self, obj):
        """Calculate total payments received from customer"""
        from decimal import Decimal
        total = obj.payments_received.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        return f"Rs. {total:,.2f}"
    total_paid.short_description = 'Total Paid'
    
    def available_credit(self, obj):
        """Display available credit"""
        return f"Rs. {obj.available_credit:,.2f}"
    available_credit.short_description = 'Available Credit'
    
    def activate_customers(self, request, queryset):
        """Bulk action to activate selected customers"""
        updated = queryset.update(status='active')
        self.message_user(request, f'{updated} customer(s) successfully activated.')
    activate_customers.short_description = 'Activate selected customers'
    
    def deactivate_customers(self, request, queryset):
        """Bulk action to deactivate selected customers"""
        updated = queryset.update(status='inactive')
        self.message_user(request, f'{updated} customer(s) successfully deactivated.')
    deactivate_customers.short_description = 'Deactivate selected customers'
    
    def export_to_csv(self, request, queryset):
        """Export selected customers to CSV"""
        import csv
        from django.http import HttpResponse
        from datetime import datetime
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="customers_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Name', 'Phone', 'Email', 'PAN', 'Type', 'Status', 
            'Credit Limit', 'Current Balance', 'Payment Terms', 'Address'
        ])
        
        for customer in queryset:
            writer.writerow([
                customer.name,
                customer.phone,
                customer.email or '',
                customer.pan or '',
                customer.type,
                customer.status,
                customer.credit_limit,
                customer.current_balance,
                customer.payment_terms,
                customer.address or ''
            ])
        
        self.message_user(request, f'{queryset.count()} customer(s) exported to CSV.')
        return response
    export_to_csv.short_description = 'Export selected customers to CSV'


class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 1
    fields = ['product', 'description', 'quantity', 'unit_price', 'discount_percent', 'tax_percent', 'amount']
    readonly_fields = ['amount']


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'date', 'customer', 'payment_type', 'status', 'total', 'created_at']
    list_filter = ['status', 'payment_type', 'date']
    search_fields = ['order_number', 'customer__name', 'reference']
    ordering = ['-date', '-created_at']
    inlines = [SalesOrderLineInline]


class QuotationLineInline(admin.TabularInline):
    model = QuotationLine
    extra = 1
    fields = ['product', 'description', 'quantity', 'unit_price', 'discount_percent', 'tax_percent', 'amount']
    readonly_fields = ['amount']


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ['quotation_number', 'date', 'customer', 'valid_until', 'total', 'status', 'created_at']
    list_filter = ['status', 'date']
    search_fields = ['quotation_number', 'customer__name']
    ordering = ['-date', '-created_at']
    inlines = [QuotationLineInline]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'date', 'due_date', 'customer', 'amount', 'paid_amount', 'status', 'created_at']
    list_filter = ['status', 'date']
    search_fields = ['invoice_number', 'customer__name']
    ordering = ['-date', '-created_at']


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ['credit_note_number', 'date', 'customer', 'invoice', 'amount', 'status', 'created_at']
    list_filter = ['status', 'date']
    search_fields = ['credit_note_number', 'customer__name']
    ordering = ['-date', '-created_at']



@admin.register(CustomerLedger)
class CustomerLedgerAdmin(admin.ModelAdmin):
    list_display = ['customer', 'date', 'transaction_type', 'reference_number', 'debit_amount', 'credit_amount', 'running_balance', 'tenant']
    list_filter = ['transaction_type', 'date', 'tenant']
    search_fields = ['customer__name', 'reference_number', 'description']
    ordering = ['-date', '-created_at']
    readonly_fields = ['running_balance', 'created_at']
    
    def has_add_permission(self, request):
        # Ledger entries are created automatically
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Ledger entries are immutable
        return False


@admin.register(PaymentReceived)
class PaymentReceivedAdmin(admin.ModelAdmin):
    list_display = ['payment_number', 'customer', 'date', 'amount', 'payment_method', 'received_by', 'tenant']
    list_filter = ['payment_method', 'date', 'tenant']
    search_fields = ['payment_number', 'customer__name', 'reference_number']
    ordering = ['-date', '-created_at']
    readonly_fields = ['payment_number', 'received_by', 'created_at', 'updated_at']
