"""POS helpers for stock, tax, and amount calculations."""

from decimal import Decimal, ROUND_HALF_UP

# Legacy constant kept for backward compatibility / tests
POS_VAT_RATE = Decimal('0.13')


def quantize_money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def get_warehouse_stock(product, warehouse):
    """Return available quantity for a product at a specific warehouse."""
    if not warehouse:
        return product.get_total_stock()
    from inventory.models import Stock

    stock = Stock.objects.filter(
        tenant=product.tenant,
        product=product,
        warehouse=warehouse,
    ).first()
    return stock.quantity if stock else Decimal('0.00')


def get_tenant_tax_rate(tenant):
    """Return the configured tax rate for a tenant (as a Decimal, e.g. 0.13)."""
    from .models import POSSettings
    settings = POSSettings.get_for_tenant(tenant)
    return settings.tax_rate / Decimal('100')


def compute_pos_amounts(lines_data, total_discount_amount, tax_rate=None):
    """Recalculate subtotal, tax, and total from line items.

    Args:
        lines_data: list of line dicts with 'quantity' and 'unit_price'.
        total_discount_amount: bill-level discount amount.
        tax_rate: Decimal tax rate (e.g. 0.13 for 13%).
                  Falls back to POS_VAT_RATE if not supplied.
    """
    if tax_rate is None:
        tax_rate = POS_VAT_RATE

    subtotal = sum(
        quantize_money(line['quantity'] * line['unit_price'])
        for line in lines_data
    )
    total_discount = quantize_money(total_discount_amount or 0)
    if total_discount > subtotal:
        raise ValueError('Discount cannot exceed subtotal')
    net = subtotal - total_discount
    tax_amount = quantize_money(net * tax_rate)
    total = net + tax_amount
    return {
        'subtotal': subtotal,
        'discount_amount': total_discount,
        'tax_amount': tax_amount,
        'total': total,
    }


def get_transaction_line_totals_sum(transaction):
    """Sum of line totals for a transaction (after line-level discounts)."""
    return sum(
        (line.line_total or Decimal('0.00') for line in transaction.lines.all()),
        Decimal('0.00'),
    )


def compute_refund_tax_amount(transaction, subtotal_refund):
    """Proportional tax for a refund subtotal based on the original sale."""
    line_totals_sum = get_transaction_line_totals_sum(transaction)
    if line_totals_sum <= 0 or subtotal_refund <= 0:
        return Decimal('0.00')
    return quantize_money(subtotal_refund / line_totals_sum * transaction.tax_amount)


def compute_line_refund_discount(line, refund_quantity):
    """Discount portion reversed for a partial line refund."""
    refund_quantity = Decimal(str(refund_quantity))
    if line.quantity <= 0:
        return Decimal('0.00')
    per_unit = Decimal(str(line.discount_amount or 0)) / line.quantity
    return quantize_money(per_unit * refund_quantity)


def compute_refund_preview(transaction, line_quantities):
    """
    Preview refund totals for a transaction.

    line_quantities: iterable of (POSTransactionLine, quantity) pairs.
    """
    items_returned = Decimal('0.00')
    subtotal_refund = Decimal('0.00')
    discount_refund = Decimal('0.00')
    line_details = []

    for line, qty in line_quantities:
        qty = Decimal(str(qty))
        if qty <= 0:
            continue
        line_subtotal = line.get_refund_amount(qty)
        line_discount = compute_line_refund_discount(line, qty)
        items_returned += qty
        subtotal_refund += line_subtotal
        discount_refund += line_discount
        line_details.append({
            'line': line,
            'quantity': qty,
            'subtotal': line_subtotal,
            'discount': line_discount,
        })

    subtotal_refund = quantize_money(subtotal_refund)
    discount_refund = quantize_money(discount_refund)
    tax_refund = compute_refund_tax_amount(transaction, subtotal_refund)
    total_refund = quantize_money(subtotal_refund + tax_refund)

    return {
        'items_returned': items_returned,
        'subtotal_refund': subtotal_refund,
        'tax_refund': tax_refund,
        'discount_refund': discount_refund,
        'total_refund': total_refund,
        'line_details': line_details,
    }


def get_transaction_refunded_subtotal(transaction):
    """Total refunded subtotal (pre-tax) across all refunds for a transaction."""
    from django.db.models import Sum
    from .models import POSRefundLine

    result = POSRefundLine.objects.filter(
        refund__original_transaction=transaction,
    ).aggregate(total=Sum('refund_amount'))
    return result['total'] or Decimal('0.00')


def get_transaction_refund_summary(transaction):
    """Summary of original sale vs refunded vs remaining refundable amounts."""
    refunded_subtotal = get_transaction_refunded_subtotal(transaction)
    refunded_tax = compute_refund_tax_amount(transaction, refunded_subtotal)
    total_refunded = quantize_money(refunded_subtotal + refunded_tax)
    remaining = quantize_money(max(transaction.total - total_refunded, Decimal('0.00')))
    return {
        'original_sale': transaction.total,
        'total_refunded': total_refunded,
        'remaining_refundable': remaining,
        'refunded_subtotal': quantize_money(refunded_subtotal),
        'refunded_tax': refunded_tax,
    }
