"""Management command to create default warehouses for existing tenants."""

from django.core.management.base import BaseCommand
from tenants.models import Tenant


class Command(BaseCommand):
    help = 'Create default warehouses for existing tenants that don\'t have one'

    def handle(self, *args, **options):
        from inventory.models import Warehouse
        
        tenants = Tenant.objects.all()
        created_count = 0
        skipped_count = 0
        
        self.stdout.write(f'Processing {tenants.count()} tenants...\n')
        
        for tenant in tenants:
            # Check if tenant already has a warehouse
            if Warehouse.objects.filter(tenant=tenant).exists():
                self.stdout.write(f'  ✓ Tenant "{tenant.name}" already has warehouse(s)')
                skipped_count += 1
                continue
            
            # Create default warehouse
            try:
                warehouse = Warehouse.objects.create(
                    tenant=tenant,
                    name='Main Warehouse',
                    location='Default Location',
                    is_active=True
                )
                self.stdout.write(self.style.SUCCESS(
                    f'  ✓ Created default warehouse for tenant "{tenant.name}"'
                ))
                created_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'  ✗ Failed to create warehouse for tenant "{tenant.name}": {e}'
                ))
        
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Created {created_count} default warehouses'
        ))
        self.stdout.write(f'  Skipped {skipped_count} tenants (already have warehouses)')
        self.stdout.write('=' * 60)
