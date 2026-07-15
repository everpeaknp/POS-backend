"""
Management command: fix_payroll_gl
-----------------------------------
Finds all HR Payroll journal entries that incorrectly credited
'Wages Payable' (2100) instead of 'Salary Payable' (2200),
reverses them, and re-posts them with the correct accounts.

Usage:
    python manage.py fix_payroll_gl            # dry run (shows what would change)
    python manage.py fix_payroll_gl --apply    # actually fixes the entries
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Fix HR payroll GL entries that incorrectly used Wages Payable instead of Salary Payable'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually apply the fix (default is dry-run)',
        )

    def handle(self, *args, **options):
        from accounting.models import JournalEntry, Account
        from accounting.services import (
            get_salary_payable_account,
            get_or_create_account,
            apply_entry_balances,
        )

        apply = options['apply']
        mode = 'APPLYING' if apply else 'DRY RUN'
        self.stdout.write(f'\n=== fix_payroll_gl [{mode}] ===\n')

        # Find all posted Payroll entries
        payroll_entries = JournalEntry.objects.filter(
            type='Payroll',
            status='posted',
        ).prefetch_related('lines__account')

        fixed = 0
        skipped = 0

        for entry in payroll_entries:
            # Check if any line credits Wages Payable (2100)
            bad_lines = [
                line for line in entry.lines.all()
                if line.account.code == '2100' and line.credit > 0
            ]

            if not bad_lines:
                skipped += 1
                continue

            self.stdout.write(
                f'  Entry {entry.entry_number} | {entry.description} | '
                f'Tenant: {entry.tenant} | Amount: {bad_lines[0].credit}'
            )

            if not apply:
                fixed += 1
                continue

            with transaction.atomic():
                tenant = entry.tenant

                # Get correct Salary Payable account (creates if missing)
                salary_payable = get_salary_payable_account(tenant)

                # Get old Wages Payable account
                try:
                    wages_payable = Account._base_manager.get(tenant=tenant, code='2100')
                except Account.DoesNotExist:
                    self.stdout.write(self.style.WARNING(
                        f'    Skipping — Wages Payable (2100) not found for tenant {tenant}'
                    ))
                    continue

                # Step 1: Reverse account balances from the bad entry
                for line in entry.lines.all():
                    acc = line.account
                    if acc.type in ['Assets', 'Expense']:
                        acc.balance -= (line.debit - line.credit)
                    else:
                        acc.balance -= (line.credit - line.debit)
                    acc.save()

                # Step 2: Swap the bad credit lines from 2100 → 2200
                for line in bad_lines:
                    line.account = salary_payable
                    line.description = (
                        line.description
                        .replace('Wages payable', 'Salary payable')
                        .replace('Wage payable', 'Salary payable')
                    )
                    line.save()

                # Step 3: Re-apply correct balances
                entry.refresh_from_db()
                apply_entry_balances(entry)

                self.stdout.write(self.style.SUCCESS(
                    f'    ✓ Fixed → now credits Salary Payable (2200)'
                ))
                fixed += 1

        self.stdout.write(
            f'\nResult: {fixed} entries {"fixed" if apply else "would be fixed"}, '
            f'{skipped} already correct.\n'
        )

        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    'This was a DRY RUN. Run with --apply to actually fix the entries.\n'
                )
            )
