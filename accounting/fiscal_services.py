"""Fiscal year lifecycle — create, ensure, close."""

from __future__ import annotations

from django.utils import timezone

from accounting.fiscal_utils import bs_fiscal_label, bs_fiscal_year_ad_range, current_bs_fiscal_start_year
from accounting.models import FiscalYear


def ensure_fiscal_year(tenant, bs_start_year: int | None = None) -> FiscalYear:
    bs_start_year = bs_start_year or current_bs_fiscal_start_year()
    start_date, end_date = bs_fiscal_year_ad_range(bs_start_year)
    label = bs_fiscal_label(bs_start_year)

    fy, _ = FiscalYear.objects.get_or_create(
        tenant=tenant,
        bs_start_year=bs_start_year,
        defaults={
            'label': label,
            'start_date': start_date,
            'end_date': end_date,
            'is_closed': False,
        },
    )
    return fy


def close_fiscal_year(fiscal_year: FiscalYear, *, user=None, notes: str = '') -> FiscalYear:
    if fiscal_year.is_closed:
        raise ValueError('Fiscal year is already closed.')
    fiscal_year.is_closed = True
    fiscal_year.closed_at = timezone.now()
    if notes:
        fiscal_year.notes = notes
    fiscal_year.save(update_fields=['is_closed', 'closed_at', 'notes'])
    return fiscal_year


def list_fiscal_years(tenant):
    ensure_fiscal_year(tenant)
    return FiscalYear.objects.filter(tenant=tenant).order_by('-start_date')
