from django.contrib import admin
from .models import (
    Supplier, PurchaseRequest, PurchaseRequestLine,
    PurchaseOrder, PurchaseOrderLine, PurchaseInvoice, DebitNote
)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email', 'type', 'status', 'credit_limit', 'created_at']
    list_filter = ['status', 'type', 'payment_terms']
    search_fields = ['name', 'phone', 'email', 'pan']
    ordering = ['-created_at']


class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1
    fields = ['product', 'description', 'quantity', 'estimated_unit_price', 'estimated_amount']
    readonly_fields = ['estimated_amount']


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = ['request_number', 'date', 'requested_by', 'department', 'status', 'priority', 'estimated_amount', 'created_at']
    list_filter = ['status', 'priority', 'department']
    search_fields = ['request_number', 'requested_by__username', 'department']
    ordering = ['-date', '-created_at']
    inlines = [PurchaseRequestLineInline]


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = ['product', 'description', 'quantity', 'unit_price', 'tax_percent', 'amount', 'received_quantity']
    readonly_fields = ['amount']


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['po_number', 'date', 'supplier', 'status', 'total', 'expected_delivery_date', 'created_at']
    list_filter = ['status', 'date']
    search_fields = ['po_number', 'supplier__name', 'reference']
    ordering = ['-date', '-created_at']
    inlines = [PurchaseOrderLineInline]


@admin.register(PurchaseInvoice)
class PurchaseInvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'date', 'due_date', 'supplier', 'amount', 'paid_amount', 'status', 'created_at']
    list_filter = ['status', 'date']
    search_fields = ['invoice_number', 'supplier__name']
    ordering = ['-date', '-created_at']


@admin.register(DebitNote)
class DebitNoteAdmin(admin.ModelAdmin):
    list_display = ['debit_note_number', 'date', 'supplier', 'invoice', 'amount', 'reason', 'status', 'created_at']
    list_filter = ['status', 'reason', 'date']
    search_fields = ['debit_note_number', 'supplier__name']
    ordering = ['-date', '-created_at']
