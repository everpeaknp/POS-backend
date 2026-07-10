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
    return record_payment_from_customer(
        payment.customer,
        payment.amount,
        payment.payment_number,
        tenant=payment.tenant,
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
    """
    if transaction.payment_method == 'credit' and getattr(transaction, 'customer', None):
        record_credit_sale(
            transaction.customer,
            transaction.total,
            transaction.transaction_number,
            tenant=transaction.tenant,
            tax_amount=transaction.tax_amount,
        )
    else:
        record_cash_sale(
            transaction.total,
            transaction.transaction_number,
            transaction.customer.name if getattr(transaction, 'customer', None) else None,
            tenant=transaction.tenant,
            tax_amount=transaction.tax_amount,
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
