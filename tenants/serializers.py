from rest_framework import serializers
from .models import Tenant
from .invitation_models import OrganizationInvitation
from users.models import User
from billing.account_limits import (
    assert_modules_allowed_for_plan,
    assert_user_can_create_org,
    normalize_active_modules_for_plan,
)


class TenantSerializer(serializers.ModelSerializer):
    """Serializer for Tenant model"""
    user_role = serializers.SerializerMethodField()
    allowed_modules = serializers.SerializerMethodField()
    user_limits = serializers.SerializerMethodField()
    
    class Meta:
        model = Tenant
        fields = [
            'id', 'name', 'slug', 'business_type', 'owner_name', 'email',
            'phone', 'address', 'pan_vat_number', 'website',
            'accounting_start_date', 'vat_registered',
            'workspace_name', 'logo', 'is_active', 'plan_type', 'active_modules',
            'allowed_modules', 'user_limits',
            'created_at', 'updated_at', 'created_by', 'user_role'
        ]
        read_only_fields = [
            'id', 'slug', 'created_at', 'updated_at', 'created_by',
            'user_role', 'allowed_modules', 'user_limits',
        ]
    
    def get_user_role(self, obj):
        """Get the current user's role in this specific tenant"""
        request = self.context.get('request')
        if not request or not request.user:
            return None
        
        user = request.user
        
        # Creator of the business card is Super Admin (top-level owner)
        if obj.created_by_id == user.id:
            return 'super_admin'
        
        # Check UserTenantMembership for role in this tenant
        from .membership_models import UserTenantMembership
        try:
            membership = UserTenantMembership.objects.get(user=user, tenant=obj)
            if not membership.is_active:
                return None
            return membership.role
        except UserTenantMembership.DoesNotExist:
            # Fallback to user's primary role if they're in this tenant
            if user.tenant_id == obj.id:
                return user.role
            return None

    def get_allowed_modules(self, obj):
        from billing.account_limits import get_tenant_allowed_modules

        try:
            return get_tenant_allowed_modules(obj)
        except Exception:
            from billing.account_limits import get_allowed_modules_for_plan
            return get_allowed_modules_for_plan('free')

    def get_user_limits(self, obj):
        from billing.account_limits import get_tenant_user_limits

        try:
            return get_tenant_user_limits(obj)
        except Exception:
            return {
                'plan_code': 'free',
                'plan_name': 'Free',
                'max_users': 1,
                'current_users': 0,
                'pending_invites': 0,
                'seats_used': 0,
                'can_invite': True,
            }


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
    
    def validate(self, data):
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None

        if user and user.is_authenticated:
            assert_user_can_create_org(user)

        new_org_plan_code = 'free'
        modules = data.get('active_modules')
        if modules:
            assert_modules_allowed_for_plan(new_org_plan_code, modules)
            data['active_modules'] = normalize_active_modules_for_plan(new_org_plan_code, modules)
        else:
            data['active_modules'] = normalize_active_modules_for_plan(new_org_plan_code, None)

        return data

    def create(self, validated_data):
        """Create tenant with default values"""
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
    """Serializer for organization invitations (registered users or email-only)."""
    invited_user_email = serializers.EmailField(write_only=True, required=True)
    invited_email = serializers.EmailField(read_only=True)
    invited_user_name = serializers.SerializerMethodField()
    invited_by_name = serializers.SerializerMethodField()
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    is_expired = serializers.ReadOnlyField()
    requires_signup = serializers.SerializerMethodField()
    tenant = serializers.PrimaryKeyRelatedField(read_only=True)
    invited_user = serializers.PrimaryKeyRelatedField(read_only=True, required=False, allow_null=True)

    class Meta:
        model = OrganizationInvitation
        fields = [
            'id', 'token', 'tenant', 'tenant_name', 'invited_user', 'invited_user_email',
            'invited_email', 'invited_user_name', 'invited_by', 'invited_by_name', 'role',
            'status', 'message', 'created_at', 'updated_at', 'expires_at',
            'responded_at', 'is_expired', 'requires_signup',
        ]
        read_only_fields = [
            'id', 'token', 'invited_by', 'invited_email', 'status',
            'created_at', 'updated_at', 'responded_at', 'expires_at', 'requires_signup',
        ]

    def get_invited_user_name(self, obj):
        if obj.invited_user:
            return (
                f"{obj.invited_user.first_name} {obj.invited_user.last_name}".strip()
                or obj.invited_user.username
            )
        return obj.invited_email or None

    def get_invited_by_name(self, obj):
        if obj.invited_by:
            return (
                f"{obj.invited_by.first_name} {obj.invited_by.last_name}".strip()
                or obj.invited_by.username
            )
        return None

    def get_requires_signup(self, obj):
        return obj.invited_user_id is None and bool(obj.invited_email)

    def validate(self, data):
        request = self.context.get('request')
        email = (data.pop('invited_user_email', '') or '').strip().lower()
        if not email:
            raise serializers.ValidationError({
                'invited_user_email': 'Email address is required',
            })

        tenant = request.user.tenant if request and request.user else None
        if not tenant:
            raise serializers.ValidationError({
                'tenant': 'You must be part of an organization to invite users',
            })

        from tenants.membership_models import UserTenantMembership

        invited_user = User.objects.filter(email__iexact=email).first()
        if invited_user:
            if invited_user.tenant_id == tenant.id:
                raise serializers.ValidationError({
                    'invited_user_email': 'This user is already a member of this organization',
                })
            if UserTenantMembership.objects.filter(user=invited_user, tenant=tenant).exists():
                raise serializers.ValidationError({
                    'invited_user_email': 'This user is already a member of this organization',
                })
            data['invited_user'] = invited_user
        else:
            data['invited_user'] = None

        pending = OrganizationInvitation.objects.filter(tenant=tenant, status='pending')
        existing = pending.filter(invited_email__iexact=email).exists()
        if invited_user and not existing:
            existing = pending.filter(invited_user=invited_user).exists()

        if existing:
            raise serializers.ValidationError({
                'invited_user_email': 'This email already has a pending invitation to this organization',
            })

        from billing.account_limits import assert_tenant_can_add_user
        assert_tenant_can_add_user(tenant)

        data['invited_email'] = email
        if request and request.user:
            data['invited_by'] = request.user
        return data


class InvitationResponseSerializer(serializers.Serializer):
    """Serializer for accepting/declining invitations"""
    action = serializers.ChoiceField(choices=['accept', 'decline'])
