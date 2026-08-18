"""
One-off management command to add personal_finance module to existing tenants.
Usage: python manage.py add_personal_finance_module
"""

from django.core.management.base import BaseCommand
from tenants.models import Tenant


class Command(BaseCommand):
    help = 'Add personal_finance module to existing tenants that do not have it'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-slug',
            type=str,
            help='Specific tenant slug to update (optional, updates all if not provided)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        tenant_slug = options.get('tenant_slug')
        dry_run = options.get('dry_run', False)

        if tenant_slug:
            tenants = Tenant.objects.filter(slug=tenant_slug)
            if not tenants.exists():
                self.stdout.write(self.style.ERROR(f'Tenant with slug "{tenant_slug}" not found'))
                return
        else:
            tenants = Tenant.objects.all()

        updated_count = 0
        skipped_count = 0

        for tenant in tenants:
            if 'personal_finance' not in tenant.active_modules:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f'[DRY RUN] Would add personal_finance to tenant: {tenant.name} ({tenant.slug})'
                        )
                    )
                    self.stdout.write(f'  Current modules: {tenant.active_modules}')
                else:
                    old_modules = list(tenant.active_modules)
                    tenant.active_modules.append('personal_finance')
                    tenant.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Added personal_finance to tenant: {tenant.name} ({tenant.slug})'
                        )
                    )
                    self.stdout.write(f'  Before: {old_modules}')
                    self.stdout.write(f'  After:  {tenant.active_modules}')
                updated_count += 1
            else:
                self.stdout.write(
                    f'- Skipped tenant {tenant.name} ({tenant.slug}) - already has personal_finance'
                )
                skipped_count += 1

        self.stdout.write('')
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'DRY RUN: Would update {updated_count} tenant(s), skip {skipped_count}')
            )
            self.stdout.write('Run without --dry-run to apply changes')
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Updated {updated_count} tenant(s), skipped {skipped_count}')
            )
