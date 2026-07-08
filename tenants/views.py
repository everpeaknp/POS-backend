from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db.models import Q
from .models import Tenant
from .invitation_models import OrganizationInvitation
from .serializers import TenantSerializer, TenantProfileSerializer, TenantCreateSerializer, OrganizationInvitationSerializer, InvitationResponseSerializer


class TenantViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing tenants
    """
    CORE_MODULES = {'accounting', 'settings', 'dashboard'}

    def _user_is_tenant_admin(self, user, tenant):
        from .membership_models import UserTenantMembership

        membership = UserTenantMembership.objects.filter(user=user, tenant=tenant).first()
        return (
            tenant.created_by_id == user.id
            or (membership and membership.role == 'admin')
            or user.role == 'admin'
        )

    def _validate_module_name(self, module_name):
        from core_backend.platform_constants import AVAILABLE_MODULES

        allowed = {module for module, _ in AVAILABLE_MODULES}
        normalized = (module_name or '').strip().lower()
        if normalized not in allowed:
            return None
        return normalized

    def get_queryset(self):
        """
        Filter tenants - authenticated users see all tenants they are members of
        
        Users can see tenants where they:
        1. Have membership (any role)
        2. Are the creator
        
        Note: We now include tenants created from registration if user is creator/member
        """
        if self.request.user.is_authenticated:
            # Import here to avoid circular import
            from .membership_models import UserTenantMembership
            
            # Get all tenant IDs where user has an active membership (enabled business access)
            membership_tenant_ids = list(UserTenantMembership.objects.filter(
                user=self.request.user,
                is_active=True,
            ).values_list('tenant_id', flat=True))
            
            # Return tenants where user has membership OR is the creator
            from django.db.models import Q
            
            # Build query: has membership OR is creator
            # We now allow registration tenants if user is creator/member
            query = Q(id__in=membership_tenant_ids) | Q(created_by=self.request.user)
            
            return Tenant.objects.filter(query).distinct()
        # For unauthenticated users (for create action), return none
        return Tenant.objects.none()
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'slug'
    
    def get_permissions(self):
        """Allow unauthenticated access to create action only"""
        if self.action == 'create':
            return [AllowAny()]
        return super().get_permissions()
    
    def get_serializer_class(self):
        """Use different serializer for create action"""
        if self.action == 'create':
            return TenantCreateSerializer
        return super().get_serializer_class()

    ALLOWED_TENANT_UPDATE_FIELDS = [
        'name', 'business_type', 'owner_name', 'email', 'phone', 'address',
        'pan_vat_number', 'website', 'workspace_name',
        'accounting_start_date', 'vat_registered', 'logo',
    ]

    def update(self, request, *args, **kwargs):
        return self._restricted_tenant_update(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._restricted_tenant_update(request, partial=True)

    def _restricted_tenant_update(self, request, partial):
        from rest_framework.exceptions import PermissionDenied

        tenant = self.get_object()
        if not self._user_is_tenant_admin(request.user, tenant):
            raise PermissionDenied('Only organization admins can update organization settings')

        update_data = {
            k: v for k, v in request.data.items() if k in self.ALLOWED_TENANT_UPDATE_FIELDS
        }
        serializer = self.get_serializer(tenant, data=update_data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    def perform_create(self, serializer):
        """Associate the created tenant with the current user if authenticated"""
        # Import here to avoid circular import
        from .membership_models import UserTenantMembership
        from users.permission_models import initialize_tenant_permissions
        from billing.services import ensure_subscription
        from billing.account_limits import assert_user_can_create_org

        if self.request.user.is_authenticated:
            assert_user_can_create_org(self.request.user)
        
        # Save tenant with created_by field and created_from_registration=False
        tenant = serializer.save(
            created_by=self.request.user if self.request.user.is_authenticated else None,
            created_from_registration=False  # Explicitly created tenant
        )

        ensure_subscription(tenant)
        
        # Initialize default permissions for the new tenant
        initialize_tenant_permissions(tenant)

        # Seed standard chart of accounts when accounting module is enabled
        active_modules = tenant.active_modules or []
        if 'accounting' in active_modules:
            try:
                from accounting.chart_seed import seed_default_chart_of_accounts
                seed_default_chart_of_accounts(tenant)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    'Failed to seed chart of accounts for tenant %s', tenant.id
                )
        
        # If user is authenticated, assign this tenant as their active tenant
        if self.request.user.is_authenticated:
            self.request.user.tenant = tenant
            # Make them admin of their organization if they don't have a role yet
            if not self.request.user.role or self.request.user.role == 'viewer':
                self.request.user.role = 'admin'
            self.request.user.save()
            
            # Create membership record
            UserTenantMembership.objects.create(
                user=self.request.user,
                tenant=tenant,
                role='admin'
            )
        
        return tenant
    
    def perform_destroy(self, instance):
        """
        Delete tenant and handle cleanup.
        Only the Super Admin (business card creator) can delete it.
        """
        from rest_framework.exceptions import PermissionDenied, ValidationError
        from .deletion import delete_tenant
        from .utils import is_tenant_super_admin
        
        if not self.request.user or not self.request.user.is_authenticated:
            raise PermissionDenied("Authentication required")

        if not is_tenant_super_admin(self.request.user, instance):
            raise PermissionDenied(
                "Only the Super Admin who created this business can delete it"
            )

        try:
            delete_tenant(instance)
        except Exception as exc:
            raise ValidationError(
                {"detail": "Could not delete organization because related records still exist. "
                           "Remove transactions and try again, or contact support."}
            ) from exc
    
    @extend_schema(
        summary='Get tenant profile by slug',
        description='Retrieve tenant profile information using the tenant slug. This endpoint is used for workspace routing.',
        parameters=[
            OpenApiParameter(
                name='slug',
                description='Tenant slug',
                required=True,
                type=str,
                location=OpenApiParameter.QUERY
            )
        ],
        responses={200: TenantProfileSerializer}
    )
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def profile(self, request):
        """Get tenant profile by slug"""
        slug = request.query_params.get('slug')
        
        if not slug:
            return Response(
                {'error': 'Slug parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            tenant = Tenant.objects.get(slug=slug, is_active=True)
        except Tenant.DoesNotExist:
            return Response(
                {'error': 'Tenant not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Verify user has access to this tenant
        if request.user.tenant != tenant:
            return Response(
                {'error': 'You do not have access to this workspace'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = TenantProfileSerializer(tenant)
        return Response(serializer.data)

    @extend_schema(
        summary='Switch active organization',
        description='Set the authenticated user\'s active tenant to this organization (must be a member or creator).',
    )
    @action(detail=True, methods=['post'])
    def switch(self, request, slug=None):
        """Switch the user's active tenant context."""
        from tenants.utils import user_has_tenant_access
        from django.contrib.auth import get_user_model
        from .membership_models import UserTenantMembership

        tenant = self.get_object()
        user = request.user

        if not user_has_tenant_access(user, tenant):
            return Response(
                {'error': 'You do not have access to this organization'},
                status=status.HTTP_403_FORBIDDEN,
            )

        User = get_user_model()
        updates = {'tenant': tenant}
        membership = UserTenantMembership.objects.filter(user=user, tenant=tenant).first()
        if membership:
            if not membership.is_active:
                return Response(
                    {'error': 'Your access to this organization has been disabled'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            updates['role'] = membership.role
        elif tenant.created_by_id == user.id:
            updates['role'] = 'admin'

        User.objects.filter(pk=user.pk).update(**updates)
        user.refresh_from_db()

        serializer = TenantProfileSerializer(tenant)
        return Response({
            'message': f'Switched to {tenant.name}',
            'tenant': serializer.data,
        })
    
    @extend_schema(
        summary='Activate a module for tenant',
        description='Activate a specific module for the tenant',
    )
    @action(detail=True, methods=['post'])
    def activate_module(self, request, slug=None):
        """Activate a module for this tenant"""
        from rest_framework.exceptions import PermissionDenied

        tenant = self.get_object()
        if not self._user_is_tenant_admin(request.user, tenant):
            raise PermissionDenied('Only organization admins can manage modules')

        module_name = self._validate_module_name(request.data.get('module_name'))
        if not module_name:
            return Response(
                {'error': 'A valid module_name is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from billing.account_limits import assert_tenant_can_enable_module

        try:
            assert_tenant_can_enable_module(tenant, module_name)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        tenant.activate_module(module_name)
        serializer = self.get_serializer(tenant)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Deactivate a module for tenant',
        description='Deactivate a specific module for the tenant',
    )
    @action(detail=True, methods=['post'])
    def deactivate_module(self, request, slug=None):
        """Deactivate a module for this tenant"""
        from rest_framework.exceptions import PermissionDenied

        tenant = self.get_object()
        if not self._user_is_tenant_admin(request.user, tenant):
            raise PermissionDenied('Only organization admins can manage modules')

        module_name = self._validate_module_name(request.data.get('module_name'))
        if not module_name:
            return Response(
                {'error': 'A valid module_name is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if module_name in self.CORE_MODULES:
            return Response(
                {'error': f'{module_name.title()} is a core module and cannot be disabled'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant.deactivate_module(module_name)
        serializer = self.get_serializer(tenant)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Get current tenant settings',
        description='Get settings for the currently active tenant',
    )
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current tenant settings"""
        if not request.user.tenant:
            return Response(
                {'error': 'No active tenant found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.get_serializer(request.user.tenant)
        return Response(serializer.data)
    
    @extend_schema(
        summary='Update current tenant settings',
        description='Update settings for the currently active tenant',
    )
    @action(detail=False, methods=['patch'])
    def update_current(self, request):
        """Update current tenant settings"""
        if not request.user.tenant:
            return Response(
                {'error': 'No active tenant found'},
                status=status.HTTP_404_NOT_FOUND
            )

        tenant = request.user.tenant
        from .membership_models import UserTenantMembership
        from rest_framework.exceptions import PermissionDenied

        membership = UserTenantMembership.objects.filter(
            user=request.user, tenant=tenant
        ).first()
        is_admin = (
            tenant.created_by_id == request.user.id
            or (membership and membership.role == 'admin')
            or request.user.role == 'admin'
        )
        if not is_admin:
            raise PermissionDenied('Only organization admins can update settings')

        allowed_fields = [
            'name', 'business_type', 'owner_name', 'email', 'phone', 'address',
            'pan_vat_number', 'website', 'workspace_name',
            'accounting_start_date', 'vat_registered', 'logo',
        ]
        update_data = {k: v for k, v in request.data.items() if k in allowed_fields}

        serializer = self.get_serializer(tenant, data=update_data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)



@extend_schema(tags=['Organization Invitations'])
class OrganizationInvitationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing organization invitations
    """
    serializer_class = OrganizationInvitationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Invitations received by the user (by account or email) plus org-sent for admins."""
        user = self.request.user
        email = (user.email or '').strip().lower()

        received = OrganizationInvitation.objects.filter(
            Q(invited_user=user) | Q(invited_email__iexact=email)
        )

        if user.tenant and user.is_admin:
            sent = OrganizationInvitation.objects.filter(tenant=user.tenant)
            return (received | sent).distinct()

        return received.distinct()

    def perform_create(self, serializer):
        """Create invitation — requires settings edit permission."""
        from rest_framework.exceptions import PermissionDenied
        from users.dynamic_permissions import has_permission

        user = self.request.user

        if not user.tenant:
            raise PermissionDenied("You must be part of an organization to invite users")

        if not has_permission(user, 'settings', 'edit') and not has_permission(user, 'hr', 'invite'):
            raise PermissionDenied("You do not have permission to invite users")

        serializer.save(tenant=user.tenant, invited_by=user)

    @extend_schema(
        request=InvitationResponseSerializer,
        responses={200: OrganizationInvitationSerializer}
    )
    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        """Accept or decline an invitation"""
        invitation = self.get_object()
        user = request.user
        email = (user.email or '').strip().lower()
        invited_email = (invitation.invited_email or '').strip().lower()

        is_recipient = (
            invitation.invited_user_id == user.id
            or (invited_email and invited_email == email)
        )
        if not is_recipient:
            return Response(
                {'error': 'You can only respond to your own invitations'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = InvitationResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action_type = serializer.validated_data['action']

        try:
            if action_type == 'accept':
                invitation.accept(user=user)
                message = f'You have joined {invitation.tenant.name} as {invitation.get_role_display()}'
            else:
                invitation.decline(user=user)
                message = 'Invitation declined'

            return Response({
                'message': message,
                'invitation': OrganizationInvitationSerializer(invitation).data
            })

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an invitation (by inviter or anyone with settings edit)."""
        from users.dynamic_permissions import has_permission

        invitation = self.get_object()

        if not request.user.tenant or request.user.tenant != invitation.tenant:
            return Response(
                {'error': 'You can only cancel invitations from your organization'},
                status=status.HTTP_403_FORBIDDEN
            )

        if (
            not has_permission(request.user, 'settings', 'edit')
            and not has_permission(request.user, 'hr', 'invite')
        ):
            return Response(
                {'error': 'You do not have permission to cancel invitations'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            invitation.cancel()
            return Response({
                'message': 'Invitation cancelled',
                'invitation': OrganizationInvitationSerializer(invitation).data
            })
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'])
    def received(self, request):
        """Get invitations received by the current user (by account or email)."""
        email = (request.user.email or '').strip().lower()
        invitations = OrganizationInvitation.objects.filter(
            status='pending',
        ).filter(
            Q(invited_user=request.user) | Q(invited_email__iexact=email)
        ).distinct()
        serializer = self.get_serializer(invitations, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def sent(self, request):
        """Get invitations sent by the user's active organization."""
        from users.dynamic_permissions import has_permission

        tenant = request.user.tenant
        if tenant and (
            has_permission(request.user, 'settings', 'edit')
            or has_permission(request.user, 'hr', 'invite')
        ):
            invitations = OrganizationInvitation.objects.filter(tenant=tenant)
            serializer = self.get_serializer(invitations, many=True)
            return Response(serializer.data)

        from .membership_models import UserTenantMembership

        admin_manager_memberships = UserTenantMembership.objects.filter(
            user=request.user,
            role__in=['admin', 'manager'],
        ).values_list('tenant_id', flat=True)

        if not admin_manager_memberships:
            return Response([])

        invitations = OrganizationInvitation.objects.filter(
            tenant_id__in=admin_manager_memberships
        )
        serializer = self.get_serializer(invitations, many=True)
        return Response(serializer.data)


def _public_invitation_payload(invitation):
    return {
        'token': str(invitation.token),
        'tenant_name': invitation.tenant.name,
        'role': invitation.role,
        'role_display': invitation.get_role_display(),
        'invited_email': invitation.recipient_email,
        'invited_by_name': (
            invitation.invited_by.get_full_name()
            if invitation.invited_by
            else 'A team member'
        ),
        'message': invitation.message,
        'expires_at': invitation.expires_at,
        'is_expired': invitation.is_expired,
        'status': invitation.status,
        'requires_signup': invitation.invited_user_id is None,
    }


@extend_schema(
    tags=['Organization Invitations'],
    summary='Preview invitation by token',
    description='Public endpoint to load invite details before signup or login.',
)
@api_view(['GET'])
@permission_classes([AllowAny])
def preview_invitation(request, token):
    invitation = OrganizationInvitation.objects.select_related(
        'tenant', 'invited_by', 'invited_user'
    ).filter(token=token).first()

    if not invitation:
        return Response({'detail': 'Invitation not found'}, status=status.HTTP_404_NOT_FOUND)

    if invitation.is_expired and invitation.status == 'pending':
        invitation.status = 'expired'
        invitation.save(update_fields=['status', 'updated_at'])

    return Response(_public_invitation_payload(invitation))


@extend_schema(
    tags=['Organization Invitations'],
    summary='Accept invitation by token',
    description='Authenticated users accept an invite via the email token.',
    request=None,
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def accept_invitation_by_token(request, token):
    invitation = OrganizationInvitation.objects.select_related(
        'tenant', 'invited_by', 'invited_user'
    ).filter(token=token).first()

    if not invitation:
        return Response({'detail': 'Invitation not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        invitation.accept(user=request.user)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        'message': f'You have joined {invitation.tenant.name} as {invitation.get_role_display()}',
        'invitation': OrganizationInvitationSerializer(invitation).data,
        'tenant_slug': invitation.tenant.slug,
    })
