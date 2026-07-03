from django.core.management.base import BaseCommand

from tenants.models import Tenant
from users.permission_models import sync_tenant_permissions, RolePermission


class Command(BaseCommand):
    help = 'Backfill missing RolePermission rows for all tenants (fixes 403 after module permission rollout).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-id',
            type=int,
            help='Sync permissions for a single tenant only',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report tenants that would be synced without writing',
        )

    def handle(self, *args, **options):
        tenant_id = options.get('tenant_id')
        dry_run = options.get('dry_run')

        qs = Tenant.objects.filter(is_active=True)
        if tenant_id:
            qs = qs.filter(id=tenant_id)

        if not qs.exists():
            self.stdout.write(self.style.WARNING('No tenants matched.'))
            return

        total_created = 0
        for tenant in qs:
            before = RolePermission.objects.filter(tenant=tenant).count()
            if dry_run:
                self.stdout.write(f'[dry-run] Would sync tenant {tenant.id} ({tenant.name}) — {before} permissions now')
                continue
            created = sync_tenant_permissions(tenant)
            after = RolePermission.objects.filter(tenant=tenant).count()
            total_created += created
            self.stdout.write(
                self.style.SUCCESS(
                    f'Tenant {tenant.id} ({tenant.name}): {before} -> {after} permissions (+{created} new)'
                )
            )

        if dry_run:
            self.stdout.write(self.style.WARNING(f'Dry run complete for {qs.count()} tenant(s).'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Done. Added {total_created} permission row(s) across {qs.count()} tenant(s).'))
