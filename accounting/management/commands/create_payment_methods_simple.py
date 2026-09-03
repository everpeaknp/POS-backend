"""
Simple fix: Create payment methods for all tenants using their first Assets account.
"""
from django.core.management.base import BaseCommand
from tenants.models import Tenant
from accounting.models import PaymentMethod, Account


class Command(BaseCommand):
    help = 'Create payment methods for all tenants'

    def handle(self, *args, **options):
        tenants = Tenant.objects.all()
        total_created = 0
        tenants_updated = 0
        
        for tenant in tenants:
            self.stdout.write(f'\nTenant {tenant.id}: {tenant.name}')
            
            # Find ANY existing Assets account
            asset_account = Account.objects.filter(
                tenant=tenant,
                type='Assets'
            ).first()
            
            if not asset_account:
                # Create minimal dummy account for linking
                try:
                    import random
                    code = f'CA-{random.randint(1000,9999)}-{tenant.id}'
                    asset_account = Account.objects.create(
                        tenant=tenant,
                        code=code,
                        name='Cash Account',
                        type='Assets',
                        sub_type='Cash',
                        status='active',
                    )
                    self.stdout.write(f'  Created dummy account ({code})')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  No account, cannot create: {e}'))
                    continue
            
            # Create payment methods
            methods = [
                ('Cash', 'cash'),
                ('Bank', 'bank_transfer'),
                ('Fonepay', 'digital_wallet'),
                ('Credit Card', 'card'),
            ]
            
            created_count = 0
            for name, method_type in methods:
                try:
                    _, created = PaymentMethod.objects.get_or_create(
                        tenant=tenant,
                        name=name,
                        defaults={
                            'method_type': method_type,
                            'linked_account': asset_account,
                            'is_active': True,
                            'is_system_default': True,
                        }
                    )
                    if created:
                        created_count += 1
                        self.stdout.write(self.style.SUCCESS(f'  ✓ {name}'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  ✗ {name}: {e}'))
            
            if created_count > 0:
                tenants_updated += 1
                total_created += created_count
        
        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Created {total_created} payment methods for {tenants_updated} tenants'
        ))
