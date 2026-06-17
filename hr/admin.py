from django.contrib import admin
from .models import Department, Employee, Attendance, LeaveType, LeaveRequest, Payroll


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'head', 'employee_count', 'tenant', 'created_at']
    list_filter = ['tenant', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'head')
        }),
        ('Tenant', {
            'fields': ('tenant',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'designation', 'department', 'employment_type',
        'status', 'basic_salary', 'tenant', 'created_at'
    ]
    list_filter = ['status', 'employment_type', 'gender', 'department', 'tenant', 'created_at']
    search_fields = ['name', 'email', 'phone', 'designation']
    readonly_fields = ['created_at', 'updated_at', 'pf_employee', 'pf_employer', 'total_pf', 'gross_salary']
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('name', 'dob', 'gender', 'phone', 'email')
        }),
        ('Employment Information', {
            'fields': ('department', 'designation', 'employment_type', 'join_date', 'status')
        }),
        ('Salary Information', {
            'fields': ('basic_salary', 'pf_employee', 'pf_employer', 'total_pf', 'gross_salary')
        }),
        ('System Access', {
            'fields': ('user',)
        }),
        ('Tenant', {
            'fields': ('tenant',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )



@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['employee', 'date', 'status', 'check_in', 'check_out', 'hours_worked', 'tenant']
    list_filter = ['status', 'date', 'employee__department', 'tenant']
    search_fields = ['employee__name', 'remarks']
    readonly_fields = ['created_at', 'updated_at', 'hours_worked']
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('employee', 'date', 'status')
        }),
        ('Time Tracking', {
            'fields': ('check_in', 'check_out', 'hours_worked')
        }),
        ('Additional Information', {
            'fields': ('remarks',)
        }),
        ('Tenant', {
            'fields': ('tenant',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )



@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'days_allowed', 'is_paid', 'tenant', 'created_at']
    list_filter = ['is_paid', 'tenant', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'days_allowed', 'is_paid', 'description')
        }),
        ('Tenant', {
            'fields': ('tenant',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'start_date', 'end_date', 'days_requested', 'status', 'tenant']
    list_filter = ['status', 'leave_type', 'start_date', 'tenant']
    search_fields = ['employee__name', 'reason']
    readonly_fields = ['created_at', 'updated_at', 'days_requested', 'approved_at']
    date_hierarchy = 'start_date'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('employee', 'leave_type', 'start_date', 'end_date', 'reason')
        }),
        ('Status', {
            'fields': ('status', 'rejection_reason')
        }),
        ('Approval Information', {
            'fields': ('approved_by', 'approved_at')
        }),
        ('Tenant', {
            'fields': ('tenant',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = ['employee', 'month', 'year', 'basic_salary', 'gross_salary', 'net_salary', 'status', 'tenant', 'processed_date']
    list_filter = ['status', 'year', 'month', 'tenant']
    search_fields = ['employee__name', 'month']
    readonly_fields = ['created_at', 'updated_at', 'processed_date']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('employee', 'month', 'year')
        }),
        ('Salary Details', {
            'fields': ('basic_salary', 'allowances', 'gross_salary', 'deductions', 'net_salary')
        }),
        ('Status', {
            'fields': ('status', 'processed_date')
        }),
        ('Tenant', {
            'fields': ('tenant',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
