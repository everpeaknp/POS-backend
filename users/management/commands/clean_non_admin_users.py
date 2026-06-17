"""
Django management command to safely clean all non-admin users and their related data.

Usage:
    python manage.py clean_non_admin_users [--dry-run] [--backup]

Options:
    --dry-run: Show what would be deleted without actually deleting
    --backup: Create a JSON backup before deletion
    --force: Skip confirmation prompt
"""

import json
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from django.apps import apps
from django.core.serializers import serialize

User = get_user_model()


class Command(BaseCommand):
    help = 'Safely delete all non-admin users and their related data while preserving admin accounts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--backup',
            action='store_true',
            help='Create a JSON backup of users before deletion',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        create_backup = options['backup']
        force = options['force']

        self.stdout.write(self.style.WARNING('\n' + '='*70))
        self.stdout.write(self.style.WARNING('CLEAN NON-ADMIN USERS - DATABASE CLEANUP'))
        self.stdout.write(self.style.WARNING('='*70 + '\n'))

        # Get all users
        all_users = User.objects.all()
        admin_users = User.objects.filter(is_superuser=True)
        non_admin_users = User.objects.filter(is_superuser=False)

        # Display summary
        self.stdout.write(f"Total users in database: {all_users.count()}")
        self.stdout.write(self.style.SUCCESS(f"Admin/Superuser accounts: {admin_users.count()}"))
        self.stdout.write(self.style.ERROR(f"Non-admin users to delete: {non_admin_users.count()}"))
        
        if admin_users.count() == 0:
            self.stdout.write(self.style.ERROR('\n⚠️  WARNING: No admin users found! Aborting to prevent system lockout.'))
            return

        # Show admin users that will be preserved
        self.stdout.write(self.style.SUCCESS('\n✓ Admin accounts that will be PRESERVED:'))
        for user in admin_users:
            self.stdout.write(f"  - {user.username} ({user.email}) - ID: {user.id}")

        # Show non-admin users that will be deleted
        if non_admin_users.count() > 0:
            self.stdout.write(self.style.ERROR('\n✗ Non-admin users that will be DELETED:'))
            for user in non_admin_users[:10]:  # Show first 10
                tenant_info = f" - Tenant: {user.tenant.name}" if user.tenant else ""
                self.stdout.write(f"  - {user.username} ({user.email}){tenant_info}")
            
            if non_admin_users.count() > 10:
                self.stdout.write(f"  ... and {non_admin_users.count() - 10} more users")

        # Analyze related data
        self.stdout.write(self.style.WARNING('\n📊 Analyzing related data...'))
        related_data = self._analyze_related_data(non_admin_users)
        
        for model_name, count in related_data.items():
            if count > 0:
                self.stdout.write(f"  - {model_name}: {count} records")

        # Create backup if requested
        if create_backup and not dry_run:
            backup_file = self._create_backup(non_admin_users)
            self.stdout.write(self.style.SUCCESS(f'\n✓ Backup created: {backup_file}'))

        # Confirmation
        if not force and not dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  This action will permanently delete:'))
            self.stdout.write(f"   - {non_admin_users.count()} non-admin users")
            self.stdout.write(f"   - All their related data (tenants, transactions, etc.)")
            self.stdout.write(self.style.WARNING('\n⚠️  Admin accounts will be PRESERVED'))
            
            confirm = input('\nType "DELETE" to confirm (or anything else to cancel): ')
            if confirm != 'DELETE':
                self.stdout.write(self.style.ERROR('\n✗ Operation cancelled'))
                return

        # Perform deletion
        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODE - No data will be deleted'))
            self.stdout.write(self.style.SUCCESS('\n✓ Dry run completed successfully'))
        else:
            self.stdout.write(self.style.WARNING('\n🗑️  Starting deletion process...'))
            deleted_counts = self._delete_non_admin_users(non_admin_users)
            
            self.stdout.write(self.style.SUCCESS('\n✓ Deletion completed successfully!'))
            self.stdout.write('\nDeleted:')
            for model_name, count in deleted_counts.items():
                if count > 0:
                    self.stdout.write(f"  - {model_name}: {count} records")

        # Final summary
        remaining_users = User.objects.all().count()
        remaining_admins = User.objects.filter(is_superuser=True).count()
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('CLEANUP SUMMARY'))
        self.stdout.write(self.style.SUCCESS('='*70))
        self.stdout.write(f"Remaining users: {remaining_users}")
        self.stdout.write(f"Remaining admins: {remaining_admins}")
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))

    def _analyze_related_data(self, users):
        """Analyze related data that will be deleted"""
        related_data = {}
        
        # Get Tenant model
        try:
            Tenant = apps.get_model('tenants', 'Tenant')
            # Tenants created by these users
            related_data['Tenants (created_by)'] = Tenant.objects.filter(created_by__in=users).count()
            # Tenants where user is assigned
            related_data['Tenants (assigned)'] = Tenant.objects.filter(users__in=users).distinct().count()
        except LookupError:
            pass

        # Get TenantMembership model
        try:
            TenantMembership = apps.get_model('tenants', 'TenantMembership')
            related_data['Tenant Memberships'] = TenantMembership.objects.filter(user__in=users).count()
        except LookupError:
            pass

        # Get Invitation model
        try:
            Invitation = apps.get_model('tenants', 'Invitation')
            related_data['Invitations (sent)'] = Invitation.objects.filter(invited_by__in=users).count()
            related_data['Invitations (received)'] = Invitation.objects.filter(email__in=users.values_list('email', flat=True)).count()
        except LookupError:
            pass

        # Get Employee model (HR)
        try:
            Employee = apps.get_model('hr', 'Employee')
            related_data['HR Employees'] = Employee.objects.filter(user__in=users).count()
        except LookupError:
            pass

        # Get AuditLog model
        try:
            AuditLog = apps.get_model('users', 'AuditLog')
            related_data['Audit Logs'] = AuditLog.objects.filter(user__in=users).count()
        except LookupError:
            pass

        # Get UserPermission model
        try:
            UserPermission = apps.get_model('users', 'UserPermission')
            related_data['User Permissions'] = UserPermission.objects.filter(user__in=users).count()
        except LookupError:
            pass

        return related_data

    def _create_backup(self, users):
        """Create a JSON backup of users before deletion"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f'user_backup_{timestamp}.json'
        
        # Serialize users
        user_data = json.loads(serialize('json', users))
        
        # Add related data
        backup_data = {
            'timestamp': timestamp,
            'total_users': users.count(),
            'users': user_data,
        }
        
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)
        
        return backup_file

    @transaction.atomic
    def _delete_non_admin_users(self, users):
        """Delete non-admin users and their related data within a transaction"""
        deleted_counts = {}
        
        # Delete related data first to avoid foreign key constraints
        
        # 1. Delete TenantMemberships
        try:
            TenantMembership = apps.get_model('tenants', 'TenantMembership')
            count, _ = TenantMembership.objects.filter(user__in=users).delete()
            deleted_counts['Tenant Memberships'] = count
        except LookupError:
            pass

        # 2. Delete Invitations (sent by these users)
        try:
            Invitation = apps.get_model('tenants', 'Invitation')
            count, _ = Invitation.objects.filter(invited_by__in=users).delete()
            deleted_counts['Invitations (sent)'] = count
        except LookupError:
            pass

        # 3. Delete Invitations (received by these users)
        try:
            Invitation = apps.get_model('tenants', 'Invitation')
            count, _ = Invitation.objects.filter(email__in=users.values_list('email', flat=True)).delete()
            deleted_counts['Invitations (received)'] = count
        except LookupError:
            pass

        # 4. Delete HR Employees
        try:
            Employee = apps.get_model('hr', 'Employee')
            count, _ = Employee.objects.filter(user__in=users).delete()
            deleted_counts['HR Employees'] = count
        except LookupError:
            pass

        # 5. Delete User Permissions
        try:
            UserPermission = apps.get_model('users', 'UserPermission')
            count, _ = UserPermission.objects.filter(user__in=users).delete()
            deleted_counts['User Permissions'] = count
        except LookupError:
            pass

        # 6. Delete Audit Logs
        try:
            AuditLog = apps.get_model('users', 'AuditLog')
            count, _ = AuditLog.objects.filter(user__in=users).delete()
            deleted_counts['Audit Logs'] = count
        except LookupError:
            pass

        # 7. Delete Tenants created by these users (CASCADE will handle related data)
        try:
            Tenant = apps.get_model('tenants', 'Tenant')
            tenants_to_delete = Tenant.objects.filter(created_by__in=users)
            tenant_count = tenants_to_delete.count()
            
            # This will cascade delete all related data (products, orders, etc.)
            tenants_to_delete.delete()
            deleted_counts['Tenants (and all related data)'] = tenant_count
        except LookupError:
            pass

        # 8. Finally, delete the users themselves
        user_count = users.count()
        users.delete()
        deleted_counts['Users'] = user_count

        return deleted_counts
