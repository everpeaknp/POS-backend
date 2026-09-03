"""
Management command to enable POS module for tenants.
Usage:
  python manage.py enable_pos --all           # Enable for all tenants
  python manage.py enable_pos --tenant=slug   # Enable for specific tenant
"""

from django.core.management.base import BaseCommand
from tenants.models import Tenant


class Command(BaseCommand):
    help = 'Enable POS module for tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Enable POS for all tenants',
        )
        parser.add_argument(
            '--tenant',
            type=str,
            help='Tenant slug to enable POS for',
        )

    def handle(self, *args, **options):
        if options['all']:
            tenants = Tenant.objects.all()
            count = 0
            for tenant in tenants:
                if 'pos' not in tenant.active_modules:
                    tenant.active_modules.append('pos')
                    tenant.save()
                    count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Enabled POS for: {tenant.name} ({tenant.slug})')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'- POS already enabled for: {tenant.name} ({tenant.slug})')
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f'\nEnabled POS for {count} tenant(s)')
            )
        
        elif options['tenant']:
            slug = options['tenant']
            try:
                tenant = Tenant.objects.get(slug=slug)
                if 'pos' not in tenant.active_modules:
                    tenant.active_modules.append('pos')
                    tenant.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Enabled POS for: {tenant.name} ({tenant.slug})')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'POS already enabled for: {tenant.name} ({tenant.slug})')
                    )
            except Tenant.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Tenant with slug "{slug}" not found')
                )
        else:
            self.stdout.write(
                self.style.ERROR('Please specify --all or --tenant=slug')
            )
