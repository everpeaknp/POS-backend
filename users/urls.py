from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.utils import extend_schema
from .views import (
    RegisterView, UserProfileView, UserViewSet, CustomTokenObtainPairView, 
    AuditLogViewSet, get_permissions, get_my_permissions, update_permissions,
    update_user_profile, change_password, get_notification_preferences,
    update_notification_preferences, get_active_sessions, revoke_session,
    get_appearance_preferences, update_appearance_preferences
)

# Add schema documentation to JWT refresh view
TokenRefreshView = extend_schema(
    tags=['Authentication'],
    summary='Refresh access token',
    description='Get a new access token using a valid refresh token.',
)(TokenRefreshView)

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
    path('sessions/', get_active_sessions, name='get_active_sessions'),
    path('sessions/<str:session_id>/', revoke_session, name='revoke_session'),
    
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
]
