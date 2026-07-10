"""Bikram Sambat fiscal year helpers for Nepal accounting."""

from __future__ import annotations

from datetime import date

import nepali_datetime

from hr.utils import bs_month_days


def bs_fiscal_year_ad_range(bs_start_year: int) -> tuple[date, date]:
    """
    Nepal fiscal year: Shrawan 1 (BS year) through last day of Ashadh (BS year + 1).
    Example: 2081 → Shrawan 2081 to Ashadh 2082.
    """
    start = nepali_datetime.date(bs_start_year, 4, 1).to_datetime_date()
    end_year = bs_start_year + 1
    last_ashadh = bs_month_days(end_year, 3)
    end = nepali_datetime.date(end_year, 3, last_ashadh).to_datetime_date()
    return start, end


def current_bs_fiscal_start_year() -> int:
    today = nepali_datetime.date.today()
    # Before Shrawan (month 4), fiscal year started previous BS year
    if today.month < 4:
        return today.year - 1
    return today.year


def bs_fiscal_label(bs_start_year: int) -> str:
    end_short = str(bs_start_year + 1)[-2:]
    return f'{bs_start_year}/{end_short}'


def ad_to_bs_fiscal_start_year(ad: date) -> int:
    bs = nepali_datetime.date.from_datetime_date(ad)
    if bs.month < 4:
        return bs.year - 1
    return bs.year
