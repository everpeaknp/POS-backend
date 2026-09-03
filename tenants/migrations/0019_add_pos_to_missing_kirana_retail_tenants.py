from django.db import migrations


def add_pos_to_affected_tenants(apps, schema_editor):
    """Add 'pos' module to kirana/retail tenants that are missing it (IDs 20, 23, 24)"""
    Tenant = apps.get_model('tenants', 'Tenant')
    
    # Specific tenant IDs that need 'pos' added
    affected_ids = [20, 23, 24]
    
    for tenant in Tenant.objects.filter(id__in=affected_ids):
        if tenant.active_modules is None:
            tenant.active_modules = []
        
        if 'pos' not in tenant.active_modules:
            tenant.active_modules = tenant.active_modules + ['pos']
            tenant.save()
            print(f"Added 'pos' to tenant {tenant.id} ({tenant.name})")
        else:
            print(f"Tenant {tenant.id} ({tenant.name}) already has 'pos'")


def reverse_add_pos(apps, schema_editor):
    """Reverse: remove 'pos' from the affected tenants"""
    Tenant = apps.get_model('tenants', 'Tenant')
    
    affected_ids = [20, 23, 24]
    
    for tenant in Tenant.objects.filter(id__in=affected_ids):
        if tenant.active_modules and 'pos' in tenant.active_modules:
            tenant.active_modules = [m for m in tenant.active_modules if m != 'pos']
            tenant.save()
            print(f"Removed 'pos' from tenant {tenant.id} ({tenant.name})")


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0018_alter_tenant_business_type'),
    ]

    operations = [
        migrations.RunPython(add_pos_to_affected_tenants, reverse_add_pos),
    ]
