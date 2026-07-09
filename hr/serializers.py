from datetime import date
from rest_framework import serializers
from tenants.utils import get_request_tenant
from .models import Department, Employee, Attendance, LeaveType, LeaveRequest, Payroll

MIN_EMPLOYEE_AGE = 18


def tenant_filtered_queryset(model, request):
    """Scope FK querysets to the request tenant (bypasses thread-local TenantManager)."""
    if not request or not getattr(request, 'user', None) or not request.user.is_authenticated:
        return model._base_manager.none()
    tenant = get_request_tenant(request.user)
    if not tenant:
        return model._base_manager.none()
    return model._base_manager.filter(tenant=tenant)


class TenantScopedFkSerializerMixin:
    """Bind tenant-scoped FK fields for create/update serializers."""

    tenant_scoped_fk_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        for field_name, model in self.tenant_scoped_fk_fields:
            if field_name in self.fields:
                self.fields[field_name].queryset = tenant_filtered_queryset(model, request)


def validate_minimum_employee_age(dob: date, min_age: int = MIN_EMPLOYEE_AGE) -> None:
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < min_age:
        raise serializers.ValidationError(
            f'Employee must be at least {min_age} years old.'
        )


class DepartmentSerializer(TenantScopedFkSerializerMixin, serializers.ModelSerializer):
    employee_count = serializers.ReadOnlyField()
    head_name = serializers.CharField(source='head.name', read_only=True)
    tenant_scoped_fk_fields = (('head', Employee),)

    class Meta:
        model = Department
        fields = [
            'id', 'name', 'description', 'head', 'head_name',
            'employee_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class EmployeeSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    pf_employee = serializers.ReadOnlyField()
    pf_employer = serializers.ReadOnlyField()
    total_pf = serializers.ReadOnlyField()
    gross_salary = serializers.ReadOnlyField()

    def validate_dob(self, value):
        validate_minimum_employee_age(value)
        return value
    
    class Meta:
        model = Employee
        fields = [
            'id', 'name', 'dob', 'gender', 'phone', 'email',
            'department', 'department_name', 'designation', 'employment_type',
            'join_date', 'basic_salary', 'pf_employee', 'pf_employer',
            'total_pf', 'gross_salary', 'status', 'user',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class EmployeeCreateSerializer(TenantScopedFkSerializerMixin, serializers.ModelSerializer):
    tenant_scoped_fk_fields = (('department', Department),)

    def validate_dob(self, value):
        validate_minimum_employee_age(value)
        return value

    class Meta:
        model = Employee
        fields = [
            'id', 'name', 'dob', 'gender', 'phone', 'email',
            'department', 'designation', 'employment_type', 'join_date',
            'basic_salary', 'status', 'user'
        ]
        read_only_fields = ['id']


class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    department_name = serializers.CharField(source='employee.department.name', read_only=True)
    hours_worked = serializers.ReadOnlyField()
    
    class Meta:
        model = Attendance
        fields = [
            'id', 'employee', 'employee_name', 'department_name',
            'date', 'status', 'check_in', 'check_out', 'remarks',
            'hours_worked', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BulkAttendanceSerializer(serializers.Serializer):
    """Serializer for bulk attendance marking"""
    date = serializers.DateField()
    records = serializers.ListField(
        child=serializers.DictField()
    )
    
    def validate_records(self, value):
        """Validate attendance records"""
        for record in value:
            if 'employee' not in record:
                raise serializers.ValidationError("Each record must have an employee ID")
            if 'status' not in record:
                raise serializers.ValidationError("Each record must have a status")
        return value


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = [
            'id', 'name', 'days_allowed', 'description', 'is_paid',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    leave_type_name = serializers.CharField(source='leave_type.name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.username', read_only=True)
    days_requested = serializers.ReadOnlyField()
    
    class Meta:
        model = LeaveRequest
        fields = [
            'id', 'employee', 'employee_name', 'leave_type', 'leave_type_name',
            'start_date', 'end_date', 'reason', 'status', 'days_requested',
            'approved_by', 'approved_by_name', 'approved_at', 'rejection_reason',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'approved_by', 'approved_at', 'created_at', 'updated_at']
        extra_kwargs = {
            'employee': {'required': False},
        }
    
    def validate(self, data):
        """Custom validation"""
        # Validate date range
        if 'start_date' in data and 'end_date' in data:
            if data['end_date'] < data['start_date']:
                raise serializers.ValidationError({
                    'end_date': 'End date must be after start date'
                })
        
        # Employee will be set in the view's perform_create method if not provided
        return data


class PayrollSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    department_name = serializers.CharField(source='employee.department.name', read_only=True)
    
    class Meta:
        model = Payroll
        fields = [
            'id', 'employee', 'employee_name', 'department_name',
            'month', 'year', 'basic_salary', 'allowances', 'gross_salary',
            'deductions', 'net_salary', 'status', 'processed_date',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'processed_date', 'created_at', 'updated_at']
