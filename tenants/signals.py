"""Signal handlers for tenant-related events."""

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Tenant


@receiver(post_save, sender=Tenant)
def create_default_warehouse(sender, instance, created, **kwargs):
    """
    Create a default warehouse when a new tenant is created.
    Users can rename it later from the warehouse management page.
    """
    if created:
        try:
            from inventory.models import Warehouse
            
            # Check if warehouse already exists
            if not Warehouse.objects.filter(tenant=instance).exists():
                Warehouse.objects.create(
                    tenant=instance,
                    name='Main Warehouse',
                    location='Default Location',
                    is_active=True
                )
                print(f"✓ Created default warehouse for tenant: {instance.name}")
        except Exception as e:
            # Don't fail tenant creation if warehouse creation fails
            print(f"Warning: Failed to create default warehouse for {instance.name}: {e}")
