from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group

from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import User, AuditLog
from .permission_models import RolePermission

# Groups (django.contrib.auth) are unused — all platform staff are
# superusers, which bypass Django's permission system entirely, and
# tenant-level roles/permissions are handled by RolePermission instead.
admin.site.unregister(Group)


@admin.register(RolePermission)
class RolePermissionAdmin(UnfoldModelAdmin):
    list_display = ['tenant', 'role', 'module', 'action', 'allowed']
    list_filter = ['tenant', 'role', 'module', 'action', 'allowed']
    search_fields = ['tenant__name']
    readonly_fields = ['tenant', 'role', 'module', 'action', 'allowed']
    ordering = ['tenant', 'role', 'module', 'action']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(UnfoldModelAdmin, BaseUserAdmin):
    # Unfold's own styled forms for the add/change/password-change pages —
    # UnfoldModelAdmin alone doesn't retrofit these since BaseUserAdmin
    # sets its own `form`/`add_form`/`change_password_form` defaults.
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = [
        'username', 'email', 'tenant', 'role',
        'is_active', 'is_superuser', 'date_joined',
    ]
    list_filter = ['is_superuser', 'is_staff', 'role', 'is_active', 'tenant']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering = ['-date_joined']

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'phone', 'avatar')}),
        ('Customer application', {
            'fields': ('tenant', 'role'),
            'description': (
                'Organization and role for the customer-facing app (dashboard). '
                'These users should not have platform admin access.'
            ),
        }),
        ('Platform access (KHATA team)', {
            'fields': ('is_superuser', 'is_staff', 'is_active'),
            'description': 'Only superusers can log into /admin. Keep tenant users non-staff.',
        }),
        ('Advanced permissions', {
            'fields': ('groups', 'user_permissions', 'assigned_sites'),
            'classes': ('collapse',),
        }),
        ('Important dates', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',),
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2'),
        }),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'phone')}),
        ('Customer application', {'fields': ('tenant', 'role')}),
        ('Platform access (KHATA team)', {'fields': ('is_superuser', 'is_staff', 'is_active')}),
    )


@admin.register(AuditLog)
class AuditLogAdmin(UnfoldModelAdmin):
    list_display = ['created_at', 'user', 'tenant', 'action', 'module', 'description']
    list_filter = ['action', 'module', 'tenant', 'created_at']
    search_fields = ['description', 'user__username', 'user__email', 'tenant__name']
    readonly_fields = [
        'user', 'tenant', 'action', 'module', 'content_type', 'object_id',
        'description', 'ip_address', 'user_agent', 'metadata', 'created_at',
    ]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
