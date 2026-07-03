import inspect

from django.core.management.base import BaseCommand
from django.db.models import Count

from accounting.models import JournalEntry
from accounting import services as accounting_services
from tenants.models import Tenant


GL_FLOWS = [
    {
        'name': 'Material consumption',
        'reference_prefix': 'MC-',
        'entry_type': 'Construction',
        'function': 'record_material_consumption',
        'module': 'construction',
    },
    {
        'name': 'Labor wage (attendance)',
        'reference_prefix': 'ATT-',
        'entry_type': 'Construction',
        'function': 'record_labor_wage',
        'module': 'construction',
    },
    {
        'name': 'Equipment usage',
        'reference_prefix': 'EQ-',
        'entry_type': 'Construction',
        'function': 'record_equipment_usage',
        'module': 'construction',
    },
    {
        'name': 'Daily log other expense',
        'reference_prefix': 'DL-',
        'entry_type': 'Construction',
        'function': 'record_site_other_expense',
        'module': 'construction',
    },
    {
        'name': 'Credit sale (invoice / order)',
        'reference_prefix': '',
        'entry_type': 'Sales',
        'function': 'record_credit_sale',
        'module': 'sales',
    },
    {
        'name': 'Cash sale',
        'reference_prefix': '',
        'entry_type': 'Sales',
        'function': 'record_cash_sale',
        'module': 'sales',
    },
    {
        'name': 'Purchase invoice',
        'reference_prefix': '',
        'entry_type': 'Purchase',
        'function': 'record_purchase',
        'module': 'purchase',
    },
    {
        'name': 'HR payroll',
        'reference_prefix': 'PAY-',
        'entry_type': 'Payroll',
        'function': 'record_payroll_expense',
        'module': 'hr',
    },
]


class Command(BaseCommand):
    help = 'Verify GL integration wiring and report posted journal entry counts per flow.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-id', type=int, help='Limit journal counts to one tenant')
        parser.add_argument('--checklist', action='store_true', help='Print manual QA checklist')

    def handle(self, *args, **options):
        tenant_id = options.get('tenant_id')
        show_checklist = options.get('checklist', True)

        self.stdout.write(self.style.MIGRATE_HEADING('GL integration — service functions'))
        for flow in GL_FLOWS:
            fn_name = flow['function']
            fn = getattr(accounting_services, fn_name, None)
            if fn and callable(fn):
                self.stdout.write(self.style.SUCCESS(f'  [OK] {fn_name}() — {flow["name"]}'))
            else:
                self.stdout.write(self.style.ERROR(f'  [MISSING] {fn_name}() — {flow["name"]}'))

        idempotent = 'has_posted_journal' in inspect.getsource(accounting_services.record_material_consumption)
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS('  [OK] record_material_consumption idempotency guard')
            if idempotent
            else self.style.WARNING('  [WARN] record_material_consumption may lack idempotency guard')
        )

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Posted journal entries by type'))

        je_qs = JournalEntry.objects.filter(status='posted')
        if tenant_id:
            je_qs = je_qs.filter(tenant_id=tenant_id)
            try:
                tenant = Tenant.objects.get(id=tenant_id)
                self.stdout.write(f'Tenant: {tenant.name} (id={tenant_id})')
            except Tenant.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Tenant {tenant_id} not found'))
                return

        by_type = je_qs.values('type').annotate(count=Count('id')).order_by('type')
        if not by_type:
            self.stdout.write(self.style.WARNING('  No posted journal entries found.'))
        else:
            for row in by_type:
                self.stdout.write(f"  {row['type'] or 'Manual'}: {row['count']}")

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Construction reference samples (posted)'))
        for prefix in ['MC-', 'ATT-', 'EQ-', 'DL-']:
            count = je_qs.filter(reference__startswith=prefix).count()
            status = self.style.SUCCESS if count else self.style.WARNING
            self.stdout.write(status(f'  {prefix}*: {count} entries'))

        payroll_count = je_qs.filter(reference__startswith='PAY-').count()
        self.stdout.write(
            self.style.SUCCESS(f'  PAY-*: {payroll_count} entries')
            if payroll_count
            else self.style.WARNING(f'  PAY-*: {payroll_count} entries')
        )

        if show_checklist:
            self.stdout.write('')
            self.stdout.write(self.style.MIGRATE_HEADING('Manual end-to-end checklist (construction → accounting)'))
            steps = [
                '1. Construction → Material Consumption: log usage at a site → Journal Entry ref MC-* (Dr Construction Expense, Cr Inventory).',
                '2. Construction → Attendance: mark worker present → Journal Entry ref ATT-* (Dr Labor Expense, Cr Wages Payable).',
                '3. Construction → Equipment: log rented equipment hours → Journal Entry ref EQ-* (if cost > 0).',
                '4. Construction → Daily Log: add other expenses → Journal Entry ref DL-*.',
                '5. Accounting → Journal Entries: filter/search MC-, ATT-, EQ-, DL- references.',
                '6. Accounting → Profit & Loss: confirm construction/labor expense totals increased.',
                '7. Construction site budget vs Accounting P&L — budget includes labor; GL may differ until all flows post.',
                '8. Sales → credit order finalize → Sales-type journal (AR + Revenue).',
                '9. HR → Run payroll → PAY-* journal entries.',
            ]
            for step in steps:
                self.stdout.write(f'  {step}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Verification complete. Run with --tenant-id=N to scope counts.'))
