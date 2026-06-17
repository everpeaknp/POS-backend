from django.urls import path
from .views import (
    SiteViewSet, WorkerViewSet, AttendanceViewSet, DailyLogViewSet,
    MaterialConsumptionViewSet, EquipmentViewSet, EquipmentUsageLogViewSet
)

urlpatterns = [
    # Sites
    path('sites/', SiteViewSet.as_view({'get': 'list', 'post': 'create'}), name='site-list'),
    path('sites/<int:pk>/', SiteViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='site-detail'),
    path('sites/<int:pk>/generate_site_report/', SiteViewSet.as_view({'get': 'generate_site_report'}), name='site-report'),
    path('sites/<int:pk>/dashboard/', SiteViewSet.as_view({'get': 'dashboard'}), name='site-dashboard'),
    
    # Workers
    path('workers/', WorkerViewSet.as_view({'get': 'list', 'post': 'create'}), name='worker-list'),
    path('workers/<int:pk>/', WorkerViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='worker-detail'),
    
    # Attendance
    path('attendance/', AttendanceViewSet.as_view({'get': 'list', 'post': 'create'}), name='attendance-list'),
    path('attendance/<int:pk>/', AttendanceViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='attendance-detail'),
    path('attendance/bulk_mark/', AttendanceViewSet.as_view({'post': 'bulk_mark'}), name='attendance-bulk-mark'),
    path('attendance/payroll_summary_by_site/', AttendanceViewSet.as_view({'get': 'payroll_summary_by_site'}), name='attendance-payroll-site'),
    path('attendance/payroll_summary_by_worker/', AttendanceViewSet.as_view({'get': 'payroll_summary_by_worker'}), name='attendance-payroll-worker'),
    
    # Daily Logs
    path('daily-logs/', DailyLogViewSet.as_view({'get': 'list', 'post': 'create'}), name='daily-log-list'),
    path('daily-logs/<int:pk>/', DailyLogViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='daily-log-detail'),
    path('daily-logs/<int:pk>/review/', DailyLogViewSet.as_view({'post': 'review'}), name='daily-log-review'),
    
    # Material Consumption
    path('material-consumption/', MaterialConsumptionViewSet.as_view({'get': 'list', 'post': 'create'}), name='material-consumption-list'),
    path('material-consumption/<int:pk>/', MaterialConsumptionViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='material-consumption-detail'),
    
    # Equipment
    path('equipment/', EquipmentViewSet.as_view({'get': 'list', 'post': 'create'}), name='equipment-list'),
    path('equipment/<int:pk>/', EquipmentViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='equipment-detail'),
    
    # Equipment Usage
    path('equipment-usage/', EquipmentUsageLogViewSet.as_view({'get': 'list', 'post': 'create'}), name='equipment-usage-list'),
    path('equipment-usage/<int:pk>/', EquipmentUsageLogViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='equipment-usage-detail'),
]
