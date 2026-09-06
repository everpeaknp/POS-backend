# from django.contrib import admin
# from .models import Vehicle, Delivery, DeliveryItem

# Admin registration removed - hardware models are managed through the API only

# @admin.register(Vehicle)
# class VehicleAdmin(admin.ModelAdmin):
#     list_display = ['vehicle_number', 'vehicle_type', 'status', 'capacity_kg', 'is_owned', 'tenant']
#     list_filter = ['status', 'vehicle_type', 'is_owned', 'tenant']
#     search_fields = ['vehicle_number', 'notes']
#     ordering = ['vehicle_number']
#     
#     fieldsets = (
#         ('Basic Information', {
#             'fields': ('tenant', 'vehicle_number', 'vehicle_type', 'capacity_kg', 'is_owned')
#         }),
#         ('Status', {
#             'fields': ('status',)
#         }),
#         ('Maintenance', {
#             'fields': ('last_service_date', 'next_service_due')
#         }),
#         ('Additional Info', {
#             'fields': ('notes',),
#             'classes': ('collapse',)
#         }),
#     )


# class DeliveryItemInline(admin.TabularInline):
#     model = DeliveryItem
#     extra = 0
#     fields = ['product', 'ordered_quantity', 'delivered_quantity', 'damaged_quantity', 'unit_price', 'notes']
#     readonly_fields = []


# @admin.register(Delivery)
# class DeliveryAdmin(admin.ModelAdmin):
#     list_display = [
#         'delivery_number',
#         'challan_number',
#         'customer',
#         'scheduled_date',
#         'status',
#         'vehicle',
#         'driver_name',
#         'tenant'
#     ]
#     list_filter = ['status', 'scheduled_date', 'tenant']
#     search_fields = ['delivery_number', 'challan_number', 'customer__name', 'driver_name']
#     ordering = ['-scheduled_date', '-created_at']
#     inlines = [DeliveryItemInline]
#     
#     fieldsets = (
#         ('Basic Information', {
#             'fields': ('tenant', 'invoice', 'delivery_number', 'challan_number')
#         }),
#         ('Customer & Location', {
#             'fields': (
#                 'customer',
#                 'delivery_address',
#                 'customer_contact_name',
#                 'customer_contact_phone'
#             )
#         }),
#         ('Schedule', {
#             'fields': ('scheduled_date', 'scheduled_time', 'status')
#         }),
#         ('Vehicle & Driver', {
#             'fields': ('vehicle', 'driver_name', 'driver_phone')
#         }),
#         ('Charges', {
#             'fields': ('transport_charge', 'loading_charge')
#         }),
#         ('Delivery Tracking', {
#             'fields': (
#                 'loading_started_at',
#                 'dispatch_time',
#                 'delivery_completed_at'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Notes & Documentation', {
#             'fields': (
#                 'delivery_notes',
#                 'driver_notes',
#                 'customer_signature',
#                 'delivery_photos'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Failure Info', {
#             'fields': ('failure_reason',),
#             'classes': ('collapse',)
#         }),
#         ('Metadata', {
#             'fields': ('created_by',),
#             'classes': ('collapse',)
#         }),
#     )


# @admin.register(DeliveryItem)
# class DeliveryItemAdmin(admin.ModelAdmin):
#     list_display = [
#         'delivery',
#         'product',
#         'ordered_quantity',
#         'delivered_quantity',
#         'damaged_quantity',
#         'unit_price',
#         'tenant'
#     ]
#     list_filter = ['tenant', 'delivery__status']
#     search_fields = ['delivery__delivery_number', 'product__name']
#     ordering = ['-delivery__scheduled_date']
