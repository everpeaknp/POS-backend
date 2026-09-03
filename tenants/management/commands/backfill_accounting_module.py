"""
Management command to backfill 'accounting' module to existing tenants.

Usage:
    python manage.py backfill_accounting_module           # Dry-run (no changes)
    python manage.py backfill_accounting_module --apply   # Apply changes
"""
from django.core.management.base import BaseCommand
from tenants.models import Tenant


class Command(BaseCommand):
    help = 'Add "accounting" module to all tenants currently missing it'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Apply changes to database (default is dry-run)',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        
        # Fetch all tenants
        tenants = list(Tenant.objects.all())
        
        # Find tenants missing 'accounting'
        missing_accounting = [
            t for t in tenants 
            if 'accounting' not in (t.active_modules or [])
        ]
        
        # Count by business_type
        business_types = ['retail', 'kirana', 'construction', 'hardware', 'other', 'personal']
        by_type = {}
        for bt in business_types:
            by_type[bt] = [t for t in missing_accounting if t.business_type == bt]
        
        # Catch any other business types not in standard list
        other_types = set(t.business_type for t in missing_accounting) - set(business_types)
        for bt in other_types:
            by_type[bt] = [t for t in missing_accounting if t.business_type == bt]
        
        # Print summary
        self.stdout.write(self.style.NOTICE(f'\nTotal tenants: {len(tenants)}'))
        self.stdout.write(self.style.NOTICE(f'Missing "accounting" module: {len(missing_accounting)}'))
        self.stdout.write('')
        self.stdout.write(self.style.NOTICE('Breakdown by business_type:'))
        
        for bt in sorted(by_type.keys()):
            count = len(by_type[bt])
            if count > 0:
                self.stdout.write(f'  {bt:15s}: {count:3d} tenant(s)')
        
        if not missing_accounting:
            self.stdout.write(self.style.SUCCESS('\n✓ All tenants already have "accounting" module'))
            return
        
        # Show sample
        self.stdout.write('')
        self.stdout.write(self.style.NOTICE('Sample tenants (first 5):'))
        for t in missing_accounting[:5]:
            modules = t.active_modules or []
            self.stdout.write(f'  ID {t.id:3d} ({t.business_type:15s}): {modules}')
        
        if not apply:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('DRY RUN - No changes made'))
            self.stdout.write(self.style.WARNING(f'Run with --apply to update {len(missing_accounting)} tenant(s)'))
            return
        
        # Apply changes
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(f'APPLYING CHANGES to {len(missing_accounting)} tenant(s)...'))
        
        updated = 0
        for tenant in missing_accounting:
            old_modules = list(tenant.active_modules or [])
            tenant.active_modules.append('accounting')
            tenant.save(update_fields=['active_modules', 'updated_at'])
            updated += 1
            self.stdout.write(
                f'  Updated ID {tenant.id} ({tenant.business_type}): '
                f'{old_modules} → {tenant.active_modules}'
            )
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'✓ Successfully updated {updated} tenant(s)'))
