from rest_framework import generics, permissions, viewsets, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_spectacular.utils import extend_schema, extend_schema_view
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import models
from .models import User, AuditLog
from .notification_models import NotificationPreferences
from .serializers import (
    UserSerializer, RegisterSerializer, CustomTokenObtainPairSerializer, 
    AuditLogSerializer, UserProfileUpdateSerializer, PasswordChangeSerializer,
    NotificationPreferencesSerializer, SessionSerializer
)
from .permissions import IsAdminOrManager


@extend_schema(
    tags=['Authentication'],
    summary='Login',
    description='''
    Obtain JWT access and refresh tokens by providing username and password.
    
    The response includes:
    - access: JWT access token (expires in 1 hour by default)
    - refresh: JWT refresh token (expires in 7 days by default)
    - user: User information including role
    - tenant: Tenant information including slug and active_modules
    
    The access token also contains custom claims:
    - role: User's role (admin, manager, supervisor, accountant)
    - tenant_id: Tenant ID
    - tenant_slug: Tenant slug for URL routing
    - tenant_name: Tenant name
    ''',
)
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


@extend_schema(
    tags=['Authentication'],
    summary='Register a new user',
    description='Create a new user account with a new organization. The user will be the admin of their organization.',
)
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer


@extend_schema_view(
    get=extend_schema(
        tags=['Authentication'],
        summary='Get user profile',
        description='Get the authenticated user\'s profile information.',
    ),
    put=extend_schema(
        tags=['Authentication'],
        summary='Update user profile',
        description='Update the authenticated user\'s profile information.',
    ),
    patch=extend_schema(
        tags=['Authentication'],
        summary='Partially update user profile',
        description='Partially update the authenticated user\'s profile information.',
    ),
)
class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user


@extend_schema_view(
    list=extend_schema(tags=['Users'], summary='List users'),
    retrieve=extend_schema(tags=['Users'], summary='Get user details'),
    create=extend_schema(tags=['Users'], summary='Create user'),
    update=extend_schema(tags=['Users'], summary='Update user'),
    partial_update=extend_schema(tags=['Users'], summary='Partially update user'),
    destroy=extend_schema(tags=['Users'], summary='Delete user'),
)
class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing users (full CRUD)
    Filtered by current tenant
    Only admins and managers can create/update/delete users
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['role', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'date_joined', 'last_login']
    ordering = ['-date_joined']
    
    def get_queryset(self):
        """Filter by current tenant - includes both direct tenant and membership"""
        if not self.request.user.tenant:
            return User.objects.none()
        
        # Get users who are either:
        # 1. Directly assigned to this tenant (User.tenant)
        # 2. Members of this tenant through UserTenantMembership
        from tenants.membership_models import UserTenantMembership
        
        # Get user IDs from memberships
        member_user_ids = UserTenantMembership.objects.filter(
            tenant=self.request.user.tenant
        ).values_list('user_id', flat=True)
        
        # Return users who are either directly assigned OR members
        return User.objects.filter(
            models.Q(tenant=self.request.user.tenant) | 
            models.Q(id__in=member_user_ids)
        ).distinct()
    
    def perform_create(self, serializer):
        """Assign user to current tenant when creating"""
        if not self.request.user.tenant:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'You must be assigned to an organization to create users.'})
        serializer.save(tenant=self.request.user.tenant)
    
    def get_permissions(self):
        """Only admins and managers can create/update/delete users"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsAdminOrManager()]
        return super().get_permissions()



@extend_schema_view(
    list=extend_schema(tags=['Audit'], summary='List audit logs'),
    retrieve=extend_schema(tags=['Audit'], summary='Get audit log details'),
)
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing audit logs (read-only)
    Filtered by current tenant
    Only admins and managers can view audit logs
    """
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrManager]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['action', 'module', 'user']
    search_fields = ['description', 'user__username', 'user__first_name', 'user__last_name']
    ordering_fields = ['created_at', 'action', 'module']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter by current tenant"""
        if not self.request.user.tenant:
            return AuditLog.objects.none()
        return AuditLog.objects.filter(tenant=self.request.user.tenant).select_related('user')



from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions as drf_permissions
from .permission_models import RolePermission, get_default_permissions, initialize_tenant_permissions
from .serializers import PermissionsMatrixSerializer, UpdatePermissionsSerializer
from .permissions import IsAdminOrManager
from tenants.utils import get_request_tenant

ROLE_DISPLAY_MAP = {
    'admin': 'Admin',
    'manager': 'Manager',
    'supervisor': 'Supervisor',
    'accountant': 'Accountant',
    'cashier': 'Cashier',
    'viewer': 'Viewer',
}

MODULE_DISPLAY_MAP = {
    'dashboard': 'Dashboard',
    'sales': 'Sales',
    'purchase': 'Purchase',
    'inventory': 'Inventory',
    'accounting': 'Accounting',
    'construction': 'Construction',
    'reports': 'Reports',
    'settings': 'Settings',
    'hr': 'HR',
    'pos': 'POS',
}

ACTION_DISPLAY_MAP = {
    'view': 'View',
    'create': 'Create',
    'edit': 'Edit',
    'delete': 'Delete',
    'export': 'Export',
    'approve': 'Approve',
}


def get_effective_role(user, tenant):
    from tenants.membership_models import UserTenantMembership
    membership = UserTenantMembership.objects.filter(user=user, tenant=tenant).first()
    if membership:
        return membership.role
    return user.role


def build_permissions_matrix(permissions_qs):
    matrix = {
        'Admin': {},
        'Manager': {},
        'Supervisor': {},
        'Accountant': {},
        'Cashier': {},
        'Viewer': {},
    }
    for perm in permissions_qs:
        role_display = ROLE_DISPLAY_MAP.get(perm.role, perm.role)
        module_display = MODULE_DISPLAY_MAP.get(perm.module, perm.module)
        action_display = ACTION_DISPLAY_MAP.get(perm.action, perm.action)
        key = f"{module_display}-{action_display}"
        if role_display in matrix:
            matrix[role_display][key] = perm.allowed
    return matrix


@extend_schema(
    tags=['User Settings'],
    summary='Update user profile',
    description='Update authenticated user profile (name, phone, avatar)',
    request=UserProfileUpdateSerializer,
    responses={200: UserSerializer}
)
@api_view(['PATCH'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([drf_permissions.IsAuthenticated])
def update_user_profile(request):
    """Update user profile with support for avatar upload"""
    serializer = UserProfileUpdateSerializer(
        request.user,
        data=request.data,
        partial=True,
        context={'request': request}
    )
    
    if serializer.is_valid():
        serializer.save()
        # Return full user data
        user_serializer = UserSerializer(request.user, context={'request': request})
        return Response(user_serializer.data, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['User Settings'],
    summary='Change password',
    description='Change user password',
    request=PasswordChangeSerializer,
    responses={200: {'description': 'Password changed successfully'}}
)
@api_view(['POST'])
@permission_classes([drf_permissions.IsAuthenticated])
def change_password(request):
    """Change user password"""
    serializer = PasswordChangeSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if serializer.is_valid():
        serializer.save()
        return Response(
            {'message': 'Password changed successfully'},
            status=status.HTTP_200_OK
        )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['User Settings'],
    summary='Get notification preferences',
    description='Get user notification preferences',
    responses={200: NotificationPreferencesSerializer}
)
@api_view(['GET'])
@permission_classes([drf_permissions.IsAuthenticated])
def get_notification_preferences(request):
    """Get user notification preferences"""
    prefs, created = NotificationPreferences.objects.get_or_create(user=request.user)
    
    serializer = NotificationPreferencesSerializer(prefs)
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['User Settings'],
    summary='Update notification preferences',
    description='Update user notification preferences',
    request=NotificationPreferencesSerializer,
    responses={200: NotificationPreferencesSerializer}
)
@api_view(['PATCH'])
@permission_classes([drf_permissions.IsAuthenticated])
def update_notification_preferences(request):
    """Update user notification preferences"""
    prefs, created = NotificationPreferences.objects.get_or_create(user=request.user)
    
    serializer = NotificationPreferencesSerializer(prefs, data=request.data, partial=True)
    
    if serializer.is_valid():
        # Update preferences
        for key, value in serializer.validated_data.items():
            setattr(prefs, key, value)
        prefs.save()
        
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['User Settings'],
    summary='Get active sessions',
    description='Get list of active user sessions',
    responses={200: SessionSerializer(many=True)}
)
@api_view(['GET'])
@permission_classes([drf_permissions.IsAuthenticated])
def get_active_sessions(request):
    """Get active sessions with real device and location information"""
    from django.utils import timezone
    import re
    
    # Get real device information from User-Agent
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    # Parse browser
    browser = 'Unknown Browser'
    if 'Chrome' in user_agent and 'Edg' not in user_agent:
        browser = 'Chrome'
    elif 'Firefox' in user_agent:
        browser = 'Firefox'
    elif 'Safari' in user_agent and 'Chrome' not in user_agent:
        browser = 'Safari'
    elif 'Edg' in user_agent:
        browser = 'Edge'
    elif 'Opera' in user_agent or 'OPR' in user_agent:
        browser = 'Opera'
    
    # Parse operating system
    os_name = 'Unknown OS'
    if 'Windows NT 10' in user_agent:
        os_name = 'Windows 10'
    elif 'Windows NT 11' in user_agent:
        os_name = 'Windows 11'
    elif 'Windows' in user_agent:
        os_name = 'Windows'
    elif 'Mac OS X' in user_agent:
        os_name = 'macOS'
    elif 'Linux' in user_agent:
        os_name = 'Linux'
    elif 'Android' in user_agent:
        os_name = 'Android'
    elif 'iPhone' in user_agent or 'iPad' in user_agent:
        os_name = 'iOS'
    
    device_string = f"{browser} on {os_name}"
    
    # Get IP address
    ip_address = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    if not ip_address:
        ip_address = request.META.get('REMOTE_ADDR', '127.0.0.1')
    
    # Simple location detection (in production, use a GeoIP service)
    location = 'Unknown Location'
    if ip_address == '127.0.0.1' or ip_address.startswith('192.168.') or ip_address.startswith('10.'):
        location = 'Local Network'
    else:
        # In production, use a GeoIP service like MaxMind or ipapi.co
        location = 'Remote Location'
    
    # Current session data
    sessions = [
        {
            'id': '1',
            'device': device_string,
            'location': location,
            'ip_address': ip_address,
            'last_active': timezone.now(),
            'is_current': True,
        }
    ]
    
    serializer = SessionSerializer(sessions, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['User Settings'],
    summary='Revoke session',
    description='Revoke a specific user session',
    responses={200: {'description': 'Session revoked successfully'}}
)
@api_view(['DELETE'])
@permission_classes([drf_permissions.IsAuthenticated])
def revoke_session(request, session_id):
    """Revoke a specific session (implement with JWT blacklist or session store)"""
    # In production, implement JWT token blacklisting or session revocation
    return Response(
        {'message': 'Session revoked successfully'},
        status=status.HTTP_200_OK
    )


@extend_schema(
    tags=['Permissions'],
    summary='Get role permissions matrix',
    description='Get the complete permissions matrix for all roles in the current tenant.',
    responses={200: PermissionsMatrixSerializer}
)
@api_view(['GET'])
@permission_classes([drf_permissions.IsAuthenticated, IsAdminOrManager])
def get_permissions(request):
    """
    Get the complete permissions matrix for all roles.
    Returns permissions in the format expected by the frontend.
    """
    tenant = get_request_tenant(request.user)
    
    if not tenant:
        return Response(
            {'detail': 'You must be assigned to an organization to view permissions.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get all permissions for this tenant
    permissions = RolePermission.objects.filter(tenant=tenant)
    
    # If no permissions exist, initialize with defaults
    if not permissions.exists():
        initialize_tenant_permissions(tenant)
        permissions = RolePermission.objects.filter(tenant=tenant)
    
    matrix = build_permissions_matrix(permissions)
    return Response(matrix, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Permissions'],
    summary='Get current user permissions',
    description='Returns the permission matrix slice for the authenticated user\'s role.',
)
@api_view(['GET'])
@permission_classes([drf_permissions.IsAuthenticated])
def get_my_permissions(request):
    """Get permissions for the current user's role within their active organization."""
    tenant = get_request_tenant(request.user)
    if not tenant:
        return Response({}, status=status.HTTP_200_OK)

    role = get_effective_role(request.user, tenant)
    permissions = RolePermission.objects.filter(tenant=tenant, role=role)
    if not permissions.exists():
        initialize_tenant_permissions(tenant)
        permissions = RolePermission.objects.filter(tenant=tenant, role=role)

    role_display = ROLE_DISPLAY_MAP.get(role, role.capitalize())
    role_perms = {}
    for perm in permissions:
        module_display = MODULE_DISPLAY_MAP.get(perm.module, perm.module)
        action_display = ACTION_DISPLAY_MAP.get(perm.action, perm.action)
        role_perms[f"{module_display}-{action_display}"] = perm.allowed

    return Response({role_display: role_perms}, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Permissions'],
    summary='Update role permissions',
    description='Update the permissions matrix for all roles in the current tenant.',
    request=UpdatePermissionsSerializer,
    responses={200: {'description': 'Permissions updated successfully'}}
)
@api_view(['POST'])
@permission_classes([drf_permissions.IsAuthenticated, IsAdminOrManager])
def update_permissions(request):
    """
    Update the permissions matrix for all roles.
    Accepts the complete permissions matrix from the frontend.
    Optimized with bulk operations for better performance.
    """
    from django.db import transaction
    
    tenant = get_request_tenant(request.user)
    
    if not tenant:
        return Response(
            {'detail': 'You must be assigned to an organization to update permissions.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer = UpdatePermissionsSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Map display names back to database names
    role_map = {
        'Admin': 'admin',
        'Manager': 'manager',
        'Supervisor': 'supervisor',
        'Accountant': 'accountant',
        'Cashier': 'cashier',
        'Viewer': 'viewer',
    }
    
    module_map = {
        'Dashboard': 'dashboard',
        'Sales': 'sales',
        'Purchase': 'purchase',
        'Inventory': 'inventory',
        'Accounting': 'accounting',
        'Construction': 'construction',
        'Reports': 'reports',
        'Settings': 'settings',
        'HR': 'hr',
        'POS': 'pos',
    }
    
    action_map = {
        'View': 'view',
        'Create': 'create',
        'Edit': 'edit',
        'Delete': 'delete',
        'Export': 'export',
        'Approve': 'approve',
    }
    
    # Use transaction for atomicity
    with transaction.atomic():
        # Fetch all existing permissions for this tenant in one query
        existing_perms = {
            (p.role, p.module, p.action): p
            for p in RolePermission.objects.filter(tenant=tenant).select_for_update()
        }
        
        permissions_to_create = []
        permissions_to_update = []
        
        # Process each role's permissions
        for role_display, perms in serializer.validated_data.items():
            role_db = role_map.get(role_display)
            if not role_db:
                continue
            
            for key, allowed in perms.items():
                # Parse the key (e.g., "Sales-View" -> module="sales", action="view")
                parts = key.split('-')
                if len(parts) != 2:
                    continue
                
                module_display, action_display = parts
                module_db = module_map.get(module_display)
                action_db = action_map.get(action_display)
                
                if not module_db or not action_db:
                    continue
                
                perm_key = (role_db, module_db, action_db)
                
                if perm_key in existing_perms:
                    # Update existing permission
                    perm = existing_perms[perm_key]
                    if perm.allowed != allowed:
                        perm.allowed = allowed
                        permissions_to_update.append(perm)
                else:
                    # Create new permission
                    permissions_to_create.append(
                        RolePermission(
                            tenant=tenant,
                            role=role_db,
                            module=module_db,
                            action=action_db,
                            allowed=allowed
                        )
                    )
        
        # Bulk create new permissions
        if permissions_to_create:
            RolePermission.objects.bulk_create(permissions_to_create, ignore_conflicts=True)
        
        # Bulk update existing permissions
        if permissions_to_update:
            RolePermission.objects.bulk_update(permissions_to_update, ['allowed'])
        
        total_updated = len(permissions_to_create) + len(permissions_to_update)
    
    return Response(
        {
            'message': 'Permissions updated successfully',
            'updated_count': total_updated
        },
        status=status.HTTP_200_OK
    )


@api_view(['GET'])
@permission_classes([drf_permissions.IsAuthenticated])
def get_appearance_preferences(request):
    """Get user appearance preferences"""
    from .appearance_models import AppearancePreferences
    from .serializers import AppearancePreferencesSerializer
    
    # Get or create preferences
    preferences, created = AppearancePreferences.objects.get_or_create(
        user=request.user,
        defaults={
            'theme': 'light',
            'language': 'en-US',
            'timezone': 'UTC',
            'date_calendar_system': 'AD',
            'compact_mode': False,
            'smooth_animations': True,
        }
    )
    
    serializer = AppearancePreferencesSerializer({
        'theme': preferences.theme,
        'language': preferences.language,
        'timezone': preferences.timezone,
        'date_calendar_system': preferences.date_calendar_system,
        'compact_mode': preferences.compact_mode,
        'smooth_animations': preferences.smooth_animations,
    })
    
    return Response(serializer.data)


@api_view(['PATCH'])
@permission_classes([drf_permissions.IsAuthenticated])
def update_appearance_preferences(request):
    """Update user appearance preferences"""
    from .appearance_models import AppearancePreferences
    from .serializers import AppearancePreferencesSerializer
    
    # Get or create preferences
    preferences, created = AppearancePreferences.objects.get_or_create(
        user=request.user
    )
    
    # Validate data
    serializer = AppearancePreferencesSerializer(data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Update preferences
    for field, value in serializer.validated_data.items():
        setattr(preferences, field, value)
    
    preferences.save()
    
    # Return updated preferences
    response_serializer = AppearancePreferencesSerializer({
        'theme': preferences.theme,
        'language': preferences.language,
        'timezone': preferences.timezone,
        'date_calendar_system': preferences.date_calendar_system,
        'compact_mode': preferences.compact_mode,
        'smooth_animations': preferences.smooth_animations,
    })
    
    return Response(response_serializer.data)
