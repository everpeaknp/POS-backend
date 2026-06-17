from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from tenants.models import Tenant

User = get_user_model()


class Command(BaseCommand):
    help = 'Fix users with registration tenants - remove tenant assignment or delete tenant'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete-tenants',
            action='store_true',
            help='Delete registration tenants instead of just unassigning users',
        )

    def handle(self, *args, **options):
        delete_tenants = options['delete_tenants']
        
        # Find all registration tenants
        registration_tenants = Tenant.objects.filter(created_from_registration=True)
        
        self.stdout.write(f"\nFound {registration_tenants.count()} registration tenants")
        
        for tenant in registration_tenants:
            self.stdout.write(f"\n=== Tenant: {tenant.name} (ID: {tenant.id}) ===")
            self.stdout.write(f"Slug: {tenant.slug}")
            self.stdout.write(f"Created by: {tenant.created_by.email if tenant.created_by else 'None'}")
            
            # Find users assigned to this tenant
            users = User.objects.filter(tenant=tenant)
            self.stdout.write(f"Users assigned: {users.count()}")
            
            for user in users:
                self.stdout.write(f"  - {user.email} (role: {user.role})")
            
            if delete_tenants:
                # Delete the tenant
                self.stdout.write(self.style.WARNING(f"Deleting tenant: {tenant.name}"))
                
                # Unassign users first
                User.objects.filter(tenant=tenant).update(tenant=None)
                
                # Delete tenant
                tenant.delete()
                self.stdout.write(self.style.SUCCESS(f"✓ Deleted tenant and unassigned {users.count()} users"))
            else:
                # Just unassign users
                if users.exists():
                    self.stdout.write(self.style.WARNING(f"Unassigning {users.count()} users from tenant"))
                    User.objects.filter(tenant=tenant).update(tenant=None)
                    self.stdout.write(self.style.SUCCESS(f"✓ Unassigned users (tenant still exists)"))
                else:
                    self.stdout.write("No users to unassign")
        
        if not delete_tenants:
            self.stdout.write(self.style.WARNING(f"\nNote: Tenants still exist. Run with --delete-tenants to remove them."))
        
        self.stdout.write(self.style.SUCCESS(f"\n✓ Done!"))
