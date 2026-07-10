"""Run scheduled business alert scans for all tenants."""

from django.core.management.base import BaseCommand

from tenants.models import Tenant
from users.business_alerts import process_tenant_business_alerts


class Command(BaseCommand):
    help = 'Scan tenants and create in-app/email alerts for stock, payments, purchases, and expiry.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-id',
            type=int,
            help='Limit scan to a single tenant ID',
        )

    def handle(self, *args, **options):
        tenant_id = options.get('tenant_id')
        tenants = Tenant.objects.all()
        if tenant_id:
            tenants = tenants.filter(id=tenant_id)

        total = {'low_stock': 0, 'payment_reminders': 0, 'purchase_reminders': 0, 'expiry_alerts': 0}
        for tenant in tenants:
            results = process_tenant_business_alerts(tenant)
            for key, value in results.items():
                total[key] += value
            self.stdout.write(
                self.style.SUCCESS(
                    f"Tenant {tenant.id} ({tenant.name}): "
                    f"low_stock={results['low_stock']}, payments={results['payment_reminders']}, "
                    f"purchases={results['purchase_reminders']}, expiry={results['expiry_alerts']}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                'Done. Totals — '
                f"low_stock={total['low_stock']}, payments={total['payment_reminders']}, "
                f"purchases={total['purchase_reminders']}, expiry={total['expiry_alerts']}"
            )
        )
