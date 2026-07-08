from rest_framework import generics, permissions, viewsets, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.utils import extend_schema, extend_schema_view
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import models
from .models import User, AuditLog
from .notification_models import NotificationPreferences
from .notification_utils import get_or_create_notification_preferences, preferences_payload
from .serializers import (
    UserSerializer, RegisterSerializer, CustomTokenObtainPairSerializer, 
    AuditLogSerializer, UserProfileUpdateSerializer, PasswordChangeSerializer,
    NotificationPreferencesSerializer, SessionSerializer, PrivacyPreferencesSerializer,
    AccountDeleteSerializer, GoogleAuthSerializer,
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


class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get('refresh')
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200 and refresh_token:
            try:
                from .session_utils import get_refresh_jti, touch_user_session
                touch_user_session(get_refresh_jti(refresh_token))
            except Exception:
                pass
        return response


@extend_schema(
    tags=['Authentication'],
    summary='Google OAuth configuration',
    description='Public config for Google sign-in button (client ID when enabled).',
)
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def google_oauth_config(request):
    from users.google_auth import get_google_oauth_config
    return Response(get_google_oauth_config())


@extend_schema(
    tags=['Authentication'],
    summary='Sign in with Google',
    description='Exchange a Google ID token for JWT access and refresh tokens.',
    request=GoogleAuthSerializer,
)
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def google_login(request):
    serializer = GoogleAuthSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    return Response(serializer.validated_data, status=status.HTTP_200_OK)


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
        from billing.account_limits import assert_tenant_can_add_user
        assert_tenant_can_add_user(self.request.user.tenant)
        serializer.save(tenant=self.request.user.tenant)

    def perform_update(self, serializer):
        """Protect Super Admin; prevent self-disable; otherwise apply updates."""
        from rest_framework.exceptions import ValidationError
        from tenants.utils import get_request_tenant, is_tenant_super_admin

        instance = self.get_object()
        tenant = get_request_tenant(self.request.user)
        next_active = serializer.validated_data.get('is_active', None)
        next_role = serializer.validated_data.get('role', None)

        if tenant and is_tenant_super_admin(instance, tenant):
            if next_active is not None:
                raise ValidationError({
                    'detail': 'No one can enable or disable the Super Admin.'
                })
            if next_role is not None:
                raise ValidationError({
                    'detail': 'No one can change the Super Admin role.'
                })

        if (
            instance.id == self.request.user.id
            and next_active is False
        ):
            raise ValidationError({'detail': 'You cannot disable your own access to this organization.'})
        serializer.save()
    
    def perform_destroy(self, instance):
        """Remove user from the current organization without deleting their account."""
        from rest_framework.exceptions import ValidationError
        from tenants.membership_models import UserTenantMembership
        from tenants.utils import get_request_tenant, is_tenant_super_admin

        tenant = get_request_tenant(self.request.user)
        if not tenant:
            raise ValidationError({'detail': 'You must be assigned to an organization to remove users.'})

        if instance.id == self.request.user.id:
            raise ValidationError({'detail': 'You cannot remove yourself from the organization.'})

        if is_tenant_super_admin(instance, tenant):
            raise ValidationError({
                'detail': 'The Super Admin who created this business cannot be removed.'
            })

        UserTenantMembership.objects.filter(user=instance, tenant=tenant).delete()

        if instance.tenant_id == tenant.id:
            other_membership = (
                UserTenantMembership.objects.filter(user=instance, is_active=True)
                .select_related('tenant')
                .first()
            )
            if other_membership:
                instance.tenant = other_membership.tenant
                instance.role = other_membership.role
            else:
                instance.tenant = None
                instance.role = 'viewer'
            instance.save(update_fields=['tenant', 'role'])
    
    def get_permissions(self):
        """Settings edit permission required to create/update/remove users"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), CanEditTenantSettings()]
        return super().get_permissions()


@extend_schema(
    tags=['Users'],
    summary='Employee options for user invitations',
    description='Returns active HR employees for auto-filling invite forms. Requires Settings edit permission.',
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_employee_invite_options(request):
    """Minimal employee list for the settings > users invite flow."""
    from users.dynamic_permissions import has_permission, tenant_has_active_module

    tenant = request.user.tenant
    if not tenant:
        return Response({'results': []})

    active_modules = tenant.active_modules or []
    if not tenant_has_active_module(tenant, 'hr'):
        return Response({'results': []})

    if (
        not has_permission(request.user, 'settings', 'edit')
        and not has_permission(request.user, 'hr', 'invite')
    ):
        return Response(
            {'detail': 'You do not have permission to manage users.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    from hr.models import Employee

    employees = (
        Employee.objects.filter(tenant=tenant, status='active')
        .order_by('name')
        .values('id', 'name', 'email', 'designation')
    )
    return Response({
        'results': [
            {
                'id': str(emp['id']),
                'name': emp['name'],
                'email': emp['email'] or '',
                'designation': emp['designation'] or '',
            }
            for emp in employees
        ],
    })



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
from .permission_models import RolePermission, get_default_permissions, initialize_tenant_permissions, sync_tenant_permissions
from .serializers import PermissionsMatrixSerializer, UpdatePermissionsSerializer
from .permissions import IsAdminOrManager, CanEditTenantSettings, CanConfigurePermissions
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
    'hardware': 'Hardware',
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
    'invite': 'Invite',
    'assign': 'Assign',
    'configure': 'Configure',
}


def get_effective_role(user, tenant):
    from tenants.membership_models import UserTenantMembership
    if tenant and tenant.created_by_id == getattr(user, 'id', None):
        return 'admin'
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
    prefs = get_or_create_notification_preferences(request.user)
    serializer = NotificationPreferencesSerializer(preferences_payload(prefs))
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
    prefs = get_or_create_notification_preferences(request.user)

    serializer = NotificationPreferencesSerializer(data=request.data, partial=True)

    if serializer.is_valid():
        for key, value in serializer.validated_data.items():
            setattr(prefs, key, value)
        prefs.save()

        response = NotificationPreferencesSerializer(preferences_payload(prefs))
        return Response(response.data, status=status.HTTP_200_OK)

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
    """Get active sessions for the authenticated user."""
    from .session_models import UserSession

    current_session_id = request.headers.get('X-Session-Id')
    sessions = UserSession.objects.filter(user=request.user, is_revoked=False)

    payload = [
        {
            'id': str(session.id),
            'device': session.device,
            'location': session.location,
            'ip_address': session.ip_address or 'Unknown',
            'last_active': session.last_active,
            'is_current': str(session.id) == current_session_id if current_session_id else False,
        }
        for session in sessions
    ]

    if payload and not any(item['is_current'] for item in payload):
        payload[0]['is_current'] = True

    serializer = SessionSerializer(payload, many=True)
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
    """Revoke a specific session."""
    from .session_models import UserSession
    from .session_utils import revoke_user_session

    session = UserSession.objects.filter(id=session_id, user=request.user, is_revoked=False).first()
    if not session:
        return Response({'detail': 'Session not found'}, status=status.HTTP_404_NOT_FOUND)

    current_session_id = request.headers.get('X-Session-Id')
    if current_session_id and str(session.id) == current_session_id:
        return Response({'detail': 'Cannot revoke the current session'}, status=status.HTTP_400_BAD_REQUEST)

    revoke_user_session(session)
    return Response({'message': 'Session revoked successfully'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([drf_permissions.IsAuthenticated])
def revoke_other_sessions(request):
    """Revoke all sessions except the current one."""
    from .session_models import UserSession
    from .session_utils import revoke_user_session

    current_session_id = request.headers.get('X-Session-Id')
    sessions = UserSession.objects.filter(user=request.user, is_revoked=False)
    if current_session_id:
        sessions = sessions.exclude(id=current_session_id)

    revoked = 0
    for session in sessions:
        revoke_user_session(session)
        revoked += 1

    return Response({'message': f'Revoked {revoked} session(s)', 'revoked': revoked}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([drf_permissions.IsAuthenticated])
def get_privacy_preferences(request):
    from .privacy_models import PrivacyPreferences

    prefs, _ = PrivacyPreferences.objects.get_or_create(user=request.user)
    serializer = PrivacyPreferencesSerializer({
        'profile_visibility': prefs.profile_visibility,
        'activity_status': prefs.activity_status,
        'search_indexing': prefs.search_indexing,
        'data_retention_years': prefs.data_retention_years,
    })
    return Response(serializer.data)


@api_view(['PATCH'])
@permission_classes([drf_permissions.IsAuthenticated])
def update_privacy_preferences(request):
    from .privacy_models import PrivacyPreferences

    prefs, _ = PrivacyPreferences.objects.get_or_create(user=request.user)
    serializer = PrivacyPreferencesSerializer(data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    for field, value in serializer.validated_data.items():
        setattr(prefs, field, value)
    prefs.save()

    response = PrivacyPreferencesSerializer({
        'profile_visibility': prefs.profile_visibility,
        'activity_status': prefs.activity_status,
        'search_indexing': prefs.search_indexing,
        'data_retention_years': prefs.data_retention_years,
    })
    return Response(response.data)


@api_view(['GET'])
@permission_classes([drf_permissions.IsAuthenticated])
def export_user_data(request):
    from .appearance_models import AppearancePreferences
    from .privacy_models import PrivacyPreferences

    user = request.user
    notification_prefs, _ = NotificationPreferences.objects.get_or_create(user=user)
    appearance_prefs, _ = AppearancePreferences.objects.get_or_create(user=user)
    privacy_prefs, _ = PrivacyPreferences.objects.get_or_create(user=user)

    payload = {
        'profile': UserSerializer(user, context={'request': request}).data,
        'notification_preferences': NotificationPreferencesSerializer({
            'email_order_updates': notification_prefs.email_order_updates,
            'email_payment_reminders': notification_prefs.email_payment_reminders,
            'email_inventory_alerts': notification_prefs.email_inventory_alerts,
            'email_team_activity': notification_prefs.email_team_activity,
            'push_desktop': notification_prefs.push_desktop,
            'push_mobile': notification_prefs.push_mobile,
            'push_sound': notification_prefs.push_sound,
            'login_alerts': notification_prefs.login_alerts,
            'security_log_exports': notification_prefs.security_log_exports,
        }).data,
        'appearance_preferences': {
            'theme': appearance_prefs.theme,
            'language': appearance_prefs.language,
            'timezone': appearance_prefs.timezone,
            'date_calendar_system': appearance_prefs.date_calendar_system,
            'compact_mode': appearance_prefs.compact_mode,
            'smooth_animations': appearance_prefs.smooth_animations,
        },
        'privacy_preferences': PrivacyPreferencesSerializer({
            'profile_visibility': privacy_prefs.profile_visibility,
            'activity_status': privacy_prefs.activity_status,
            'search_indexing': privacy_prefs.search_indexing,
            'data_retention_years': privacy_prefs.data_retention_years,
        }).data,
    }

    response = Response(payload)
    response['Content-Disposition'] = 'attachment; filename="khata-user-export.json"'
    return response


@api_view(['POST'])
@permission_classes([drf_permissions.IsAuthenticated])
def ensure_current_session(request):
    """Ensure the client has a trackable session id."""
    from .session_models import UserSession
    from .session_utils import parse_device, get_client_ip, resolve_location

    current_session_id = request.headers.get('X-Session-Id')
    if current_session_id:
        session = UserSession.objects.filter(
            id=current_session_id,
            user=request.user,
            is_revoked=False,
        ).first()
        if session:
            return Response({'session_id': str(session.id)})

    user_agent = request.META.get('HTTP_USER_AGENT', '')
    ip_address = get_client_ip(request)
    import uuid
    session = UserSession.objects.create(
        user=request.user,
        refresh_jti=f'local-{uuid.uuid4()}',
        device=parse_device(user_agent),
        ip_address=ip_address,
        location=resolve_location(ip_address),
        user_agent=user_agent,
    )
    return Response({'session_id': str(session.id)}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([drf_permissions.IsAuthenticated])
def delete_account(request):
    serializer = AccountDeleteSerializer(data=request.data, context={'request': request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = request.user
    user.is_active = False
    user.save(update_fields=['is_active'])

    from .session_models import UserSession
    from .session_utils import revoke_user_session
    for session in UserSession.objects.filter(user=user, is_revoked=False):
        revoke_user_session(session)

    return Response({'message': 'Account deactivated successfully'}, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Permissions'],
    summary='Get role permissions matrix',
    description='Get the complete permissions matrix for all roles in the current tenant.',
    responses={200: PermissionsMatrixSerializer}
)
@api_view(['GET'])
@permission_classes([drf_permissions.IsAuthenticated, CanConfigurePermissions])
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
    permissions = RolePermission._base_manager.filter(tenant=tenant)
    
    # If no permissions exist, initialize with defaults
    if not permissions.exists():
        initialize_tenant_permissions(tenant)
    else:
        sync_tenant_permissions(tenant)
    permissions = RolePermission._base_manager.filter(tenant=tenant)
    
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
    permissions = RolePermission._base_manager.filter(tenant=tenant, role=role)
    if not permissions.exists():
        initialize_tenant_permissions(tenant)
    else:
        sync_tenant_permissions(tenant)
    permissions = RolePermission._base_manager.filter(tenant=tenant, role=role)

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
@permission_classes([drf_permissions.IsAuthenticated, CanConfigurePermissions])
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
        'Hardware': 'hardware',
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
        'Invite': 'invite',
        'Assign': 'assign',
        'Configure': 'configure',
    }
    
    import time
    from django.db import OperationalError

    # Avoid select_for_update — SQLite often raises "database is locked" under concurrent reads.
    max_attempts = 3
    total_updated = 0
    last_error = None

    for attempt in range(max_attempts):
        try:
            with transaction.atomic():
                existing_perms = {
                    (p.role, p.module, p.action): p
                    for p in RolePermission._base_manager.filter(tenant=tenant)
                }

                permissions_to_create = []
                permissions_to_update = []

                for role_display, perms in serializer.validated_data.items():
                    role_db = role_map.get(role_display)
                    if not role_db:
                        continue

                    for key, allowed in perms.items():
                        if '-' not in key:
                            continue
                        module_display, action_display = key.rsplit('-', 1)
                        module_db = module_map.get(module_display)
                        action_db = action_map.get(action_display)

                        if not module_db or not action_db:
                            continue

                        perm_key = (role_db, module_db, action_db)

                        if perm_key in existing_perms:
                            perm = existing_perms[perm_key]
                            if perm.allowed != allowed:
                                perm.allowed = allowed
                                permissions_to_update.append(perm)
                        else:
                            permissions_to_create.append(
                                RolePermission(
                                    tenant=tenant,
                                    role=role_db,
                                    module=module_db,
                                    action=action_db,
                                    allowed=allowed,
                                )
                            )

                if permissions_to_create:
                    RolePermission._base_manager.bulk_create(
                        permissions_to_create, ignore_conflicts=True
                    )

                if permissions_to_update:
                    RolePermission._base_manager.bulk_update(
                        permissions_to_update, ['allowed']
                    )

                total_updated = len(permissions_to_create) + len(permissions_to_update)
            break
        except OperationalError as exc:
            last_error = exc
            if 'locked' not in str(exc).lower() or attempt == max_attempts - 1:
                raise
            time.sleep(0.15 * (attempt + 1))
    else:
        if last_error:
            raise last_error

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


from rest_framework.decorators import action
from .notification_models import Notification
from .serializers import NotificationSerializer


@extend_schema_view(
    list=extend_schema(tags=['Notifications'], summary='List user notifications'),
    retrieve=extend_schema(tags=['Notifications'], summary='Get notification'),
)
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Notification.objects.filter(tenant=user.tenant, user=user)
        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            qs = qs.filter(is_read=is_read.lower() in ('true', '1'))
        return qs

    @extend_schema(tags=['Notifications'], summary='Mark notification as read')
    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.mark_as_read()
        return Response(NotificationSerializer(notification).data)

    @extend_schema(tags=['Notifications'], summary='Mark all notifications as read')
    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        from django.utils import timezone
        updated = Notification.objects.filter(
            tenant=request.user.tenant,
            user=request.user,
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())
        return Response({'updated': updated})
