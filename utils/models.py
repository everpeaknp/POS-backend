from django.db import models
from tenants.middleware import get_current_tenant


class TenantManager(models.Manager):
    """
    Custom manager that automatically filters querysets by current tenant.
    """
    
    def get_queryset(self):
        """
        Override to filter by current tenant from thread-local storage.
        """
        queryset = super().get_queryset()
        tenant = get_current_tenant()
        
        if tenant:
            return queryset.filter(tenant=tenant)
        
        return queryset


class TenantModel(models.Model):
    """
    Abstract base model for all tenant-scoped models.
    Automatically includes tenant FK and timestamp fields.
    """
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='%(class)s_set'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = TenantManager()
    
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        """
        Auto-assign tenant from current thread if not set.
        """
        if not self.tenant_id:
            tenant = get_current_tenant()
            if tenant:
                self.tenant = tenant
        super().save(*args, **kwargs)
