from django.core.management.base import BaseCommand
from users.models import User, AuditLog
from tenants.models import Tenant
from datetime import datetime, timedelta
import random


class Command(BaseCommand):
    help = 'Seed sample audit logs for testing'

    def handle(self, *args, **kwargs):
        # Get first tenant and users
        tenant = Tenant.objects.first()
        if not tenant:
            self.stdout.write(self.style.ERROR('No tenant found. Please create a tenant first.'))
            return
        
        users = list(User.objects.filter(tenant=tenant))
        if not users:
            self.stdout.write(self.style.ERROR('No users found for this tenant.'))
            return
        
        # Sample actions and modules
        actions = ['create', 'update', 'delete', 'view', 'login', 'logout', 'export']
        modules = ['sales', 'purchase', 'inventory', 'accounting', 'construction', 'users', 'settings']
        
        descriptions = {
            'create': [
                'Created new sales order SO-{num}',
                'Created new customer {name}',
                'Created new product {name}',
                'Created new invoice INV-{num}',
            ],
            'update': [
                'Updated sales order SO-{num}',
                'Updated customer information',
                'Updated product pricing',
                'Updated invoice status',
            ],
            'delete': [
                'Deleted sales order SO-{num}',
                'Deleted customer record',
                'Deleted product from inventory',
                'Deleted draft invoice',
            ],
            'view': [
                'Viewed sales report',
                'Viewed customer details',
                'Viewed inventory summary',
                'Viewed financial statements',
            ],
            'login': ['User logged in successfully'],
            'logout': ['User logged out'],
            'export': [
                'Exported sales data to Excel',
                'Exported customer list',
                'Exported inventory report',
            ],
        }
        
        # Create 50 sample audit logs
        logs_created = 0
        for i in range(50):
            user = random.choice(users)
            action = random.choice(actions)
            module = random.choice(modules)
            
            desc_template = random.choice(descriptions[action])
            description = desc_template.format(
                num=random.randint(1000, 9999),
                name=f"Sample {random.randint(1, 100)}"
            )
            
            # Random timestamp within last 30 days
            days_ago = random.randint(0, 30)
            hours_ago = random.randint(0, 23)
            created_at = datetime.now() - timedelta(days=days_ago, hours=hours_ago)
            
            AuditLog.objects.create(
                user=user,
                tenant=tenant,
                action=action,
                module=module,
                description=description,
                ip_address=f"192.168.1.{random.randint(1, 255)}",
                metadata={'sample': True},
                created_at=created_at
            )
            logs_created += 1
        
        self.stdout.write(self.style.SUCCESS(f'Successfully created {logs_created} audit logs'))
