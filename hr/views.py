from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from users.dynamic_permissions import DynamicModulePermission
from drf_spectacular.utils import extend_schema, extend_schema_view
from django.db.models import Count, Sum, Avg, Q
from decimal import Decimal

from .models import Department, Employee, Attendance, LeaveType, LeaveRequest, Payroll
from .serializers import (
    DepartmentSerializer, EmployeeSerializer, EmployeeCreateSerializer,
    AttendanceSerializer, BulkAttendanceSerializer,
    LeaveTypeSerializer, LeaveRequestSerializer, PayrollSerializer
)


@extend_schema_view(
    list=extend_schema(description="List all departments for the current tenant", tags=["HR - Departments"]),
    retrieve=extend_schema(description="Get department details", tags=["HR - Departments"]),
    create=extend_schema(description="Create a new department", tags=["HR - Departments"]),
    update=extend_schema(description="Update department details", tags=["HR - Departments"]),
    partial_update=extend_schema(description="Partially update department", tags=["HR - Departments"]),
    destroy=extend_schema(description="Delete a department", tags=["HR - Departments"]),
)
class DepartmentViewSet(viewsets.ModelViewSet):
    """ViewSet for Department CRUD operations"""
    serializer_class = DepartmentSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'hr'
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        """Filter by current tenant"""
        return Department.objects.filter(tenant=self.request.user.tenant)
    
    def perform_create(self, serializer):
        """Set tenant when creating department"""
        serializer.save(tenant=self.request.user.tenant)


@extend_schema_view(
    list=extend_schema(description="List all employees for the current tenant", tags=["HR - Employees"]),
    retrieve=extend_schema(description="Get employee details", tags=["HR - Employees"]),
    create=extend_schema(
        description="Create a new employee",
        tags=["HR - Employees"],
        request=EmployeeCreateSerializer
    ),
    update=extend_schema(
        description="Update employee details",
        tags=["HR - Employees"],
        request=EmployeeCreateSerializer
    ),
    partial_update=extend_schema(description="Partially update employee", tags=["HR - Employees"]),
    destroy=extend_schema(description="Delete an employee", tags=["HR - Employees"]),
)
class EmployeeViewSet(viewsets.ModelViewSet):
    """ViewSet for Employee CRUD operations"""
    permission_classes = [DynamicModulePermission]
    permission_module = 'hr'
    filterset_fields = ['status', 'department', 'employment_type', 'gender']
    search_fields = ['name', 'phone', 'email', 'designation']
    ordering_fields = ['name', 'join_date', 'created_at', 'basic_salary']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        return Employee.objects.filter(tenant=self.request.user.tenant).select_related('department', 'user')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return EmployeeCreateSerializer
        return EmployeeSerializer
    
    def perform_create(self, serializer):
        """Set tenant when creating employee"""
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['HR - Dashboard'],
        summary='Get HR dashboard data',
        description='Returns comprehensive HR dashboard data including employee stats and department breakdown'
    )
    @action(detail=False, methods=['get'], url_path='dashboard')
    def hr_dashboard(self, request):
        """HR Dashboard API endpoint"""
        tenant = request.user.tenant
        
        # Get all employees for this tenant
        employees = Employee.objects.filter(tenant=tenant)
        active_employees = employees.filter(status='active')
        
        # Calculate stats
        total_employees = employees.count()
        active_count = active_employees.count()
        inactive_count = employees.filter(status='inactive').count()
        terminated_count = employees.filter(status='terminated').count()
        
        # Calculate salary stats
        total_salary = active_employees.aggregate(
            total=Sum('basic_salary')
        )['total'] or Decimal('0')
        
        avg_salary = active_employees.aggregate(
            avg=Avg('basic_salary')
        )['avg'] or Decimal('0')
        
        # Department breakdown
        departments = Department.objects.filter(tenant=tenant).annotate(
            emp_count=Count('employees', filter=Q(employees__status='active'))
        ).values('id', 'name', 'emp_count')
        
        # Employment type breakdown
        employment_types = active_employees.values('employment_type').annotate(
            count=Count('id')
        )
        
        # Recent employees
        recent_employees = active_employees.order_by('-join_date')[:5]
        recent_serializer = EmployeeSerializer(recent_employees, many=True)
        
        return Response({
            'stats': {
                'total_employees': total_employees,
                'active_employees': active_count,
                'inactive_employees': inactive_count,
                'terminated_employees': terminated_count,
                'total_salary': float(total_salary),
                'average_salary': float(avg_salary),
            },
            'departments': list(departments),
            'employment_types': list(employment_types),
            'recent_employees': recent_serializer.data,
        })
    
    @extend_schema(
        tags=['HR - Employees'],
        summary='Get managers/approvers',
        description='Returns list of employees who can approve purchase requests (Manager, Director, CEO, etc.)'
    )
    @action(detail=False, methods=['get'], url_path='managers')
    def managers(self, request):
        """Get list of managers/approvers for purchase requests"""
        tenant = request.user.tenant
        
        # Designations that can approve
        manager_designations = [
            'Manager', 'Senior Manager', 'Director', 
            'Senior Director', 'CEO', 'CFO', 'CTO', 
            'COO', 'VP', 'Vice President', 'President'
        ]
        
        # Get active employees with manager-level designations
        managers = Employee.objects.filter(
            tenant=tenant,
            status='active',
            designation__in=manager_designations
        ).select_related('department').order_by('name')
        
        # Serialize with basic info
        data = [{
            'id': emp.id,
            'name': emp.name,
            'designation': emp.designation,
            'department': emp.department.name if emp.department else None,
            'email': emp.email,
        } for emp in managers]
        
        return Response(data)



@extend_schema_view(
    list=extend_schema(description="List attendance records", tags=["HR - Attendance"]),
    retrieve=extend_schema(description="Get attendance record details", tags=["HR - Attendance"]),
    create=extend_schema(description="Create attendance record", tags=["HR - Attendance"]),
    update=extend_schema(description="Update attendance record", tags=["HR - Attendance"]),
    partial_update=extend_schema(description="Partially update attendance", tags=["HR - Attendance"]),
    destroy=extend_schema(description="Delete attendance record", tags=["HR - Attendance"]),
)
class AttendanceViewSet(viewsets.ModelViewSet):
    """ViewSet for Attendance CRUD operations"""
    serializer_class = AttendanceSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'hr'
    filterset_fields = ['employee', 'date', 'status']
    search_fields = ['employee__name', 'remarks']
    ordering_fields = ['date', 'created_at']
    ordering = ['-date', 'employee__name']
    
    def get_queryset(self):
        """Filter by current tenant"""
        return Attendance.objects.filter(tenant=self.request.user.tenant).select_related('employee', 'employee__department')
    
    def perform_create(self, serializer):
        """Set tenant when creating attendance"""
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['HR - Attendance'],
        summary='Bulk mark attendance',
        description='Mark attendance for multiple employees at once',
        request=BulkAttendanceSerializer,
        responses={201: AttendanceSerializer(many=True)}
    )
    @action(detail=False, methods=['post'], url_path='bulk-mark')
    def bulk_mark(self, request):
        """Bulk mark attendance for multiple employees"""
        serializer = BulkAttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        date = serializer.validated_data['date']
        records = serializer.validated_data['records']
        tenant = request.user.tenant
        
        created_records = []
        updated_records = []
        
        for record in records:
            employee_id = record.get('employee')
            status_value = record.get('status', 'present')
            check_in = record.get('check_in')
            check_out = record.get('check_out')
            remarks = record.get('remarks', '')
            
            # Check if employee exists and belongs to tenant
            try:
                employee = Employee.objects.get(id=employee_id, tenant=tenant)
            except Employee.DoesNotExist:
                continue
            
            # Update or create attendance record
            attendance, created = Attendance.objects.update_or_create(
                tenant=tenant,
                employee=employee,
                date=date,
                defaults={
                    'status': status_value,
                    'check_in': check_in,
                    'check_out': check_out,
                    'remarks': remarks
                }
            )
            
            if created:
                created_records.append(attendance)
            else:
                updated_records.append(attendance)
        
        all_records = created_records + updated_records
        response_serializer = AttendanceSerializer(all_records, many=True)
        
        return Response({
            'message': f'Successfully processed {len(all_records)} attendance records',
            'created': len(created_records),
            'updated': len(updated_records),
            'records': response_serializer.data
        }, status=status.HTTP_201_CREATED)
    
    @extend_schema(
        tags=['HR - Attendance'],
        summary='Get attendance statistics',
        description='Get attendance statistics for a specific month'
    )
    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Get attendance statistics for a month"""
        from datetime import datetime
        from calendar import monthrange
        
        tenant = request.user.tenant
        
        # Get month parameter (format: YYYY-MM)
        month_str = request.query_params.get('month')
        if month_str:
            try:
                year, month = map(int, month_str.split('-'))
            except (ValueError, AttributeError):
                return Response({'error': 'Invalid month format. Use YYYY-MM'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            now = datetime.now()
            year, month = now.year, now.month
        
        # Get working days in month
        _, working_days = monthrange(year, month)
        
        # Get attendance records for the month
        start_date = datetime(year, month, 1).date()
        if month == 12:
            end_date = datetime(year + 1, 1, 1).date()
        else:
            end_date = datetime(year, month + 1, 1).date()
        
        attendance_records = Attendance.objects.filter(
            tenant=tenant,
            date__gte=start_date,
            date__lt=end_date
        )
        
        # Calculate stats
        total_records = attendance_records.count()
        present_count = attendance_records.filter(status='present').count()
        absent_count = attendance_records.filter(status='absent').count()
        late_count = attendance_records.filter(status='late').count()
        
        # Calculate average attendance percentage
        active_employees = Employee.objects.filter(tenant=tenant, status='active').count()
        expected_records = active_employees * working_days
        avg_attendance = (present_count / expected_records * 100) if expected_records > 0 else 0
        
        return Response({
            'working_days': working_days,
            'avg_attendance': round(avg_attendance, 1),
            'late_arrivals': late_count,
            'absences': absent_count,
            'total_records': total_records,
            'present_count': present_count
        })



@extend_schema_view(
    list=extend_schema(description="List all leave types", tags=["HR - Leave"]),
    retrieve=extend_schema(description="Get leave type details", tags=["HR - Leave"]),
    create=extend_schema(description="Create a new leave type", tags=["HR - Leave"]),
    update=extend_schema(description="Update leave type", tags=["HR - Leave"]),
    partial_update=extend_schema(description="Partially update leave type", tags=["HR - Leave"]),
    destroy=extend_schema(description="Delete a leave type", tags=["HR - Leave"]),
)
class LeaveTypeViewSet(viewsets.ModelViewSet):
    """ViewSet for LeaveType CRUD operations"""
    serializer_class = LeaveTypeSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'hr'
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'days_allowed', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        """Filter by current tenant"""
        return LeaveType.objects.filter(tenant=self.request.user.tenant)
    
    def perform_create(self, serializer):
        """Set tenant when creating leave type"""
        serializer.save(tenant=self.request.user.tenant)


@extend_schema_view(
    list=extend_schema(description="List all leave requests", tags=["HR - Leave"]),
    retrieve=extend_schema(description="Get leave request details", tags=["HR - Leave"]),
    create=extend_schema(description="Create a new leave request", tags=["HR - Leave"]),
    update=extend_schema(description="Update leave request", tags=["HR - Leave"]),
    partial_update=extend_schema(description="Partially update leave request", tags=["HR - Leave"]),
    destroy=extend_schema(description="Delete a leave request", tags=["HR - Leave"]),
)
class LeaveRequestViewSet(viewsets.ModelViewSet):
    """ViewSet for LeaveRequest CRUD operations"""
    serializer_class = LeaveRequestSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'hr'
    filterset_fields = ['employee', 'leave_type', 'status', 'start_date', 'end_date']
    search_fields = ['employee__name', 'reason']
    ordering_fields = ['start_date', 'created_at', 'status']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        return LeaveRequest.objects.filter(tenant=self.request.user.tenant).select_related('employee', 'leave_type', 'approved_by')
    
    def perform_create(self, serializer):
        """Set tenant and employee when creating leave request"""
        # Try to get employee from current user
        employee = None
        if hasattr(self.request.user, 'employee_profile'):
            employee = self.request.user.employee_profile
        
        # If employee is provided in data, use that (for admin/manager creating on behalf)
        if 'employee' in self.request.data and self.request.data.get('employee'):
            employee_id = self.request.data.get('employee')
            try:
                employee = Employee.objects.get(id=employee_id, tenant=self.request.user.tenant)
            except Employee.DoesNotExist:
                pass
        
        # If still no employee, try to get the first active employee for this tenant (for testing)
        if not employee:
            employee = Employee.objects.filter(tenant=self.request.user.tenant, status='active').first()
        
        if employee:
            try:
                serializer.save(tenant=self.request.user.tenant, employee=employee)
            except Exception as e:
                from rest_framework.exceptions import ValidationError
                import traceback
                print(f"Error saving leave request: {e}")
                print(traceback.format_exc())
                raise ValidationError({
                    'error': f'Failed to create leave request: {str(e)}'
                })
        else:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({
                'employee': 'No employee profile found. Please create an employee profile first or specify an employee ID.'
            })
    
    @extend_schema(
        tags=['HR - Leave'],
        summary='Approve leave request',
        description='Approve a leave request'
    )
    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        """Approve a leave request"""
        from django.utils import timezone
        
        leave_request = self.get_object()
        
        if leave_request.status != 'pending':
            return Response(
                {'error': 'Only pending requests can be approved'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        leave_request.status = 'approved'
        leave_request.approved_by = request.user
        leave_request.approved_at = timezone.now()
        leave_request.save()
        
        serializer = self.get_serializer(leave_request)
        return Response(serializer.data)
    
    @extend_schema(
        tags=['HR - Leave'],
        summary='Reject leave request',
        description='Reject a leave request'
    )
    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        """Reject a leave request"""
        leave_request = self.get_object()
        
        if leave_request.status != 'pending':
            return Response(
                {'error': 'Only pending requests can be rejected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        rejection_reason = request.data.get('rejection_reason', '')
        
        leave_request.status = 'rejected'
        leave_request.rejection_reason = rejection_reason
        leave_request.save()
        
        serializer = self.get_serializer(leave_request)
        return Response(serializer.data)



@extend_schema_view(
    list=extend_schema(description="List all payroll records", tags=["HR - Payroll"]),
    retrieve=extend_schema(description="Get payroll record details", tags=["HR - Payroll"]),
    create=extend_schema(description="Create payroll record", tags=["HR - Payroll"]),
    update=extend_schema(description="Update payroll record", tags=["HR - Payroll"]),
    partial_update=extend_schema(description="Partially update payroll", tags=["HR - Payroll"]),
    destroy=extend_schema(description="Delete payroll record", tags=["HR - Payroll"]),
)
class PayrollViewSet(viewsets.ModelViewSet):
    """ViewSet for Payroll CRUD operations"""
    serializer_class = PayrollSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'hr'
    filterset_fields = ['employee', 'month', 'year', 'status']
    search_fields = ['employee__name', 'month']
    ordering_fields = ['year', 'created_at']
    ordering = ['-year', '-created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        return Payroll.objects.filter(tenant=self.request.user.tenant).select_related('employee', 'employee__department')
    
    def perform_create(self, serializer):
        """Set tenant when creating payroll"""
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['HR - Payroll'],
        summary='Calculate payroll for a month',
        description='Calculate payroll for all active employees for a specific month'
    )
    @action(detail=False, methods=['post'], url_path='calculate')
    def calculate(self, request):
        """Calculate payroll for a month"""
        month = request.data.get('month')
        year = request.data.get('year', 2081)  # Default Nepali year
        
        if not month:
            return Response({'error': 'Month is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        tenant = request.user.tenant
        employees = Employee.objects.filter(tenant=tenant, status='active')
        
        payroll_data = []
        for employee in employees:
            basic_salary = employee.basic_salary
            allowances = basic_salary * Decimal('0.15')
            gross_salary = basic_salary + allowances
            deductions = basic_salary * Decimal('0.15')
            net_salary = gross_salary - deductions
            
            payroll_data.append({
                'employee': employee.id,
                'employee_name': employee.name,
                'department_name': employee.department.name,
                'month': month,
                'year': year,
                'basic_salary': float(basic_salary),
                'allowances': float(allowances),
                'gross_salary': float(gross_salary),
                'deductions': float(deductions),
                'net_salary': float(net_salary),
            })
        
        # Calculate totals
        total_gross = sum(p['gross_salary'] for p in payroll_data)
        total_deductions = sum(p['deductions'] for p in payroll_data)
        total_net = sum(p['net_salary'] for p in payroll_data)
        
        return Response({
            'month': month,
            'year': year,
            'total_employees': len(payroll_data),
            'total_gross': total_gross,
            'total_deductions': total_deductions,
            'total_net': total_net,
            'payroll_data': payroll_data
        })
    
    @extend_schema(
        tags=['HR - Payroll'],
        summary='Process payroll',
        description='Process and save payroll records for employees'
    )
    @action(detail=False, methods=['post'], url_path='process')
    def process(self, request):
        """Process and save payroll records"""
        from django.utils import timezone
        
        payroll_data = request.data.get('payroll_data', [])
        month = request.data.get('month')
        year = request.data.get('year', 2081)
        
        if not payroll_data:
            return Response({'error': 'Payroll data is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        tenant = request.user.tenant
        created_records = []
        
        for data in payroll_data:
            employee_id = data.get('employee')
            
            try:
                employee = Employee.objects.get(id=employee_id, tenant=tenant)
            except Employee.DoesNotExist:
                continue
            
            payroll, created = Payroll.objects.update_or_create(
                tenant=tenant,
                employee=employee,
                month=month,
                year=year,
                defaults={
                    'basic_salary': Decimal(str(data.get('basic_salary', 0))),
                    'allowances': Decimal(str(data.get('allowances', 0))),
                    'gross_salary': Decimal(str(data.get('gross_salary', 0))),
                    'deductions': Decimal(str(data.get('deductions', 0))),
                    'net_salary': Decimal(str(data.get('net_salary', 0))),
                    'status': 'processed',
                    'processed_date': timezone.now()
                }
            )
            if created:
                try:
                    from accounting.services import record_payroll_expense
                    from django.utils import timezone as tz
                    record_payroll_expense(
                        employee,
                        payroll.net_salary,
                        f'PAY-{payroll.id}',
                        tz.now().date(),
                        tenant=tenant,
                    )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(
                        f"Failed to post payroll GL for {payroll.id}: {e}"
                    )
            created_records.append(payroll)
        
        serializer = PayrollSerializer(created_records, many=True)
        return Response({
            'message': f'Successfully processed payroll for {len(created_records)} employees',
            'records': serializer.data
        }, status=status.HTTP_201_CREATED)



@extend_schema(
    tags=['HR - Reports'],
    summary='Get HR reports and analytics',
    description='Returns comprehensive HR analytics including employee stats, department breakdown, attendance trends, and employment type distribution'
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def hr_reports(request):
    """HR Reports API endpoint"""
    from django.db.models import Count, Avg, Sum
    from datetime import datetime, timedelta
    
    tenant = request.user.tenant
    
    # Get all employees
    employees = Employee.objects.filter(tenant=tenant)
    active_employees = employees.filter(status='active')
    
    # Summary stats
    total_employees = employees.count()
    active_count = active_employees.count()
    on_leave_count = 0  # Count employees with active leave requests
    leave_requests = LeaveRequest.objects.filter(
        tenant=tenant,
        status='approved',
        start_date__lte=datetime.now().date(),
        end_date__gte=datetime.now().date()
    )
    on_leave_count = leave_requests.values('employee').distinct().count()
    
    # Average salary
    avg_salary = active_employees.aggregate(avg=Avg('basic_salary'))['avg'] or Decimal('0')
    
    # Department breakdown
    department_data = Department.objects.filter(tenant=tenant).annotate(
        employee_count=Count('employees', filter=Q(employees__status='active'))
    ).values('name', 'employee_count').order_by('-employee_count')
    
    # Attendance trend (last 7 days)
    today = datetime.now().date()
    attendance_data = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        total_records = Attendance.objects.filter(tenant=tenant, date=date).count()
        present_records = Attendance.objects.filter(
            tenant=tenant, date=date, status__in=['present', 'late']
        ).count()
        
        if total_records > 0:
            rate = round((present_records / total_records) * 100, 1)
        else:
            rate = 0
        
        attendance_data.append({
            'date': date.strftime('%Y-%m-%d'),
            'rate': rate
        })
    
    # Employment type distribution
    employment_type_data = active_employees.values('employment_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Calculate percentages
    for item in employment_type_data:
        item['percentage'] = round((item['count'] / active_count * 100), 1) if active_count > 0 else 0
    
    return Response({
        'summary': {
            'total_employees': total_employees,
            'active_employees': active_count,
            'on_leave': on_leave_count,
            'avg_salary': float(avg_salary)
        },
        'department_data': list(department_data),
        'attendance_trend': attendance_data,
        'employment_type_data': list(employment_type_data)
    })
