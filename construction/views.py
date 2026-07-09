from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from users.dynamic_permissions import DynamicModulePermission, _effective_role
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from django.utils import timezone
from django.db.models import Sum, F, Q, Count
from decimal import Decimal

from .models import Site, Worker, Attendance, DailyLog, MaterialConsumption, Equipment, EquipmentUsageLog
from .serializers import (
    SiteSerializer, WorkerSerializer, AttendanceSerializer, DailyLogSerializer,
    MaterialConsumptionSerializer, EquipmentSerializer, EquipmentUsageLogSerializer,
    DailyLogCreateSerializer
)


@extend_schema_view(
    list=extend_schema(tags=['Construction - Sites'], summary='List all construction sites'),
    retrieve=extend_schema(tags=['Construction - Sites'], summary='Get site details'),
    create=extend_schema(tags=['Construction - Sites'], summary='Create new site'),
    update=extend_schema(tags=['Construction - Sites'], summary='Update site'),
    partial_update=extend_schema(tags=['Construction - Sites'], summary='Partially update site'),
    destroy=extend_schema(tags=['Construction - Sites'], summary='Delete site'),
)
class SiteViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Construction Sites
    Includes budget tracking and cost calculations
    """
    serializer_class = SiteSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'construction'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'manager']
    search_fields = ['name', 'location', 'client_name']
    ordering_fields = ['name', 'start_date', 'allocated_budget', 'created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        user = self.request.user
        queryset = Site.objects.filter(tenant=user.tenant).select_related('manager', 'warehouse')
        
        # Managers only see their assigned sites
        role = _effective_role(user, user.tenant)
        if role == 'manager':
            from hr.models import Employee
            employee = Employee.objects.filter(tenant=user.tenant, user=user).first()
            if employee:
                queryset = queryset.filter(manager=employee)
            else:
                queryset = queryset.none()
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['Construction - Sites'],
        summary='Generate site budget report',
        description='Returns detailed budget vs actual spend report for a site',
        responses={200: {
            'type': 'object',
            'properties': {
                'site_id': {'type': 'string'},
                'site_name': {'type': 'string'},
                'allocated_budget': {'type': 'number'},
                'material_cost': {'type': 'number'},
                'labor_cost': {'type': 'number'},
                'equipment_cost': {'type': 'number'},
                'other_expenses': {'type': 'number'},
                'total_actual_spend': {'type': 'number'},
                'remaining_budget': {'type': 'number'},
                'budget_percentage': {'type': 'number'},
                'status': {'type': 'string'},
                'budget_health': {'type': 'string'},
            }
        }}
    )
    @action(detail=True, methods=['get'])
    def generate_site_report(self, request, pk=None):
        """
        Generate comprehensive budget vs actual spend report
        """
        site = self.get_object()
        
        # Calculate costs
        material_cost = site.get_material_cost()
        labor_cost = site.get_labor_cost()
        other_expenses = site.get_other_expenses()
        equipment_cost = site.get_equipment_cost()
        total_actual_spend = site.get_actual_spend()
        remaining_budget = site.allocated_budget - total_actual_spend
        budget_percentage = (total_actual_spend / site.allocated_budget * 100) if site.allocated_budget > 0 else Decimal('0.00')
        
        # Determine budget health
        if budget_percentage < 80:
            budget_health = 'green'
        elif budget_percentage < 100:
            budget_health = 'yellow'
        else:
            budget_health = 'red'
        
        report = {
            'site_id': str(site.id),
            'site_name': site.name,
            'location': site.location,
            'client_name': site.client_name or '',
            'manager': site.manager.name if site.manager else '',
            'status': site.status,
            
            # Budget
            'allocated_budget': float(site.allocated_budget),
            
            # Cost breakdown
            'material_cost': float(material_cost),
            'labor_cost': float(labor_cost),
            'equipment_cost': float(equipment_cost),
            'other_expenses': float(other_expenses),
            'total_actual_spend': float(total_actual_spend),
            
            # Budget analysis
            'remaining_budget': float(remaining_budget),
            'budget_percentage': float(budget_percentage),
            'budget_health': budget_health,
            
            # Timeline
            'start_date': site.start_date.isoformat(),
            'estimated_end_date': site.estimated_end_date.isoformat() if site.estimated_end_date else None,
            'actual_end_date': site.actual_end_date.isoformat() if site.actual_end_date else None,
        }
        
        return Response(report)
    
    @extend_schema(
        tags=['Construction - Sites'],
        summary='Get site dashboard data',
        description='Returns dashboard metrics for a site'
    )
    @action(detail=True, methods=['get'])
    def dashboard(self, request, pk=None):
        """Get site dashboard metrics"""
        site = self.get_object()
        
        # Worker statistics
        total_workers = site.workers.filter(status='active').count()
        
        # Recent attendance (last 7 days)
        from datetime import timedelta
        seven_days_ago = timezone.now().date() - timedelta(days=7)
        recent_attendance = site.attendances.filter(date__gte=seven_days_ago)
        
        attendance_stats = recent_attendance.aggregate(
            present=Count('id', filter=Q(status='present')),
            absent=Count('id', filter=Q(status='absent')),
            half_day=Count('id', filter=Q(status='half_day')),
            overtime=Count('id', filter=Q(status='overtime')),
        )
        
        # Material consumption (last 30 days)
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        recent_consumption = site.material_consumptions.filter(
            created_at__date__gte=thirty_days_ago
        ).count()
        
        # Daily logs count
        total_logs = site.daily_logs.count()
        
        dashboard_data = {
            'site': SiteSerializer(site).data,
            'workers': {
                'total_active': total_workers,
            },
            'attendance': attendance_stats,
            'material_consumption': {
                'last_30_days': recent_consumption,
            },
            'daily_logs': {
                'total': total_logs,
            }
        }
        
        return Response(dashboard_data)


@extend_schema_view(
    list=extend_schema(tags=['Construction - Workers'], summary='List all workers'),
    retrieve=extend_schema(tags=['Construction - Workers'], summary='Get worker details'),
    create=extend_schema(tags=['Construction - Workers'], summary='Create new worker'),
    update=extend_schema(tags=['Construction - Workers'], summary='Update worker'),
    partial_update=extend_schema(tags=['Construction - Workers'], summary='Partially update worker'),
    destroy=extend_schema(tags=['Construction - Workers'], summary='Delete worker'),
)
class WorkerViewSet(viewsets.ModelViewSet):
    """ViewSet for Construction Workers"""
    serializer_class = WorkerSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'construction'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'status', 'assigned_site']
    search_fields = ['name', 'phone', 'id_number']
    ordering_fields = ['name', 'daily_wage', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        return Worker.objects.filter(tenant=self.request.user.tenant).select_related('assigned_site')
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)

    def destroy(self, request, *args, **kwargs):
        """Deactivate worker instead of hard delete to preserve payroll history."""
        worker = self.get_object()
        worker.status = 'inactive'
        worker.save(update_fields=['status', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(tags=['Construction - Attendance'], summary='List all attendance records'),
    retrieve=extend_schema(tags=['Construction - Attendance'], summary='Get attendance details'),
    create=extend_schema(tags=['Construction - Attendance'], summary='Mark attendance'),
    update=extend_schema(tags=['Construction - Attendance'], summary='Update attendance'),
    partial_update=extend_schema(tags=['Construction - Attendance'], summary='Partially update attendance'),
    destroy=extend_schema(tags=['Construction - Attendance'], summary='Delete attendance'),
)
class AttendanceViewSet(viewsets.ModelViewSet):
    """ViewSet for Worker Attendance"""
    serializer_class = AttendanceSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'construction'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['worker', 'site', 'date', 'status']
    search_fields = ['worker__name', 'site__name']
    ordering_fields = ['date', 'created_at']
    ordering = ['-date']
    
    def get_queryset(self):
        return Attendance.objects.filter(tenant=self.request.user.tenant).select_related(
            'worker', 'site', 'marked_by'
        )
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)
    
    @extend_schema(
        tags=['Construction - Attendance'],
        summary='Bulk mark attendance',
        description='Mark attendance for multiple workers at once',
        request={
            'type': 'object',
            'properties': {
                'site': {'type': 'string'},
                'date': {'type': 'string', 'format': 'date'},
                'attendances': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'worker': {'type': 'string'},
                            'status': {'type': 'string'},
                            'check_in': {'type': 'string', 'format': 'time'},
                            'check_out': {'type': 'string', 'format': 'time'},
                        }
                    }
                }
            }
        }
    )
    @action(detail=False, methods=['post'])
    def bulk_mark(self, request):
        """Bulk mark attendance for multiple workers"""
        site_id = request.data.get('site')
        date = request.data.get('date')
        attendances_data = request.data.get('attendances', [])
        
        if not site_id or not date or not attendances_data:
            return Response(
                {'error': 'site, date, and attendances are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        created_attendances = []
        updated_attendances = []
        errors = []
        tenant = request.user.tenant

        for attendance_data in attendances_data:
            attendance_data['site'] = site_id
            attendance_data['date'] = date
            worker_id = attendance_data.get('worker')

            existing = None
            if worker_id:
                existing = Attendance.objects.filter(
                    tenant=tenant,
                    worker_id=worker_id,
                    site_id=site_id,
                    date=date,
                ).first()

            if existing:
                serializer = self.get_serializer(existing, data=attendance_data, partial=True)
            else:
                serializer = self.get_serializer(data=attendance_data)

            if serializer.is_valid():
                instance = serializer.save(tenant=tenant, marked_by=request.user)
                if existing:
                    updated_attendances.append(serializer.data)
                else:
                    created_attendances.append(serializer.data)
            else:
                errors.append({
                    'worker': attendance_data.get('worker'),
                    'errors': serializer.errors
                })

        return Response({
            'created': created_attendances,
            'updated': updated_attendances,
            'errors': errors
        })
    
    @extend_schema(
        tags=['Construction - Attendance'],
        summary='Monthly payroll summary per site',
        description='Returns monthly payroll summary for a specific site',
        parameters=[
            OpenApiParameter(name='site', description='Site ID', required=True, type=str),
            OpenApiParameter(name='month', description='Month (1-12)', required=True, type=int),
            OpenApiParameter(name='year', description='Year (e.g., 2024)', required=True, type=int),
        ],
        responses={200: {
            'type': 'object',
            'properties': {
                'site_id': {'type': 'string'},
                'site_name': {'type': 'string'},
                'month': {'type': 'integer'},
                'year': {'type': 'integer'},
                'total_payroll': {'type': 'number'},
                'worker_breakdown': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'worker_id': {'type': 'string'},
                            'worker_name': {'type': 'string'},
                            'category': {'type': 'string'},
                            'days_present': {'type': 'integer'},
                            'days_half_day': {'type': 'integer'},
                            'days_overtime': {'type': 'integer'},
                            'total_wage': {'type': 'number'},
                        }
                    }
                }
            }
        }}
    )
    @action(detail=False, methods=['get'])
    def payroll_summary_by_site(self, request):
        """Monthly payroll summary per site"""
        site_id = request.query_params.get('site')
        month = request.query_params.get('month')
        year = request.query_params.get('year')
        
        if not site_id or not month or not year:
            return Response(
                {'error': 'site, month, and year are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            site = Site.objects.get(id=site_id, tenant=request.user.tenant)
        except Site.DoesNotExist:
            return Response(
                {'error': 'Site not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get all attendance records for this site in the specified month
        attendances = Attendance.objects.filter(
            tenant=request.user.tenant,
            site=site,
            date__month=int(month),
            date__year=int(year)
        ).select_related('worker')
        
        # Calculate worker breakdown
        worker_summary = {}
        for attendance in attendances:
            worker_id = str(attendance.worker.id)
            if worker_id not in worker_summary:
                worker_summary[worker_id] = {
                    'worker_id': worker_id,
                    'worker_name': attendance.worker.name,
                    'category': attendance.worker.category,
                    'daily_wage': float(attendance.worker.daily_wage),
                    'days_present': 0,
                    'days_half_day': 0,
                    'days_overtime': 0,
                    'days_absent': 0,
                    'total_wage': Decimal('0.00'),
                }
            
            # Count attendance by status
            if attendance.status == 'present':
                worker_summary[worker_id]['days_present'] += 1
            elif attendance.status == 'half_day':
                worker_summary[worker_id]['days_half_day'] += 1
            elif attendance.status == 'overtime':
                worker_summary[worker_id]['days_overtime'] += 1
            elif attendance.status == 'absent':
                worker_summary[worker_id]['days_absent'] += 1
            
            # Add wage amount
            worker_summary[worker_id]['total_wage'] += attendance.wage_amount
        
        # Convert to list and calculate totals
        worker_breakdown = []
        total_payroll = Decimal('0.00')
        
        for worker_data in worker_summary.values():
            worker_data['total_wage'] = float(worker_data['total_wage'])
            total_payroll += Decimal(str(worker_data['total_wage']))
            worker_breakdown.append(worker_data)
        
        # Sort by worker name
        worker_breakdown.sort(key=lambda x: x['worker_name'])
        
        return Response({
            'site_id': str(site.id),
            'site_name': site.name,
            'month': int(month),
            'year': int(year),
            'total_payroll': float(total_payroll),
            'worker_count': len(worker_breakdown),
            'worker_breakdown': worker_breakdown,
        })
    
    @extend_schema(
        tags=['Construction - Attendance'],
        summary='Monthly payroll summary per worker',
        description='Returns monthly payroll summary for a specific worker across all sites',
        parameters=[
            OpenApiParameter(name='worker', description='Worker ID', required=True, type=str),
            OpenApiParameter(name='month', description='Month (1-12)', required=True, type=int),
            OpenApiParameter(name='year', description='Year (e.g., 2024)', required=True, type=int),
        ],
        responses={200: {
            'type': 'object',
            'properties': {
                'worker_id': {'type': 'string'},
                'worker_name': {'type': 'string'},
                'category': {'type': 'string'},
                'daily_wage': {'type': 'number'},
                'month': {'type': 'integer'},
                'year': {'type': 'integer'},
                'total_wage': {'type': 'number'},
                'site_breakdown': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'site_id': {'type': 'string'},
                            'site_name': {'type': 'string'},
                            'days_present': {'type': 'integer'},
                            'days_half_day': {'type': 'integer'},
                            'days_overtime': {'type': 'integer'},
                            'total_wage': {'type': 'number'},
                        }
                    }
                }
            }
        }}
    )
    @action(detail=False, methods=['get'])
    def payroll_summary_by_worker(self, request):
        """Monthly payroll summary per worker"""
        worker_id = request.query_params.get('worker')
        month = request.query_params.get('month')
        year = request.query_params.get('year')
        
        if not worker_id or not month or not year:
            return Response(
                {'error': 'worker, month, and year are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            worker = Worker.objects.get(id=worker_id, tenant=request.user.tenant)
        except Worker.DoesNotExist:
            return Response(
                {'error': 'Worker not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get all attendance records for this worker in the specified month
        attendances = Attendance.objects.filter(
            tenant=request.user.tenant,
            worker=worker,
            date__month=int(month),
            date__year=int(year)
        ).select_related('site')
        
        # Calculate site breakdown
        site_summary = {}
        for attendance in attendances:
            site_id = str(attendance.site.id)
            if site_id not in site_summary:
                site_summary[site_id] = {
                    'site_id': site_id,
                    'site_name': attendance.site.name,
                    'days_present': 0,
                    'days_half_day': 0,
                    'days_overtime': 0,
                    'days_absent': 0,
                    'total_wage': Decimal('0.00'),
                }
            
            # Count attendance by status
            if attendance.status == 'present':
                site_summary[site_id]['days_present'] += 1
            elif attendance.status == 'half_day':
                site_summary[site_id]['days_half_day'] += 1
            elif attendance.status == 'overtime':
                site_summary[site_id]['days_overtime'] += 1
            elif attendance.status == 'absent':
                site_summary[site_id]['days_absent'] += 1
            
            # Add wage amount
            site_summary[site_id]['total_wage'] += attendance.wage_amount
        
        # Convert to list and calculate totals
        site_breakdown = []
        total_wage = Decimal('0.00')
        
        for site_data in site_summary.values():
            site_data['total_wage'] = float(site_data['total_wage'])
            total_wage += Decimal(str(site_data['total_wage']))
            site_breakdown.append(site_data)
        
        # Sort by site name
        site_breakdown.sort(key=lambda x: x['site_name'])
        
        # Calculate total days worked
        total_days_present = sum(s['days_present'] for s in site_breakdown)
        total_days_half_day = sum(s['days_half_day'] for s in site_breakdown)
        total_days_overtime = sum(s['days_overtime'] for s in site_breakdown)
        
        return Response({
            'worker_id': str(worker.id),
            'worker_name': worker.name,
            'category': worker.category,
            'daily_wage': float(worker.daily_wage),
            'month': int(month),
            'year': int(year),
            'total_wage': float(total_wage),
            'total_days_present': total_days_present,
            'total_days_half_day': total_days_half_day,
            'total_days_overtime': total_days_overtime,
            'site_count': len(site_breakdown),
            'site_breakdown': site_breakdown,
        })


@extend_schema_view(
    list=extend_schema(tags=['Construction - Daily Logs'], summary='List all daily logs'),
    retrieve=extend_schema(tags=['Construction - Daily Logs'], summary='Get daily log details'),
    create=extend_schema(tags=['Construction - Daily Logs'], summary='Create daily log'),
    update=extend_schema(tags=['Construction - Daily Logs'], summary='Update daily log'),
    partial_update=extend_schema(tags=['Construction - Daily Logs'], summary='Partially update daily log'),
    destroy=extend_schema(tags=['Construction - Daily Logs'], summary='Delete daily log'),
)
class DailyLogViewSet(viewsets.ModelViewSet):
    """ViewSet for Daily Site Logs with 24-hour immutability (SRS 4.6)"""
    permission_classes = [DynamicModulePermission]
    permission_module = 'construction'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['site', 'date']
    search_fields = ['work_description', 'progress_notes']
    ordering_fields = ['date', 'created_at']
    ordering = ['-date']

    def get_serializer_class(self):
        if self.action == 'create':
            return DailyLogCreateSerializer
        return DailyLogSerializer

    def get_queryset(self):
        return DailyLog.objects.filter(tenant=self.request.user.tenant).select_related(
            'site', 'submitted_by', 'reviewed_by'
        ).prefetch_related('material_consumptions__product')

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)

    def update(self, request, *args, **kwargs):
        """Enforce 24-hour immutability rule (SRS 4.6)"""
        instance = self.get_object()

        if not instance.is_editable():
            from rest_framework.exceptions import PermissionDenied
            hours_passed = (timezone.now() - instance.created_at).total_seconds() / 3600
            raise PermissionDenied(
                f"This daily log cannot be edited. It was created {hours_passed:.1f} hours ago. "
                "Daily logs are immutable after 24 hours."
            )

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Enforce 24-hour immutability rule (SRS 4.6)"""
        instance = self.get_object()

        if not instance.is_editable():
            from rest_framework.exceptions import PermissionDenied
            hours_passed = (timezone.now() - instance.created_at).total_seconds() / 3600
            raise PermissionDenied(
                f"This daily log cannot be edited. It was created {hours_passed:.1f} hours ago. "
                "Daily logs are immutable after 24 hours."
            )

        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Enforce 24-hour immutability rule (SRS 4.6)"""
        instance = self.get_object()

        if not instance.is_editable():
            from rest_framework.exceptions import PermissionDenied
            hours_passed = (timezone.now() - instance.created_at).total_seconds() / 3600
            raise PermissionDenied(
                f"This daily log cannot be deleted. It was created {hours_passed:.1f} hours ago. "
                "Daily logs are immutable after 24 hours."
            )

        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        tags=['Construction - Daily Logs'],
        summary='Review daily log',
        description='Manager reviews and comments on a daily log'
    )
    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """Manager reviews a daily log"""
        daily_log = self.get_object()

        comments = request.data.get('comments', '')

        daily_log.reviewed_by = request.user
        daily_log.reviewed_at = timezone.now()
        daily_log.manager_comments = comments
        daily_log.save()

        serializer = self.get_serializer(daily_log)
        return Response(serializer.data)



@extend_schema_view(
    list=extend_schema(tags=['Construction - Material Consumption'], summary='List all material consumption'),
    retrieve=extend_schema(tags=['Construction - Material Consumption'], summary='Get consumption details'),
    create=extend_schema(tags=['Construction - Material Consumption'], summary='Log material consumption'),
    update=extend_schema(tags=['Construction - Material Consumption'], summary='Update consumption'),
    partial_update=extend_schema(tags=['Construction - Material Consumption'], summary='Partially update consumption'),
    destroy=extend_schema(tags=['Construction - Material Consumption'], summary='Delete consumption'),
)
class MaterialConsumptionViewSet(viewsets.ModelViewSet):
    """ViewSet for Material Consumption"""
    serializer_class = MaterialConsumptionSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'construction'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['site', 'daily_log', 'product']
    search_fields = ['product__name', 'notes']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        return MaterialConsumption.objects.filter(tenant=self.request.user.tenant).select_related(
            'site', 'daily_log', 'product'
        )
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


@extend_schema_view(
    list=extend_schema(tags=['Construction - Equipment'], summary='List all equipment'),
    retrieve=extend_schema(tags=['Construction - Equipment'], summary='Get equipment details'),
    create=extend_schema(tags=['Construction - Equipment'], summary='Create new equipment'),
    update=extend_schema(tags=['Construction - Equipment'], summary='Update equipment'),
    partial_update=extend_schema(tags=['Construction - Equipment'], summary='Partially update equipment'),
    destroy=extend_schema(tags=['Construction - Equipment'], summary='Delete equipment'),
)
class EquipmentViewSet(viewsets.ModelViewSet):
    """ViewSet for Construction Equipment"""
    serializer_class = EquipmentSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'construction'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['ownership_type', 'status', 'assigned_site']
    search_fields = ['name', 'equipment_type', 'registration_number']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        return Equipment.objects.filter(tenant=self.request.user.tenant).select_related('assigned_site')
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


@extend_schema_view(
    list=extend_schema(tags=['Construction - Equipment Usage'], summary='List all equipment usage logs'),
    retrieve=extend_schema(tags=['Construction - Equipment Usage'], summary='Get usage log details'),
    create=extend_schema(tags=['Construction - Equipment Usage'], summary='Log equipment usage'),
    update=extend_schema(tags=['Construction - Equipment Usage'], summary='Update usage log'),
    partial_update=extend_schema(tags=['Construction - Equipment Usage'], summary='Partially update usage log'),
    destroy=extend_schema(tags=['Construction - Equipment Usage'], summary='Delete usage log'),
)
class EquipmentUsageLogViewSet(viewsets.ModelViewSet):
    """ViewSet for Equipment Usage Logs"""
    serializer_class = EquipmentUsageLogSerializer
    permission_classes = [DynamicModulePermission]
    permission_module = 'construction'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['equipment', 'site', 'date']
    search_fields = ['equipment__name', 'site__name']
    ordering_fields = ['date', 'created_at']
    ordering = ['-date']
    
    def get_queryset(self):
        return EquipmentUsageLog.objects.filter(tenant=self.request.user.tenant).select_related(
            'equipment', 'site', 'daily_log'
        )
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)
