from decimal import Decimal

from django.db import migrations, transaction


def separate_payroll_and_vat_liabilities(apps, schema_editor):
    """Keep construction wages, HR salaries, and VAT in separate accounts."""
    Account = apps.get_model('accounting', 'Account')
    JournalLine = apps.get_model('accounting', 'JournalLine')

    with transaction.atomic():
        tenant_ids = Account.objects.values_list('tenant_id', flat=True).distinct()
        for tenant_id in tenant_ids:
            # Legacy chart seeds used 2200 for VAT. Move only explicitly named
            # VAT accounts, so a correctly configured Salary Payable is preserved.
            old_vat = Account.objects.filter(
                tenant_id=tenant_id, code='2200', name__iexact='VAT Payable'
            ).first()
            if old_vat:
                new_vat = Account.objects.filter(tenant_id=tenant_id, code='2250').first()
                if new_vat:
                    JournalLine.objects.filter(account_id=old_vat.id).update(account_id=new_vat.id)
                    new_vat.balance += old_vat.balance
                    new_vat.save(update_fields=['balance'])
                    old_vat.delete()
                else:
                    old_vat.code = '2250'
                    old_vat.save(update_fields=['code'])

            salary, _ = Account.objects.get_or_create(
                tenant_id=tenant_id,
                code='2200',
                defaults={
                    'name': 'Salary Payable',
                    'type': 'Liabilities',
                    'sub_type': 'Payable',
                    'status': 'active',
                    'level': 0,
                },
            )
            wages = Account.objects.filter(tenant_id=tenant_id, code='2100').first()
            if not wages:
                continue

            bad_lines = JournalLine.objects.filter(
                account_id=wages.id,
                credit__gt=0,
                journal_entry__tenant_id=tenant_id,
                journal_entry__type='Payroll',
                journal_entry__status='posted',
            )
            amount = sum((line.credit for line in bad_lines), Decimal('0.00'))
            if not amount:
                continue
            bad_lines.update(account_id=salary.id)
            wages.balance -= amount
            wages.save(update_fields=['balance'])
            salary.balance += amount
            salary.save(update_fields=['balance'])


class Migration(migrations.Migration):
    dependencies = [('accounting', '0003_alter_account_sub_type_alter_fiscalyear_tenant')]

    operations = [
        migrations.RunPython(separate_payroll_and_vat_liabilities, migrations.RunPython.noop),
    ]
