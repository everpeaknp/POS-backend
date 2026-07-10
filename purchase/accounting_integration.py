"""Purchase ↔ accounting GL integration."""

from decimal import Decimal

from accounting.services import (
    record_purchase,
    record_payment_to_supplier,
    record_purchase_debit_note,
)


def post_purchase_invoice(invoice):
    """Post purchase bill to GL when invoice is recorded (net AP only)."""
    ap_amount = invoice._ap_amount()
    if ap_amount <= 0:
        return None
    tax_amount = None
    if invoice.purchase_order_id:
        tax_amount = invoice.purchase_order.tax
    return record_purchase(
        invoice.supplier,
        ap_amount,
        invoice.invoice_number,
        tenant=invoice.tenant,
        tax_amount=tax_amount,
    )


def post_purchase_invoice_payment(invoice, payment_amount, payment_id=None):
    """Post supplier payment to GL."""
    payment_amount = Decimal(str(payment_amount))
    if payment_amount <= 0:
        return None
    suffix = payment_id or invoice.paid_amount
    reference = f"PI-PAY-{invoice.invoice_number}-{suffix}"
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
