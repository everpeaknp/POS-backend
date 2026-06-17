from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from tenants.models import Tenant

User = get_user_model()


class Command(BaseCommand):
    help = 'Check user tenant status'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='User email to check')

    def handle(self, *args, **options):
        email = options['email']
        
        try:
            user = User.objects.get(email=email)
            self.stdout.write(f"\n=== User: {user.email} ===")
            self.stdout.write(f"ID: {user.id}")
            self.stdout.write(f"Username: {user.username}")
            self.stdout.write(f"Role: {user.role}")
            
            if user.tenant:
                self.stdout.write(self.style.WARNING(f"\n=== HAS TENANT ASSIGNED ==="))
                self.stdout.write(f"Tenant Name: {user.tenant.name}")
                self.stdout.write(f"Tenant ID: {user.tenant.id}")
                self.stdout.write(f"Tenant Slug: {user.tenant.slug}")
                self.stdout.write(f"Is Active: {user.tenant.is_active}")
                self.stdout.write(f"Created By: {user.tenant.created_by.email if user.tenant.created_by else 'None'}")
                self.stdout.write(f"Created from Registration: {user.tenant.created_from_registration}")
                self.stdout.write(self.style.ERROR(f"\nThis is why user can access dashboard!"))
            else:
                self.stdout.write(self.style.SUCCESS(f"\nTenant: None"))
                self.stdout.write(f"User should NOT be able to access dashboard")
                
            # Check tenants created by this user
            created_tenants = Tenant.objects.filter(created_by=user)
            self.stdout.write(f"\n=== Tenants Created by User: {created_tenants.count()} ===")
            for tenant in created_tenants:
                self.stdout.write(f"  - {tenant.name} (slug: {tenant.slug}, active: {tenant.is_active})")
                
            # Check all tenants where this user is a member
            all_user_tenants = Tenant.objects.filter(users=user)
            self.stdout.write(f"\n=== All Tenants with User as Member: {all_user_tenants.count()} ===")
            for tenant in all_user_tenants:
                self.stdout.write(f"  - {tenant.name} (slug: {tenant.slug})")
                
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User {email} not found"))
