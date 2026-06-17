from django.contrib import admin
from .models import Tenant
from .invitation_models import OrganizationInvitation
from .membership_models import UserTenantMembership


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'business_type', 'plan_type', 'is_active', 'created_at']
    list_filter = ['business_type', 'plan_type', 'is_active', 'created_from_registration']
    search_fields = ['name', 'slug', 'email', 'owner_name']
    readonly_fields = ['slug', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'business_type', 'created_by')
        }),
        ('Contact Information', {
            'fields': ('owner_name', 'email', 'phone', 'address')
        }),
        ('Subscription & Status', {
            'fields': ('is_active', 'plan_type', 'created_from_registration', 'active_modules')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(admin.ModelAdmin):
    list_display = ['invited_user', 'tenant', 'role', 'status', 'invited_by', 'created_at', 'expires_at']
    list_filter = ['status', 'role', 'created_at']
    search_fields = ['invited_user__email', 'invited_user__username', 'tenant__name']
    readonly_fields = ['created_at', 'updated_at', 'responded_at', 'is_expired']
    
    fieldsets = (
        ('Invitation Details', {
            'fields': ('tenant', 'invited_user', 'invited_by', 'role', 'message')
        }),
        ('Status', {
            'fields': ('status', 'expires_at', 'is_expired', 'responded_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserTenantMembership)
class UserTenantMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'tenant', 'role', 'joined_at']
    list_filter = ['role', 'joined_at']
    search_fields = ['user__email', 'user__username', 'tenant__name']
    readonly_fields = ['joined_at', 'updated_at']
    
    fieldsets = (
        ('Membership Details', {
            'fields': ('user', 'tenant', 'role')
        }),
        ('Timestamps', {
            'fields': ('joined_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
