"""Accounting helpers — entry numbers, VAT, and bank reconciliation."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounting.models import Account, BankTransaction, JournalEntry, JournalLine, TaxRule


def generate_entry_number(tenant) -> str:
    """Sequential JE number shared by manual and auto-posted entries."""
    last_entry = JournalEntry.objects.filter(tenant=tenant).order_by('-id').first()
    if last_entry and last_entry.entry_number.startswith('JE-'):
        try:
            last_num = int(last_entry.entry_number.split('-')[1])
            return f'JE-{last_num + 1:04d}'
        except (ValueError, IndexError):
            pass
    return 'JE-0001'


def get_vat_payable_account(tenant):
    from accounting.services import get_or_create_account

    account = Account._base_manager.filter(tenant=tenant, code='2200').first()
    if account:
        return account
    return get_or_create_account('2200', 'VAT Payable', 'liability', tenant)


def _vat_account_ids(tenant) -> set:
    account_ids = set(
        TaxRule.objects.filter(tenant=tenant, type='VAT', status='active').values_list(
            'account_id', flat=True
        )
    )
    default_vat = Account._base_manager.filter(tenant=tenant, code='2200').first()
    if default_vat:
        account_ids.add(default_vat.id)
    return account_ids


def calculate_vat_for_period(tenant, from_date, to_date) -> dict:
    """
    Derive output/input VAT from posted journal lines on VAT liability accounts.
    Excludes VAT payment journals (reference VAT-PAY-*).
    """
    account_ids = _vat_account_ids(tenant)
    if not account_ids:
        return {
            'output_tax': Decimal('0.00'),
            'input_tax': Decimal('0.00'),
            'net_payable': Decimal('0.00'),
        }

    lines = JournalLine.objects.filter(
        tenant=tenant,
        account_id__in=account_ids,
        journal_entry__status='posted',
        journal_entry__date__gte=from_date,
        journal_entry__date__lte=to_date,
    ).exclude(journal_entry__reference__startswith='VAT-PAY-')

    aggregates = lines.aggregate(
        total_credit=Sum('credit'),
        total_debit=Sum('debit'),
    )
    output_tax = aggregates['total_credit'] or Decimal('0.00')
    input_tax = aggregates['total_debit'] or Decimal('0.00')
    net_payable = output_tax - input_tax

    return {
        'output_tax': output_tax,
        'input_tax': input_tax,
        'net_payable': net_payable,
    }


def record_vat_payment(vat_return, tenant):
    """Post GL for VAT remittance when a return is marked paid."""
    from accounting.services import create_journal_entry, get_cash_account, has_posted_journal

    reference = f'VAT-PAY-{vat_return.return_number}'
    if has_posted_journal(tenant, reference, 'Payment'):
        return None

    amount = Decimal(str(vat_return.net_payable))
    if amount <= 0:
        return None

    vat_account = get_vat_payable_account(tenant)
    cash_account = get_cash_account(tenant)

    return create_journal_entry(
        tenant=tenant,
        description=f'VAT payment — {vat_return.period}',
        reference=reference,
        date=vat_return.paid_date or timezone.now().date(),
        entry_type='Payment',
        entries=[
            {'account': vat_account, 'debit': amount, 'credit': Decimal('0')},
            {'account': cash_account, 'debit': Decimal('0'), 'credit': amount},
        ],
    )


def create_bank_reconciliation_adjustment(bank_account, difference: Decimal, tenant, user=None):
    """
    Post an adjusting journal when book and statement balances differ.
    Positive difference => increase book (Dr bank GL, Cr other income).
    Negative difference => decrease book (Dr bank charges, Cr bank GL).
    """
    from accounting.services import create_journal_entry, get_or_create_account

    amount = abs(difference)
    if amount < Decimal('0.01'):
        return None

    gl_account = bank_account.gl_account
    reference = f'BANK-RECON-{bank_account.id}-{timezone.now().date().isoformat()}'

    if difference > 0:
        other_income = get_or_create_account('4100', 'Other Income', 'revenue', tenant)
        entries = [
            {'account': gl_account, 'debit': amount, 'credit': Decimal('0')},
            {'account': other_income, 'debit': Decimal('0'), 'credit': amount},
        ]
        description = f'Bank reconciliation adjustment — {bank_account.account_name}'
    else:
        bank_charges = get_or_create_account('5450', 'Bank Charges', 'expense', tenant)
        entries = [
            {'account': bank_charges, 'debit': amount, 'credit': Decimal('0')},
            {'account': gl_account, 'debit': Decimal('0'), 'credit': amount},
        ]
        description = f'Bank reconciliation adjustment — {bank_account.account_name}'

    entry = create_journal_entry(
        tenant=tenant,
        description=description,
        reference=reference,
        entry_type='Adjustment',
        entries=entries,
    )

    last_tx = (
        BankTransaction.objects.filter(bank_account=bank_account)
        .order_by('-date', '-id')
        .first()
    )
    prev_balance = last_tx.balance if last_tx else bank_account.balance
    if difference > 0:
        new_balance = prev_balance + amount
        BankTransaction.objects.create(
            tenant=tenant,
            bank_account=bank_account,
            date=timezone.now().date(),
            reference=reference,
            description=description,
            type='Credit',
            debit=Decimal('0'),
            credit=amount,
            balance=new_balance,
            reconciled=True,
            reconciled_date=timezone.now().date(),
            journal_entry=entry,
        )
    else:
        new_balance = prev_balance - amount
        BankTransaction.objects.create(
            tenant=tenant,
            bank_account=bank_account,
            date=timezone.now().date(),
            reference=reference,
            description=description,
            type='Debit',
            debit=amount,
            credit=Decimal('0'),
            balance=new_balance,
            reconciled=True,
            reconciled_date=timezone.now().date(),
            journal_entry=entry,
        )

    bank_account.balance = new_balance
    bank_account.last_reconciled = timezone.now().date()
    bank_account.save(update_fields=['balance', 'last_reconciled', 'updated_at'])
    return entry


@transaction.atomic
def complete_bank_reconciliation(
    bank_account,
    tenant,
    transaction_ids,
    statement_balance: Decimal,
    user=None,
):
    """Reconcile selected transactions and optionally post an adjusting entry."""
    txs = BankTransaction.objects.filter(
        tenant=tenant,
        bank_account=bank_account,
        id__in=transaction_ids,
        reconciled=False,
    )
    today = timezone.now().date()
    for tx in txs:
        tx.reconciled = True
        tx.reconciled_date = today
        tx.save(update_fields=['reconciled', 'reconciled_date', 'updated_at'])

    book_balance = bank_account.balance
    unreconciled = BankTransaction.objects.filter(
        tenant=tenant,
        bank_account=bank_account,
        reconciled=False,
    )
    add_credits = unreconciled.aggregate(t=Sum('credit'))['t'] or Decimal('0')
    add_debits = unreconciled.aggregate(t=Sum('debit'))['t'] or Decimal('0')
    adjusted_book = book_balance + add_credits - add_debits
    difference = adjusted_book - statement_balance

    adjustment_entry = None
    if abs(difference) >= Decimal('0.01'):
        adjustment_entry = create_bank_reconciliation_adjustment(
            bank_account, difference, tenant, user
        )
    else:
        bank_account.last_reconciled = today
        bank_account.save(update_fields=['last_reconciled', 'updated_at'])

    return {
        'reconciled_count': txs.count(),
        'adjusted_book': float(adjusted_book),
        'statement_balance': float(statement_balance),
        'difference': float(difference),
        'adjustment_entry_id': adjustment_entry.id if adjustment_entry else None,
    }
