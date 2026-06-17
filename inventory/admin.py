from django.contrib import admin
from .models import Category, UnitOfMeasure, Warehouse, Product, Stock, StockMovement
from .bulk_pricing_models import BulkPricing
from .pricing_models import CustomerSpecificPrice, PriceHistory


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'tenant', 'created_at']
    list_filter = ['tenant', 'parent']
    search_fields = ['name', 'description']


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ['name', 'abbreviation', 'type', 'tenant']
    list_filter = ['type', 'tenant']
    search_fields = ['name', 'abbreviation']


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'manager', 'is_active', 'tenant']
    list_filter = ['is_active', 'tenant']
    search_fields = ['name', 'location']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'category', 'cost_price', 'selling_price', 'status', 'tenant']
    list_filter = ['status', 'category', 'tenant']
    search_fields = ['name', 'sku', 'description']


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ['product', 'warehouse', 'quantity', 'tenant']
    list_filter = ['warehouse', 'tenant']
    search_fields = ['product__name', 'product__sku']


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['product', 'warehouse', 'movement_type', 'quantity', 'performed_by', 'created_at']
    list_filter = ['movement_type', 'warehouse', 'created_at']
    search_fields = ['product__name', 'reason']
    readonly_fields = ['created_at']


@admin.register(BulkPricing)
class BulkPricingAdmin(admin.ModelAdmin):
    list_display = ['product', 'min_quantity', 'max_quantity', 'unit_price', 'discount_percent', 'is_active', 'tenant']
    list_filter = ['is_active', 'tenant', 'product__category']
    search_fields = ['product__name', 'product__sku']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Product', {
            'fields': ('product',)
        }),
        ('Quantity Range', {
            'fields': ('min_quantity', 'max_quantity')
        }),
        ('Pricing', {
            'fields': ('unit_price', 'discount_percent')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CustomerSpecificPrice)
class CustomerSpecificPriceAdmin(admin.ModelAdmin):
    list_display = ['customer', 'product', 'unit_price', 'min_quantity', 'valid_from', 'valid_until', 'is_active', 'tenant']
    list_filter = ['is_active', 'tenant', 'valid_from', 'valid_until']
    search_fields = ['customer__name', 'product__name', 'product__sku', 'notes']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    date_hierarchy = 'valid_from'
    
    fieldsets = (
        ('Customer & Product', {
            'fields': ('customer', 'product')
        }),
        ('Pricing', {
            'fields': ('unit_price', 'min_quantity')
        }),
        ('Validity Period', {
            'fields': ('valid_from', 'valid_until')
        }),
        ('Status & Notes', {
            'fields': ('is_active', 'notes')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """Set created_by on creation"""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = [
        'product', 
        'change_type', 
        'old_selling_price', 
        'new_selling_price', 
        'selling_price_change_percent',
        'effective_date', 
        'changed_by'
    ]
    list_filter = ['change_type', 'effective_date', 'tenant']
    search_fields = ['product__name', 'product__sku', 'change_reason']
    readonly_fields = [
        'product', 'old_cost_price', 'new_cost_price', 'cost_price_change_percent',
        'old_selling_price', 'new_selling_price', 'selling_price_change_percent',
        'change_type', 'change_reason', 'changed_by', 'effective_date', 'created_at'
    ]
    date_hierarchy = 'effective_date'
    
    fieldsets = (
        ('Product', {
            'fields': ('product',)
        }),
        ('Cost Price Change', {
            'fields': ('old_cost_price', 'new_cost_price', 'cost_price_change_percent')
        }),
        ('Selling Price Change', {
            'fields': ('old_selling_price', 'new_selling_price', 'selling_price_change_percent')
        }),
        ('Change Details', {
            'fields': ('change_type', 'change_reason', 'effective_date')
        }),
        ('Audit', {
            'fields': ('changed_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        """Price history is auto-generated, no manual creation"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Price history is immutable"""
        return False

