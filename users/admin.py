from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'tenant', 'role', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active', 'tenant']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Tenant & Role', {'fields': ('tenant', 'role', 'phone')}),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Tenant & Role', {'fields': ('tenant', 'role', 'phone')}),
    )
