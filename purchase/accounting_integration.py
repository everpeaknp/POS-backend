"""Purchase ↔ accounting GL integration."""

from decimal import Decimal

from accounting.services import (
    record_purchase,
    record_payment_to_supplier,
    record_purchase_debit_note,
)


def post_purchase_invoice(invoice):
    """Post purchase bill to GL when invoice is recorded."""
    if not invoice.amount or Decimal(str(invoice.amount)) <= 0:
        return None
    return record_purchase(
        invoice.supplier,
        invoice.amount,
        invoice.invoice_number,
        tenant=invoice.tenant,
    )


def post_purchase_invoice_payment(invoice, payment_amount):
    """Post supplier payment to GL."""
    payment_amount = Decimal(str(payment_amount))
    if payment_amount <= 0:
        return None
    reference = f"PI-PAY-{invoice.invoice_number}-{invoice.paid_amount}"
    return record_payment_to_supplier(
        invoice.supplier,
        payment_amount,
        reference,
        tenant=invoice.tenant,
    )


def post_purchase_debit_note(debit_note):
    """Post purchase debit note to GL."""
    return record_purchase_debit_note(
        debit_note.supplier,
        debit_note.amount,
        debit_note.debit_note_number,
        tenant=debit_note.tenant,
    )
