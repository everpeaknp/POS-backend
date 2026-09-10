from django.contrib import admin

from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.admin import TabularInline as UnfoldTabularInline
from .models import Site, Worker, Attendance, DailyLog, MaterialConsumption, Equipment, EquipmentUsageLog


@admin.register(Site)
class SiteAdmin(UnfoldModelAdmin):
    list_display = ['name', 'location', 'manager', 'status', 'allocated_budget', 'start_date', 'tenant']
    list_filter = ['status', 'tenant']
    search_fields = ['name', 'location', 'client_name']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Worker)
class WorkerAdmin(UnfoldModelAdmin):
    list_display = ['name', 'category', 'daily_wage', 'assigned_site', 'status', 'tenant']
    list_filter = ['category', 'status', 'tenant']
    search_fields = ['name', 'phone', 'id_number']
    ordering = ['name']


@admin.register(Attendance)
class AttendanceAdmin(UnfoldModelAdmin):
    list_display = ['worker', 'site', 'date', 'status', 'wage_amount', 'marked_by', 'tenant']
    list_filter = ['status', 'date', 'tenant']
    search_fields = ['worker__name', 'site__name']
    ordering = ['-date']
    readonly_fields = ['wage_amount', 'created_at', 'updated_at']


class MaterialConsumptionInline(UnfoldTabularInline):
    model = MaterialConsumption
    extra = 1
    readonly_fields = ['total_cost']


@admin.register(DailyLog)
class DailyLogAdmin(UnfoldModelAdmin):
    list_display = ['site', 'date', 'submitted_by', 'reviewed_by', 'tenant']
    list_filter = ['date', 'tenant']
    search_fields = ['site__name', 'work_description']
    ordering = ['-date']
    readonly_fields = ['submitted_by', 'reviewed_by', 'reviewed_at', 'created_at', 'updated_at']
    inlines = [MaterialConsumptionInline]


@admin.register(MaterialConsumption)
class MaterialConsumptionAdmin(UnfoldModelAdmin):
    list_display = ['product', 'site', 'quantity', 'unit_cost', 'total_cost', 'daily_log', 'tenant']
    list_filter = ['site', 'tenant']
    search_fields = ['product__name', 'site__name']
    ordering = ['-created_at']
    readonly_fields = ['total_cost', 'created_at', 'updated_at']


@admin.register(Equipment)
class EquipmentAdmin(UnfoldModelAdmin):
    list_display = ['name', 'equipment_type', 'ownership_type', 'status', 'assigned_site', 'tenant']
    list_filter = ['ownership_type', 'status', 'tenant']
    search_fields = ['name', 'equipment_type', 'registration_number']
    ordering = ['name']


@admin.register(EquipmentUsageLog)
class EquipmentUsageLogAdmin(UnfoldModelAdmin):
    list_display = ['equipment', 'site', 'date', 'hours_used', 'cost', 'tenant']
    list_filter = ['date', 'tenant']
    search_fields = ['equipment__name', 'site__name']
    ordering = ['-date']
    readonly_fields = ['cost', 'created_at', 'updated_at']
