from django.db import models
from django.utils.text import slugify
from django.conf import settings


class Tenant(models.Model):
    """
    Represents an organization/tenant in the multi-tenant system.
    Each tenant can subscribe to different business modules.
    """
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('premium', 'Premium'),
        ('enterprise', 'Enterprise'),
    ]
    
    BUSINESS_TYPE_CHOICES = [
        ('construction', 'Construction'),
        ('hardware', 'Hardware'),
        ('retail', 'Retail'),
        ('wholesale', 'Wholesale'),
        ('manufacturing', 'Manufacturing'),
        ('services', 'Services'),
        ('other', 'Other'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    business_type = models.CharField(max_length=50, choices=BUSINESS_TYPE_CHOICES, default='other')
    
    # Creator tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_tenants',
        help_text="User who created this organization"
    )
    
    # Contact Information
    owner_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    
    # Accounting Details
    accounting_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when accounting records start for this organization"
    )
    vat_registered = models.BooleanField(
        default=False,
        help_text="Whether the organization is registered for VAT"
    )
    
    # Workspace Details
    workspace_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Custom workspace name (defaults to organization name if not provided)"
    )
    logo = models.ImageField(
        upload_to='tenant_logos/',
        null=True,
        blank=True,
        help_text="Organization logo"
    )
    
    # Subscription & Status
    is_active = models.BooleanField(default=True)
    plan_type = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free')
    created_from_registration = models.BooleanField(
        default=False,
        help_text="True if tenant was created during user registration, False if created explicitly from /erp/new"
    )
    
    # Module Subscriptions (JSON field for flexibility)
    active_modules = models.JSONField(
        default=list,
        help_text="List of active module names: ['construction', 'hardware', 'retail']"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tenants'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            
            # Ensure slug is unique
            while Tenant.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            self.slug = slug
        super().save(*args, **kwargs)
    
    def has_module(self, module_name):
        """Check if tenant has access to a specific module"""
        return module_name in self.active_modules
    
    def activate_module(self, module_name):
        """Activate a module for this tenant"""
        if module_name not in self.active_modules:
            self.active_modules.append(module_name)
            self.save()
    
    def deactivate_module(self, module_name):
        """Deactivate a module for this tenant"""
        if module_name in self.active_modules:
            self.active_modules.remove(module_name)
            self.save()


# Import invitation and membership models
from .invitation_models import OrganizationInvitation
from .membership_models import UserTenantMembership
