from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, AuditLog
from .notification_models import Notification
from tenants.models import Tenant


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT serializer that includes user role and tenant information in the response.
    Accepts email instead of username for login.
    """
    
    # Override username_field to use email
    username_field = 'email'
    
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        
        # Get tenant (either direct or via membership)
        tenant = user.get_tenant()
        
        # Add custom claims to the token
        token['role'] = user.role
        token['tenant_id'] = tenant.id if tenant else None
        token['tenant_slug'] = tenant.slug if tenant else None
        token['tenant_name'] = tenant.name if tenant else None
        
        return token
    
    def validate(self, attrs):
        # Use email for authentication
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            # Authenticate using email
            from django.contrib.auth import authenticate
            user = authenticate(request=self.context.get('request'), email=email, password=password)
            
            if not user:
                raise serializers.ValidationError(
                    {'detail': 'No active account found with the given credentials'},
                    code='authorization'
                )
        else:
            raise serializers.ValidationError(
                {'detail': 'Must include "email" and "password".'},
                code='authorization'
            )
        
        from users.auth_tokens import issue_tokens_for_user
        return issue_tokens_for_user(user, self.context.get('request'))


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = [
            'id', 'name', 'slug', 'workspace_name', 'email', 'address', 'business_type',
            'is_active', 'plan_type', 'active_modules', 'created_by',
        ]
        read_only_fields = ['id', 'slug', 'created_by']


class UserSerializer(serializers.ModelSerializer):
    tenant = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    permissions = serializers.SerializerMethodField()
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, required=False)
    is_super_admin = serializers.SerializerMethodField()
    # Membership access in the active org (business card). Not Khata login.
    is_active = serializers.BooleanField(required=False)
    avatar = serializers.ImageField(required=False, allow_null=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'role', 'phone',
            'avatar', 'tenant', 'password', 'is_active', 'last_login', 'date_joined',
            'permissions', 'is_super_admin',
        ]
        read_only_fields = ['id', 'last_login', 'date_joined', 'permissions', 'is_super_admin']

    def get_is_super_admin(self, obj):
        tenant = self._request_tenant() or obj.get_tenant()
        return bool(tenant and tenant.created_by_id == obj.id)

    def get_tenant(self, obj):
        tenant = obj.get_tenant()
        if not tenant:
            return None
        return TenantSerializer(tenant).data

    def _request_tenant(self):
        request = self.context.get('request')
        if not request or not getattr(request, 'user', None):
            return None
        from tenants.utils import get_request_tenant
        return get_request_tenant(request.user)

    def _get_membership(self, obj):
        tenant = self._request_tenant() or obj.get_tenant()
        if not tenant:
            return None
        from tenants.membership_models import UserTenantMembership
        return UserTenantMembership.objects.filter(user=obj, tenant=tenant).first()

    def _get_effective_role(self, obj):
        """Tenant membership role for the active organization, else global role."""
        tenant = self._request_tenant() or obj.get_tenant()
        if tenant and tenant.created_by_id == obj.id:
            return 'super_admin'
        membership = self._get_membership(obj)
        if membership:
            return membership.role
        return obj.role

    def _get_effective_is_active(self, obj):
        """Whether membership for the active org is enabled (business access)."""
        tenant = self._request_tenant() or obj.get_tenant()
        if tenant and tenant.created_by_id == obj.id:
            return True
        membership = self._get_membership(obj)
        if membership is not None:
            return bool(membership.is_active)
        return True

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['role'] = self._get_effective_role(instance)
        data['is_active'] = self._get_effective_is_active(instance)
        return data
    
    def get_permissions(self, obj):
        """Get user permissions including module access"""
        return {
            'is_admin': obj.is_admin,
            'is_manager': obj.is_manager,
            'is_supervisor': obj.is_supervisor,
            'is_accountant': obj.is_accountant,
            'is_viewer': obj.is_viewer,
            'can_approve_purchases': obj.can_approve_purchases(),
            'can_manage_users': obj.can_manage_users(),
            'can_view_financials': obj.can_view_financials(),
            'can_edit_data': obj.can_edit_data(),
            'modules': {
                'dashboard': obj.has_module_access('dashboard'),
                'sales': obj.has_module_access('sales'),
                'purchase': obj.has_module_access('purchase'),
                'inventory': obj.has_module_access('inventory'),
                'construction': obj.has_module_access('construction'),
                'accounting': obj.has_module_access('accounting'),
                'hardware': obj.has_module_access('hardware'),
                'reports': obj.has_module_access('reports'),
                'settings': obj.has_module_access('settings'),
                'pos': obj.has_module_access('pos'),
                'hr': obj.has_module_access('hr'),
            }
        }
    
    def create(self, validated_data):
        """Create user with password"""
        password = validated_data.pop('password', None)
        # Account-level login status stays enabled; org access is membership.is_active
        validated_data.pop('is_active', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_password('changeme123')  # Default password
        user.save()
        return user
    
    def update(self, instance, validated_data):
        """Update user; role/is_active apply to membership in the active organization."""
        from rest_framework.exceptions import ValidationError

        password = validated_data.pop('password', None)
        role = validated_data.pop('role', None)
        membership_active = validated_data.pop('is_active', None)

        tenant = self._request_tenant()
        if tenant and tenant.created_by_id == instance.id:
            if membership_active is not None:
                raise ValidationError({'detail': 'No one can enable or disable the Super Admin.'})
            if role is not None:
                raise ValidationError({'detail': 'No one can change the Super Admin role.'})

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if password:
            instance.set_password(password)
        
        if tenant and (role is not None or membership_active is not None):
            from tenants.membership_models import UserTenantMembership

            membership, _ = UserTenantMembership.objects.get_or_create(
                user=instance,
                tenant=tenant,
                defaults={
                    'role': role or instance.role or 'viewer',
                    'is_active': True if membership_active is None else membership_active,
                },
            )
            membership_updates = []
            if role is not None and membership.role != role:
                membership.role = role
                membership_updates.append('role')
            if membership_active is not None and membership.is_active != membership_active:
                membership.is_active = membership_active
                membership_updates.append('is_active')
            if membership_updates:
                membership_updates.append('updated_at')
                membership.save(update_fields=membership_updates)

            if role is not None and instance.tenant_id == tenant.id:
                instance.role = role

            # If access to current org was disabled, move them off this business card
            if membership_active is False and instance.tenant_id == tenant.id:
                other = (
                    UserTenantMembership.objects.filter(user=instance, is_active=True)
                    .exclude(tenant=tenant)
                    .select_related('tenant')
                    .first()
                )
                if other:
                    instance.tenant = other.tenant
                    instance.role = other.role
                else:
                    instance.tenant = None
                    instance.role = 'viewer'
        elif role is not None:
            instance.role = role
        
        instance.save()
        return instance

class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile (name, phone, etc.)"""
    avatar = serializers.ImageField(required=False, allow_null=True)
    remove_avatar = serializers.BooleanField(required=False, write_only=True, default=False)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'avatar', 'remove_avatar']

    def update(self, instance, validated_data):
        remove_avatar = validated_data.pop('remove_avatar', False)
        if remove_avatar:
            if instance.avatar:
                instance.avatar.delete(save=False)
            instance.avatar = None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class PasswordChangeSerializer(serializers.Serializer):
    """Serializer for changing password"""
    current_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, min_length=8)
    
    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value
    
    def validate_new_password(self, value):
        # Add password strength validation
        if len(value) < 8:
            raise serializers.ValidationError('Password must be at least 8 characters long.')
        return value
    
    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'message', 'notification_type', 'level',
            'reference_type', 'reference_id', 'data', 'is_read', 'read_at',
            'action_url', 'created_at',
        ]
        read_only_fields = ['id', 'read_at', 'created_at']


class NotificationPreferencesSerializer(serializers.Serializer):
    """Serializer for notification preferences"""
    email_order_updates = serializers.BooleanField(default=True)
    email_payment_reminders = serializers.BooleanField(default=True)
    email_inventory_alerts = serializers.BooleanField(default=True)
    email_team_activity = serializers.BooleanField(default=True)
    push_desktop = serializers.BooleanField(default=False)
    push_mobile = serializers.BooleanField(default=False)
    push_sound = serializers.BooleanField(default=False)
    login_alerts = serializers.BooleanField(default=True)
    security_log_exports = serializers.BooleanField(default=False)


class SessionSerializer(serializers.Serializer):
    """Serializer for active sessions"""
    id = serializers.CharField()
    device = serializers.CharField()
    location = serializers.CharField()
    ip_address = serializers.CharField()
    last_active = serializers.DateTimeField()
    is_current = serializers.BooleanField()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    username = serializers.CharField(required=False, help_text="Username (auto-generated from email if not provided)")
    phone = serializers.CharField(required=True, help_text="Phone number is required")
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'first_name', 'last_name', 'phone']
    
    def validate_email(self, value):
        """Ensure email is unique"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('This email is already registered. Please use a different email or login.')
        return value
    
    def create(self, validated_data):
        try:
            email = validated_data.get('email', '')
            username = validated_data.get('username') or (email.split('@')[0] if email else 'user')

            # Ensure username is unique even when provided by the client
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            validated_data['username'] = username
            
            # Create user WITHOUT tenant (tenant=None)
            # User will create organization manually after login
            user = User.objects.create_user(
                **validated_data,
                tenant=None,  # No automatic tenant assignment
                role='viewer'  # Default role until they create/join an organization
            )

            try:
                from tenants.invitation_models import claim_pending_invitations_for_user
                claim_pending_invitations_for_user(user)
            except Exception:
                pass

            try:
                from mail.services import dispatch_welcome_email
                dispatch_welcome_email(user)
            except Exception:
                pass
            
            return user
        except serializers.ValidationError:
            # Re-raise validation errors as-is
            raise
        except Exception as e:
            # Handle specific database errors
            error_msg = str(e)
            if 'UNIQUE constraint failed: users.username' in error_msg:
                raise serializers.ValidationError({
                    'username': 'This username is already taken. Please choose a different username.'
                })
            elif 'UNIQUE constraint failed: users.email' in error_msg:
                raise serializers.ValidationError({
                    'email': 'This email is already registered. Please use a different email or login.'
                })
            else:
                raise serializers.ValidationError({
                    'detail': f'Registration failed: {error_msg}'
                })



class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    # Explicitly define ip_address as CharField to avoid Python 3.14 compatibility issue
    ip_address = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    
    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'user_name', 'action', 'action_display', 'module',
            'description', 'ip_address', 'metadata', 'created_at'
        ]
        read_only_fields = fields
    
    def get_user_name(self, obj):
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.username
        return "System"



class RolePermissionSerializer(serializers.Serializer):
    """
    Serializer for role permissions.
    Returns permissions in a format suitable for the frontend permissions matrix.
    """
    role = serializers.CharField()
    permissions = serializers.DictField(child=serializers.BooleanField())


class PermissionsMatrixSerializer(serializers.Serializer):
    """
    Serializer for the complete permissions matrix.
    Returns all roles with their permissions.
    """
    Admin = serializers.DictField(child=serializers.BooleanField())
    Manager = serializers.DictField(child=serializers.BooleanField())
    Supervisor = serializers.DictField(child=serializers.BooleanField())
    Accountant = serializers.DictField(child=serializers.BooleanField())
    Cashier = serializers.DictField(child=serializers.BooleanField())
    Viewer = serializers.DictField(child=serializers.BooleanField())


class UpdatePermissionsSerializer(serializers.Serializer):
    """
    Serializer for updating permissions.
    Accepts the complete permissions matrix from the frontend.
    """
    Admin = serializers.DictField(child=serializers.BooleanField(), required=False)
    Manager = serializers.DictField(child=serializers.BooleanField(), required=False)
    Supervisor = serializers.DictField(child=serializers.BooleanField(), required=False)
    Accountant = serializers.DictField(child=serializers.BooleanField(), required=False)
    Cashier = serializers.DictField(child=serializers.BooleanField(), required=False)
    Viewer = serializers.DictField(child=serializers.BooleanField(), required=False)


class PrivacyPreferencesSerializer(serializers.Serializer):
    profile_visibility = serializers.ChoiceField(
        choices=['everyone', 'organization', 'private'],
        default='organization',
    )
    activity_status = serializers.BooleanField(default=True)
    search_indexing = serializers.BooleanField(default=False)
    data_retention_years = serializers.ChoiceField(
        choices=[1, 5, 0],
        default=1,
    )


class AccountDeleteSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Password is incorrect.')
        return value


class GoogleAuthSerializer(serializers.Serializer):
    credential = serializers.CharField(write_only=True)

    def validate(self, attrs):
        from users.google_auth import verify_google_id_token, authenticate_or_create_google_user
        from users.auth_tokens import issue_tokens_for_user

        idinfo = verify_google_id_token(attrs['credential'])
        user = authenticate_or_create_google_user(idinfo)
        request = self.context.get('request')
        return issue_tokens_for_user(user, request)


class AppearancePreferencesSerializer(serializers.Serializer):
    """Serializer for user appearance preferences"""
    theme = serializers.ChoiceField(
        choices=['light', 'dark', 'system'],
        default='light'
    )
    language = serializers.ChoiceField(
        choices=['en-US', 'en-GB', 'es', 'fr', 'de', 'hi'],
        default='en-US'
    )
    timezone = serializers.CharField(default='UTC')
    date_calendar_system = serializers.ChoiceField(
        choices=['AD', 'BS'],
        default='AD'
    )
    compact_mode = serializers.BooleanField(default=False)
    smooth_animations = serializers.BooleanField(default=True)
