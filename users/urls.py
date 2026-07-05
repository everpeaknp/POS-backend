from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.utils import extend_schema
from .views import (
    RegisterView, UserProfileView, UserViewSet, CustomTokenObtainPairView, CustomTokenRefreshView,
    AuditLogViewSet, get_permissions, get_my_permissions, update_permissions,
    update_user_profile, change_password, get_notification_preferences,
    update_notification_preferences, get_active_sessions, revoke_session, revoke_other_sessions,
    get_appearance_preferences, update_appearance_preferences, NotificationViewSet,
    get_privacy_preferences, update_privacy_preferences, export_user_data, delete_account,
    ensure_current_session,
)

TokenRefreshView = extend_schema(
    tags=['Authentication'],
    summary='Refresh access token',
    description='Get a new access token using a valid refresh token.',
)(CustomTokenRefreshView)

urlpatterns = [
    # Authentication
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('profile/', UserProfileView.as_view(), name='user_profile'),
    
    # User Settings
    path('me/', update_user_profile, name='update_user_profile'),
    path('password/', change_password, name='change_password'),
    path('preferences/', get_notification_preferences, name='get_notification_preferences'),
    path('preferences/update/', update_notification_preferences, name='update_notification_preferences'),
    path('appearance/', get_appearance_preferences, name='get_appearance_preferences'),
    path('appearance/update/', update_appearance_preferences, name='update_appearance_preferences'),
    path('privacy/', get_privacy_preferences, name='get_privacy_preferences'),
    path('privacy/update/', update_privacy_preferences, name='update_privacy_preferences'),
    path('sessions/', get_active_sessions, name='get_active_sessions'),
    path('sessions/ensure/', ensure_current_session, name='ensure_current_session'),
    path('sessions/revoke-others/', revoke_other_sessions, name='revoke_other_sessions'),
    path('sessions/<str:session_id>/', revoke_session, name='revoke_session'),
    path('export/', export_user_data, name='export_user_data'),
    path('account/delete/', delete_account, name='delete_account'),
    
    # Permissions
    path('permissions/', get_permissions, name='get_permissions'),
    path('permissions/me/', get_my_permissions, name='get_my_permissions'),
    path('permissions/update/', update_permissions, name='update_permissions'),
    
    # Users
    path('users/', UserViewSet.as_view({'get': 'list', 'post': 'create'}), name='user-list'),
    path('users/<int:pk>/', UserViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='user-detail'),
    
    # Audit Logs
    path('audit-logs/', AuditLogViewSet.as_view({'get': 'list'}), name='audit-log-list'),
    path('audit-logs/<int:pk>/', AuditLogViewSet.as_view({'get': 'retrieve'}), name='audit-log-detail'),

    # Notifications
    path('notifications/', NotificationViewSet.as_view({'get': 'list'}), name='notification-list'),
    path('notifications/<int:pk>/', NotificationViewSet.as_view({'get': 'retrieve'}), name='notification-detail'),
    path('notifications/<int:pk>/mark-read/', NotificationViewSet.as_view({'post': 'mark_read'}), name='notification-mark-read'),
    path('notifications/mark-all-read/', NotificationViewSet.as_view({'post': 'mark_all_read'}), name='notification-mark-all-read'),
]
