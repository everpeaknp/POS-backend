"""POS helpers for stock, tax, and amount calculations."""

from decimal import Decimal, ROUND_HALF_UP

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


def compute_pos_amounts(lines_data, total_discount_amount):
    """Recalculate subtotal, tax, and total from line items (13% VAT)."""
    subtotal = sum(
        quantize_money(line['quantity'] * line['unit_price'])
        for line in lines_data
    )
    total_discount = quantize_money(total_discount_amount or 0)
    if total_discount > subtotal:
        raise ValueError('Discount cannot exceed subtotal')
    net = subtotal - total_discount
    tax_amount = quantize_money(net * POS_VAT_RATE)
    total = net + tax_amount
    return {
        'subtotal': subtotal,
        'discount_amount': total_discount,
        'tax_amount': tax_amount,
        'total': total,
    }
