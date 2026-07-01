from rest_framework import serializers
from .models import Tenant
from .invitation_models import OrganizationInvitation
from users.models import User


class TenantSerializer(serializers.ModelSerializer):
    """Serializer for Tenant model"""
    user_role = serializers.SerializerMethodField()
    
    class Meta:
        model = Tenant
        fields = [
            'id', 'name', 'slug', 'business_type', 'owner_name', 'email',
            'phone', 'address', 'pan_vat_number', 'website',
            'accounting_start_date', 'vat_registered',
            'workspace_name', 'logo', 'is_active', 'plan_type', 'active_modules',
            'created_at', 'updated_at', 'created_by', 'user_role'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at', 'created_by', 'user_role']
    
    def get_user_role(self, obj):
        """Get the current user's role in this specific tenant"""
        request = self.context.get('request')
        if not request or not request.user:
            return None
        
        user = request.user
        
        # Check if user is the creator/owner
        if obj.created_by == user:
            return 'admin'
        
        # Check UserTenantMembership for role in this tenant
        from .membership_models import UserTenantMembership
        try:
            membership = UserTenantMembership.objects.get(user=user, tenant=obj)
            return membership.role
        except UserTenantMembership.DoesNotExist:
            # Fallback to user's primary role if they're in this tenant
            if user.tenant == obj:
                return user.role
            return None


class TenantCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new tenant"""
    
    # Include read-only fields in response
    id = serializers.IntegerField(read_only=True)
    slug = serializers.SlugField(read_only=True)
    
    class Meta:
        model = Tenant
        fields = [
            'id', 'slug', 'name', 'business_type', 'owner_name', 'email',
            'phone', 'address', 'pan_vat_number', 'website',
            'accounting_start_date', 'vat_registered',
            'workspace_name', 'logo', 'active_modules'
        ]
        read_only_fields = ['id', 'slug']
    
    def validate_name(self, value):
        """Ensure tenant name is unique"""
        if Tenant.objects.filter(name=value).exists():
            raise serializers.ValidationError('An organization with this name already exists.')
        return value
    
    def create(self, validated_data):
        """Create tenant with default values"""
        # Set default modules if not provided
        if 'active_modules' not in validated_data or not validated_data['active_modules']:
            validated_data['active_modules'] = [
                'inventory', 'sales', 'purchase', 'accounting', 'reports'
            ]
        
        # Set default plan
        validated_data['plan_type'] = 'free'
        validated_data['is_active'] = True
        
        return super().create(validated_data)


class TenantProfileSerializer(serializers.ModelSerializer):
    """Serializer for public tenant profile (accessed by slug)"""
    
    class Meta:
        model = Tenant
        fields = [
            'id', 'name', 'slug', 'workspace_name', 'email', 'business_type', 'is_active',
            'plan_type', 'active_modules',
        ]
        read_only_fields = fields



class OrganizationInvitationSerializer(serializers.ModelSerializer):
    """Serializer for organization invitations"""
    invited_user_email = serializers.EmailField(write_only=True, required=False)
    invited_user_name = serializers.SerializerMethodField()
    invited_by_name = serializers.SerializerMethodField()
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    is_expired = serializers.ReadOnlyField()
    tenant = serializers.PrimaryKeyRelatedField(read_only=True)  # Set by viewset
    invited_user = serializers.PrimaryKeyRelatedField(read_only=True, required=False)  # Set by validation
    
    class Meta:
        model = OrganizationInvitation
        fields = [
            'id', 'tenant', 'tenant_name', 'invited_user', 'invited_user_email',
            'invited_user_name', 'invited_by', 'invited_by_name', 'role',
            'status', 'message', 'created_at', 'updated_at', 'expires_at',
            'responded_at', 'is_expired'
        ]
        read_only_fields = ['id', 'invited_by', 'status', 'created_at', 'updated_at', 'responded_at', 'expires_at']
    
    def get_invited_user_name(self, obj):
        """Get invited user's full name"""
        if obj.invited_user:
            return f"{obj.invited_user.first_name} {obj.invited_user.last_name}".strip() or obj.invited_user.username
        return None
    
    def get_invited_by_name(self, obj):
        """Get inviter's full name"""
        if obj.invited_by:
            return f"{obj.invited_by.first_name} {obj.invited_by.last_name}".strip() or obj.invited_by.username
        return None
    
    def validate(self, data):
        """Validate invitation data"""
        request = self.context.get('request')
        
        # Get invited user by email if provided
        if 'invited_user_email' in data:
            email = data.pop('invited_user_email')
            try:
                invited_user = User.objects.get(email=email)
                data['invited_user'] = invited_user
            except User.DoesNotExist:
                raise serializers.ValidationError({
                    'invited_user_email': 'No user found with this email address'
                })
        
        # Validate invited user exists
        if 'invited_user' not in data:
            raise serializers.ValidationError({
                'invited_user': 'Invited user is required'
            })
        
        invited_user = data['invited_user']
        
        # Get tenant from request user (set by viewset)
        request = self.context.get('request')
        tenant = request.user.tenant if request and request.user else None
        
        if not tenant:
            raise serializers.ValidationError({
                'tenant': 'You must be part of an organization to invite users'
            })
        
        # Check if user is already in this organization
        if invited_user.tenant == tenant:
            raise serializers.ValidationError({
                'invited_user': 'This user is already a member of this organization'
            })
        
        # Check if there's already a pending invitation
        existing = OrganizationInvitation.objects.filter(
            tenant=tenant,
            invited_user=invited_user,
            status='pending'
        ).exists()
        
        if existing:
            raise serializers.ValidationError({
                'invited_user': 'This user already has a pending invitation to this organization'
            })
        
        # Set invited_by from request user
        if request and request.user:
            data['invited_by'] = request.user
        
        return data


class InvitationResponseSerializer(serializers.Serializer):
    """Serializer for accepting/declining invitations"""
    action = serializers.ChoiceField(choices=['accept', 'decline'])
