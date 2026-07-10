"""VAT calculation helpers — configurable via TaxRule."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from accounting.models import TaxRule


def get_active_vat_rate(tenant, *, applicable_on: str = 'Sales') -> Decimal:
    """Return active VAT percentage for tenant (default 13% Nepal standard)."""
    rule = (
        TaxRule.objects.filter(
            tenant=tenant,
            type='VAT',
            status='active',
        )
        .filter(applicable_on__in=[applicable_on, 'Both'])
        .order_by('-rate')
        .first()
    )
    if rule:
        return Decimal(str(rule.rate))
    return Decimal('13.00')


def split_tax_inclusive_amount(
    gross: Decimal | float | str,
    *,
    tax_amount: Decimal | float | str | None = None,
    tenant=None,
    applicable_on: str = 'Sales',
) -> tuple[Decimal, Decimal]:
    """
    Split a tax-inclusive gross amount into net and VAT.
    Uses explicit tax when provided; otherwise derives from active TaxRule.
    """
    gross_dec = Decimal(str(gross or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if gross_dec <= 0:
        return Decimal('0.00'), Decimal('0.00')

    if tax_amount is not None:
        tax_dec = Decimal(str(tax_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        tax_dec = min(tax_dec, gross_dec)
        return gross_dec - tax_dec, tax_dec

    if tenant is None:
        rate = Decimal('13.00')
    else:
        rate = get_active_vat_rate(tenant, applicable_on=applicable_on)

    if rate <= 0:
        return gross_dec, Decimal('0.00')

    tax_dec = (gross_dec * rate / (Decimal('100') + rate)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    return gross_dec - tax_dec, tax_dec
