from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .models import Tenant
from .invitation_models import OrganizationInvitation
from .serializers import TenantSerializer, TenantProfileSerializer, TenantCreateSerializer, OrganizationInvitationSerializer, InvitationResponseSerializer


class TenantViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing tenants
    """
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
            
            # Get all tenant IDs where user has membership
            membership_tenant_ids = list(UserTenantMembership.objects.filter(
                user=self.request.user
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
    
    def perform_create(self, serializer):
        """Associate the created tenant with the current user if authenticated"""
        # Import here to avoid circular import
        from .membership_models import UserTenantMembership
        from users.permission_models import initialize_tenant_permissions
        
        # Save tenant with created_by field and created_from_registration=False
        tenant = serializer.save(
            created_by=self.request.user if self.request.user.is_authenticated else None,
            created_from_registration=False  # Explicitly created tenant
        )
        
        # Initialize default permissions for the new tenant
        initialize_tenant_permissions(tenant)
        
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
        Delete tenant and handle cleanup
        - Only admins of the organization can delete it
        - Unassign all users from this tenant
        - Delete all related data (handled by CASCADE)
        """
        from django.contrib.auth import get_user_model
        from rest_framework.exceptions import PermissionDenied
        from .membership_models import UserTenantMembership
        
        User = get_user_model()
        
        # Verify user is authenticated
        if not self.request.user or not self.request.user.is_authenticated:
            raise PermissionDenied("Authentication required")
        
        # Check if user is admin of this organization through membership
        membership = UserTenantMembership.objects.filter(
            user=self.request.user,
            tenant=instance,
            role='admin'
        ).first()
        
        # Also check if user is the creator
        is_creator = instance.created_by == self.request.user
        
        if not membership and not is_creator:
            raise PermissionDenied("You must be an admin of this organization to delete it")
        
        # If user has membership but not admin role
        if membership and membership.role != 'admin' and not is_creator:
            raise PermissionDenied("Only organization admins can delete the organization")
        
        # Unassign all users who have this as their primary tenant
        users_count = User.objects.filter(tenant=instance).count()
        if users_count > 0:
            User.objects.filter(tenant=instance).update(tenant=None)
        
        # Delete all memberships for this tenant
        UserTenantMembership.objects.filter(tenant=instance).delete()
        
        # Delete the tenant (CASCADE will handle related objects)
        instance.delete()
    
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
        summary='Activate a module for tenant',
        description='Activate a specific module for the tenant',
    )
    @action(detail=True, methods=['post'])
    def activate_module(self, request, slug=None):
        """Activate a module for this tenant"""
        tenant = self.get_object()
        module_name = request.data.get('module_name')
        
        if not module_name:
            return Response(
                {'error': 'module_name is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
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
        tenant = self.get_object()
        module_name = request.data.get('module_name')
        
        if not module_name:
            return Response(
                {'error': 'module_name is required'},
                status=status.HTTP_400_BAD_REQUEST
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
        
        # Only allow certain fields to be updated
        allowed_fields = ['name', 'business_type', 'owner_name', 'email', 'phone', 'address']
        update_data = {k: v for k, v in request.data.items() if k in allowed_fields}
        
        serializer = self.get_serializer(request.user.tenant, data=update_data, partial=True)
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
        """
        Return invitations based on user role:
        - Invitations sent by user's organization (if user is admin)
        - Invitations received by the user
        """
        user = self.request.user
        
        # Get invitations received by this user
        received = OrganizationInvitation.objects.filter(invited_user=user)
        
        # If user is admin of an organization, also show invitations sent by their org
        if user.tenant and user.is_admin:
            sent = OrganizationInvitation.objects.filter(tenant=user.tenant)
            return (received | sent).distinct()
        
        return received
    
    def perform_create(self, serializer):
        """Create invitation - admins and managers can invite users"""
        user = self.request.user
        
        # Check if user is part of an organization
        if not user.tenant:
            raise PermissionError("You must be part of an organization to invite users")
        
        # Check if user is admin or manager
        if not (user.is_admin or user.is_manager):
            raise PermissionError("Only admins and managers can invite users to the organization")
        
        # Set tenant to user's primary organization
        serializer.save(tenant=user.tenant, invited_by=user)
    
    @extend_schema(
        request=InvitationResponseSerializer,
        responses={200: OrganizationInvitationSerializer}
    )
    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        """Accept or decline an invitation"""
        invitation = self.get_object()
        
        # Check if user is the invited user
        if invitation.invited_user != request.user:
            return Response(
                {'error': 'You can only respond to your own invitations'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = InvitationResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        action_type = serializer.validated_data['action']
        
        try:
            if action_type == 'accept':
                invitation.accept()
                message = f'You have joined {invitation.tenant.name} as {invitation.get_role_display()}'
            else:
                invitation.decline()
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
        """Cancel an invitation (by inviter/admin)"""
        invitation = self.get_object()
        
        # Check if user is admin of the organization
        if not request.user.tenant or request.user.tenant != invitation.tenant:
            return Response(
                {'error': 'You can only cancel invitations from your organization'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not request.user.is_admin:
            return Response(
                {'error': 'Only admins can cancel invitations'},
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
        """Get invitations received by the current user"""
        invitations = OrganizationInvitation.objects.filter(
            invited_user=request.user,
            status='pending'
        )
        serializer = self.get_serializer(invitations, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def sent(self, request):
        """Get invitations sent by organizations where user is admin or manager"""
        # Import here to avoid circular import
        from .membership_models import UserTenantMembership
        
        # Get all tenants where user is admin or manager
        admin_manager_memberships = UserTenantMembership.objects.filter(
            user=request.user,
            role__in=['admin', 'manager']
        ).values_list('tenant_id', flat=True)
        
        if not admin_manager_memberships:
            return Response([])
        
        # Get invitations from those tenants
        invitations = OrganizationInvitation.objects.filter(
            tenant_id__in=admin_manager_memberships
        )
        serializer = self.get_serializer(invitations, many=True)
        return Response(serializer.data)
