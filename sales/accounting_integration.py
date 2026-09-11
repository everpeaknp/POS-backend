"""Sales ↔ accounting GL integration."""

from decimal import Decimal

from accounting.services import (
    record_cash_sale,
    record_credit_sale,
    record_payment_from_customer,
    record_sales_credit_note,
    record_cogs,
    reverse_cogs,
)


def post_sales_invoice(invoice):
    """Post sales invoice revenue to GL."""
    if not invoice.amount or Decimal(str(invoice.amount)) <= 0:
        return None
    tax_amount = None
    if invoice.sales_order_id:
        tax_amount = invoice.sales_order.tax
    if invoice.payment_type == 'cash':
        return record_cash_sale(
            invoice.amount,
            invoice.invoice_number,
            invoice.customer.name,
            tenant=invoice.tenant,
            tax_amount=tax_amount,
        )
    return record_credit_sale(
        invoice.customer,
        invoice.amount,
        invoice.invoice_number,
        tenant=invoice.tenant,
        tax_amount=tax_amount,
    )


def post_invoice_payment(invoice, payment_amount):
    """Post customer payment against invoice to GL."""
    payment_amount = Decimal(str(payment_amount))
    if payment_amount <= 0:
        return None
    reference = f"SI-PAY-{invoice.invoice_number}-{invoice.paid_amount}"
    return record_payment_from_customer(
        invoice.customer,
        payment_amount,
        reference,
        tenant=invoice.tenant,
    )


def post_payment_received(payment):
    """Post standalone customer payment to GL."""
    # Determine the account to debit based on payment_method_ref or fallback to Cash
    if hasattr(payment, 'payment_method_ref') and payment.payment_method_ref:
        cash_account = payment.payment_method_ref.linked_account
    else:
        # Fallback to default Cash account for backward compatibility
        from accounting.services import get_cash_account
        cash_account = get_cash_account(payment.tenant)
    
    # Create journal entry manually to use the specific account
    from accounting.services import create_journal_entry, get_accounts_receivable_account, has_posted_journal
    
    reference = payment.payment_number
    if has_posted_journal(payment.tenant, reference, 'Receipt'):
        return None
    
    amount = Decimal(str(payment.amount))
    
    return create_journal_entry(
        tenant=payment.tenant,
        description=f"Payment from {payment.customer.name}",
        reference=reference,
        entry_type='Receipt',
        entries=[
            {
                'account': cash_account,  # Use payment method's linked account
                'debit': amount,
                'credit': 0,
                'description': f"Payment from {payment.customer.name}"
            },
            {
                'account': get_accounts_receivable_account(payment.tenant),
                'debit': 0,
                'credit': amount,
                'description': f"Receivable from {payment.customer.name}"
            }
        ]
    )


def post_sales_credit_note(credit_note):
    """Post sales credit note to GL."""
    return record_sales_credit_note(
        credit_note.customer,
        credit_note.amount,
        credit_note.credit_note_number,
        tenant=credit_note.tenant,
    )


def _sales_order_cogs_total(sales_order):
    from decimal import Decimal
    total = Decimal('0')
    for line in sales_order.lines.select_related('product'):
        cost = line.product.cost_price or Decimal('0')
        total += Decimal(str(line.quantity)) * Decimal(str(cost))
    return total


def post_sales_order_revenue(sales_order):
    """
    Post sales revenue to GL when a sales order is fulfilled.
    Cash orders: revenue on confirm/deliver.
    Credit orders: revenue is posted via finalize_on_credit() only.
    """
    total = Decimal(str(sales_order.total or 0))
    if total <= 0:
        return None
    if sales_order.payment_type != 'cash':
        return None
    return record_cash_sale(
        total,
        sales_order.order_number,
        sales_order.customer.name,
        tenant=sales_order.tenant,
        tax_amount=sales_order.tax,
    )


def reverse_sales_order_revenue(sales_order):
    """Reverse GL revenue when a fulfilled sales order is cancelled."""
    from accounting.services import (
        create_journal_entry,
        get_accounts_receivable_account,
        get_cash_account,
        get_sales_revenue_account,
        has_posted_journal,
    )

    reference = sales_order.order_number
    reversal_ref = f"{reference}-REV"
    tenant = sales_order.tenant

    if not has_posted_journal(tenant, reference, 'Sales'):
        return None
    if has_posted_journal(tenant, reversal_ref, 'Sales'):
        return None

    total = Decimal(str(sales_order.total or 0))
    if total <= 0:
        return None

    if sales_order.payment_type == 'cash':
        cash_account = get_cash_account(tenant)
        revenue_account = get_sales_revenue_account(tenant)
        entries = [
            {
                'account': revenue_account,
                'debit': total,
                'credit': 0,
                'description': f"Reverse sale {reference}",
            },
            {
                'account': cash_account,
                'debit': 0,
                'credit': total,
                'description': f"Reverse cash sale {reference}",
            },
        ]
    else:
        ar_account = get_accounts_receivable_account(tenant)
        revenue_account = get_sales_revenue_account(tenant)
        entries = [
            {
                'account': revenue_account,
                'debit': total,
                'credit': 0,
                'description': f"Reverse credit sale {reference}",
            },
            {
                'account': ar_account,
                'debit': 0,
                'credit': total,
                'description': f"Reverse AR for {reference}",
            },
        ]

    return create_journal_entry(
        tenant=tenant,
        description=f"Reverse sales order {reference}",
        reference=reversal_ref,
        entry_type='Sales',
        entries=entries,
    )


def post_sales_order_cogs(sales_order):
    """Post COGS when a sales order consumes inventory."""
    total_cogs = _sales_order_cogs_total(sales_order)
    return record_cogs(
        total_cogs,
        f"COGS-{sales_order.order_number}",
        f"COGS for sales order {sales_order.order_number}",
        tenant=sales_order.tenant,
    )


def reverse_sales_order_cogs(sales_order):
    total_cogs = _sales_order_cogs_total(sales_order)
    return reverse_cogs(
        total_cogs,
        f"COGS-{sales_order.order_number}",
        f"Reverse COGS for cancelled order {sales_order.order_number}",
        tenant=sales_order.tenant,
    )


def post_pos_sale(transaction, lines_with_products):
    """
    Post POS revenue and COGS.
    lines_with_products: iterable of objects with .product and .quantity
    
    Payment Method Integration:
    - eSewa/Khalti/FonePay: Requires a BankAccount with the corresponding wallet enabled
      (esewa_enabled/khalti_enabled/fonepay_enabled = True). If found, updates that bank
      account's balance and creates a BankTransaction record.
    - Bank Transfer: Uses the first active BankAccount found. Updates balance and creates
      BankTransaction record.
    - If no matching BankAccount exists for digital wallets/bank transfer, falls back to
      default Cash account (does NOT auto-create bank accounts - user must set up first).
    """
    # Ensure an open fiscal year exists before posting
    from accounting.fiscal_services import ensure_fiscal_year
    ensure_fiscal_year(transaction.tenant)
    
    # Determine the account to debit based on payment method
    cash_account = None
    
    # Handle CASH payments separately - update user's CashAccount
    if transaction.payment_method == 'cash' and transaction.cashier:
        from accounting.models import CashAccount, CashTransaction
        from django.db import transaction as db_transaction
        from django.db.models import F
        from django.utils import timezone
        
        # Get or create cash account for this cashier
        cash_account_obj, created = CashAccount.objects.get_or_create(
            tenant=transaction.tenant,
            user=transaction.cashier,
            defaults={'balance': Decimal('0.00')}
        )
        
        # Atomically update balance and create transaction record
        with db_transaction.atomic():
            # Lock the cash account row for update
            cash_account_obj = CashAccount.objects.select_for_update().get(pk=cash_account_obj.pk)
            
            # Calculate new balance for the transaction record
            new_balance = cash_account_obj.balance + transaction.total
            
            try:
                # Create cash transaction record
                CashTransaction.objects.create(
                    tenant=transaction.tenant,
                    cash_account=cash_account_obj,
                    date=transaction.date.date() if hasattr(transaction.date, 'date') else transaction.date,
                    reference=transaction.transaction_number,
                    description=f'POS Sale via Cash',
                    type='Credit',
                    debit=Decimal('0.00'),
                    credit=transaction.total,
                    balance=new_balance,
                )
                # Update cash account balance using F() expression
                CashAccount.objects.filter(pk=cash_account_obj.pk).update(
                    balance=F('balance') + transaction.total,
                    updated_at=timezone.now()
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f'Failed to create cash transaction: {e}')
                raise
        
        # Still use GL Cash account for journal entries (existing behavior)
        from accounting.services import get_cash_account
        cash_account = get_cash_account(transaction.tenant)
    # Check if payment_method_ref is set (new payment method system)
    elif hasattr(transaction, 'payment_method_ref') and transaction.payment_method_ref:
        cash_account = transaction.payment_method_ref.linked_account
    # Check if it's a digital wallet payment (eSewa/Khalti/FonePay) or bank transfer
    elif transaction.payment_method in ['esewa', 'khalti', 'fonepay', 'bank_transfer', 'card']:
        from accounting.models import BankAccount
        
        bank_account = None
        
        # For digital wallets, find account with that wallet enabled
        if transaction.payment_method in ['esewa', 'khalti', 'fonepay']:
            wallet_field_map = {
                'esewa': 'esewa_enabled',
                'khalti': 'khalti_enabled',
                'fonepay': 'fonepay_enabled',
            }
            field_name = wallet_field_map.get(transaction.payment_method)
            if field_name:
                bank_account = BankAccount.objects.filter(
                    tenant=transaction.tenant,
                    status='active',
                    **{field_name: True}
                ).first()
        
        # For bank_transfer, check if POSSettings has a linked bank account, otherwise use any active account
        elif transaction.payment_method in ['bank_transfer', 'card']:
            # Try to get the linked bank account from POS Settings first
            from pos.models import POSSettings
            pos_settings = POSSettings.get_for_tenant(transaction.tenant)
            
            if pos_settings.linked_bank_account and pos_settings.linked_bank_account.status == 'active':
                bank_account = pos_settings.linked_bank_account
            else:
                # Fallback to first active bank account
                bank_account = BankAccount.objects.filter(
                    tenant=transaction.tenant,
                    status='active'
                ).first()
        
        if bank_account:
            if bank_account.gl_account:
                cash_account = bank_account.gl_account
            
            # Record in bank transactions and update balance
            from accounting.models import BankTransaction
            from django.utils import timezone
            try:
                BankTransaction.objects.create(
                    tenant=transaction.tenant,
                    bank_account=bank_account,
                    date=transaction.date.date() if hasattr(transaction.date, 'date') else transaction.date,
                    reference=transaction.transaction_number,
                    description=f'POS Sale via {transaction.payment_method.replace("_", " ").title()}',
                    type='Credit',
                    debit=Decimal('0.00'),
                    credit=transaction.total,
                    balance=bank_account.balance + transaction.total,
                    reconciled=False,
                )
                # Update bank account balance
                bank_account.balance += transaction.total
                bank_account.save(update_fields=['balance', 'updated_at'])
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f'Failed to create bank transaction: {e}')
    
    # Fallback to default Cash account if no specific account found
    if not cash_account:
        from accounting.services import get_cash_account
        cash_account = get_cash_account(transaction.tenant)
    
    if transaction.payment_method == 'credit' and getattr(transaction, 'customer', None):
        record_credit_sale(
            transaction.customer,
            transaction.total,
            transaction.transaction_number,
            tenant=transaction.tenant,
            tax_amount=transaction.tax_amount,
        )
    else:
        # Use the determined cash account instead of always using default Cash
        from accounting.services import create_journal_entry, get_sales_revenue_account, get_vat_payable_account
        
        tax_amount = transaction.tax_amount or Decimal('0')
        gross_amount = transaction.total
        net_amount = gross_amount - tax_amount
        
        entries = [
            {
                'account': cash_account,  # Use payment method's linked account
                'debit': gross_amount,
                'credit': 0,
                'description': f'Cash received for {transaction.transaction_number}',
            },
            {
                'account': get_sales_revenue_account(transaction.tenant),
                'debit': 0,
                'credit': net_amount,
                'description': f'Sales revenue for {transaction.transaction_number}',
            },
        ]
        
        if tax_amount > 0:
            entries.append({
                'account': get_vat_payable_account(transaction.tenant),
                'debit': 0,
                'credit': tax_amount,
                'description': f'VAT on {transaction.transaction_number}',
            })
        
        create_journal_entry(
            reference=transaction.transaction_number,
            description=f'POS Sale - {transaction.customer.name if getattr(transaction, "customer", None) else "Walk-in Customer"}',
            entry_type='Sales',
            tenant=transaction.tenant,
            entries=entries,
        )

    total_cogs = Decimal('0')
    for line in lines_with_products:
        product = line.product
        cost = product.cost_price or Decimal('0')
        total_cogs += Decimal(str(line.quantity)) * Decimal(str(cost))

    record_cogs(
        total_cogs,
        f"COGS-{transaction.transaction_number}",
        f"COGS for POS {transaction.transaction_number}",
        tenant=transaction.tenant,
    )


def _pos_cogs_total(lines_with_products):
    total_cogs = Decimal('0')
    for line in lines_with_products:
        product = line.product
        cost = product.cost_price or Decimal('0')
        total_cogs += Decimal(str(line.quantity)) * Decimal(str(cost))
    return total_cogs


def reverse_pos_sale(transaction, lines_with_products):
    """Reverse GL revenue and COGS when a POS transaction is cancelled."""
    from accounting.services import (
        create_journal_entry,
        get_accounts_receivable_account,
        get_cash_account,
        get_sales_revenue_account,
        has_posted_journal,
    )

    reference = transaction.transaction_number
    reversal_ref = f"{reference}-REV"
    tenant = transaction.tenant

    if has_posted_journal(tenant, reference, 'Sales') and not has_posted_journal(
        tenant, reversal_ref, 'Sales'
    ):
        total = Decimal(str(transaction.total or 0))
        if total > 0:
            revenue_account = get_sales_revenue_account(tenant)
            if transaction.payment_method == 'credit' and transaction.customer:
                ar_account = get_accounts_receivable_account(tenant)
                entries = [
                    {
                        'account': revenue_account,
                        'debit': total,
                        'credit': 0,
                        'description': f"Reverse POS sale {reference}",
                    },
                    {
                        'account': ar_account,
                        'debit': 0,
                        'credit': total,
                        'description': f"Reverse AR for POS {reference}",
                    },
                ]
            else:
                cash_account = get_cash_account(tenant)
                entries = [
                    {
                        'account': revenue_account,
                        'debit': total,
                        'credit': 0,
                        'description': f"Reverse POS sale {reference}",
                    },
                    {
                        'account': cash_account,
                        'debit': 0,
                        'credit': total,
                        'description': f"Reverse cash POS sale {reference}",
                    },
                ]
            create_journal_entry(
                tenant=tenant,
                description=f"Reverse POS transaction {reference}",
                reference=reversal_ref,
                entry_type='Sales',
                entries=entries,
            )

    total_cogs = _pos_cogs_total(lines_with_products)
    reverse_cogs(
        total_cogs,
        f"COGS-{reference}",
        f"Reverse COGS for cancelled POS {reference}",
        tenant=tenant,
    )
