from django.contrib import admin
from .models import CustomReport


@admin.register(CustomReport)
class CustomReportAdmin(admin.ModelAdmin):
    """Admin interface for Custom Reports"""
    list_display = ['name', 'module', 'report_type', 'created_by', 'schedule', 'last_run', 'created_at']
    list_filter = ['module', 'report_type', 'schedule', 'created_at']
    search_fields = ['name', 'description', 'created_by__username']
    readonly_fields = ['created_at', 'updated_at', 'last_run']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'report_type', 'module')
        }),
        ('Configuration', {
            'fields': ('fields', 'filters', 'grouping', 'sorting', 'chart_config')
        }),
        ('Scheduling', {
            'fields': ('schedule', 'last_run')
        }),
        ('Metadata', {
            'fields': ('created_by', 'is_shared', 'created_at', 'updated_at')
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """Set created_by to current user if creating new report"""
        if not change:
            obj.created_by = request.user
            obj.tenant = request.user.tenant
        super().save_model(request, obj, form, change)
