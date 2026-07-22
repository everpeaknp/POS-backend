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
