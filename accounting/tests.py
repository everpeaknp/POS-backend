from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from accounting.chart_seed import seed_default_chart_of_accounts
from accounting.models import Account, JournalEntry
from accounting.services import record_labor_wage, record_payroll_expense
from accounting.utils import get_vat_payable_account
from tenants.models import Tenant


class PayrollLiabilityClassificationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Payroll GL Test Tenant')

    def test_hr_payroll_uses_salary_payable_not_wages(self):
        employee = SimpleNamespace(name='HR Employee')

        entry = record_payroll_expense(
            employee, Decimal('1500.00'), 'PAY-test-1', date.today(), self.tenant
        )

        credit_line = entry.lines.model._base_manager.get(journal_entry=entry, credit__gt=0)
        self.assertEqual(entry.type, 'Payroll')
        self.assertEqual(credit_line.account.code, '2200')
        self.assertEqual(credit_line.account.name, 'Salary Payable')
        self.assertFalse(entry.lines.model._base_manager.filter(journal_entry=entry, account__code='2100').exists())

    def test_construction_wage_uses_wages_payable_not_salary(self):
        site = SimpleNamespace(name='Site A', cost_center_account=None)
        worker = SimpleNamespace(name='Construction Worker', category='laborer')

        entry = record_labor_wage(
            site, worker, Decimal('900.00'), date.today(), 'ATT-test-1', self.tenant
        )

        credit_line = entry.lines.model._base_manager.get(journal_entry=entry, credit__gt=0)
        self.assertEqual(entry.type, 'Construction')
        self.assertEqual(credit_line.account.code, '2100')
        self.assertEqual(credit_line.account.name, 'Wages Payable')
        self.assertFalse(entry.lines.model._base_manager.filter(journal_entry=entry, account__code='2200').exists())

    def test_chart_and_vat_account_do_not_conflict_with_salary_payable(self):
        seed_default_chart_of_accounts(self.tenant)

        self.assertEqual(Account._base_manager.get(tenant=self.tenant, code='2200').name, 'Salary Payable')
        self.assertEqual(get_vat_payable_account(self.tenant).code, '2250')
        self.assertEqual(JournalEntry._base_manager.filter(tenant=self.tenant).count(), 0)
