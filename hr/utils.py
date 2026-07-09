"""HR helpers — Bikram Sambat calendar and payroll calculations."""
from datetime import date
from decimal import Decimal

import nepali_datetime

NEPALI_MONTHS = [
    'Baisakh',
    'Jestha',
    'Ashadh',
    'Shrawan',
    'Bhadra',
    'Ashwin',
    'Kartik',
    'Mangsir',
    'Poush',
    'Magh',
    'Falgun',
    'Chaitra',
]


def current_bs_year() -> int:
    return nepali_datetime.date.today().year


def bs_month_index(month_name: str) -> int:
    try:
        return NEPALI_MONTHS.index(month_name) + 1
    except ValueError as exc:
        raise ValueError(f'Unknown BS month: {month_name}') from exc


def bs_month_days(bs_year: int, month_index: int) -> int:
    for day in range(32, 27, -1):
        try:
            nepali_datetime.date(bs_year, month_index, day)
            return day
        except ValueError:
            continue
    return 30


def bs_month_ad_range(bs_year: int, month_name: str) -> tuple[date, date]:
    """Inclusive Gregorian date range for a Bikram Sambat month."""
    month_index = bs_month_index(month_name)
    start = nepali_datetime.date(bs_year, month_index, 1).to_datetime_date()
    last_day = bs_month_days(bs_year, month_index)
    end = nepali_datetime.date(bs_year, month_index, last_day).to_datetime_date()
    return start, end


def attendance_pay_weight(status: str) -> Decimal:
    if status in ('present', 'late', 'leave'):
        return Decimal('1')
    if status == 'half-day':
        return Decimal('0.5')
    return Decimal('0')


def calculate_employee_payroll_amounts(employee, bs_year: int, month_name: str, tenant):
    """
    Compute payroll line items using PF model fields and attendance proration.
    If no attendance exists for the BS month, full salary is used.
    """
    from .models import Attendance

    start, end = bs_month_ad_range(bs_year, month_name)
    days_in_month = bs_month_days(bs_year, bs_month_index(month_name))

    records = Attendance.objects.filter(
        tenant=tenant,
        employee=employee,
        date__gte=start,
        date__lte=end,
    )

    basic = employee.basic_salary
    if not records.exists():
        factor = Decimal('1')
    else:
        paid_days = sum(attendance_pay_weight(r.status) for r in records)
        factor = min(Decimal('1'), Decimal(str(paid_days)) / Decimal(str(days_in_month)))

    basic_prorated = basic * factor
    allowances = employee.pf_employer * factor
    deductions = employee.pf_employee * factor
    gross_salary = basic_prorated + allowances
    net_salary = gross_salary - deductions

    return {
        'basic_salary': basic_prorated,
        'allowances': allowances,
        'gross_salary': gross_salary,
        'deductions': deductions,
        'net_salary': net_salary,
    }


def sync_leave_to_attendance(leave_request) -> None:
    """Create or update attendance rows for an approved leave request."""
    from datetime import timedelta

    from .models import Attendance

    current = leave_request.start_date
    remark = f'Approved leave: {leave_request.leave_type.name}'
    while current <= leave_request.end_date:
        Attendance.objects.update_or_create(
            tenant=leave_request.tenant,
            employee=leave_request.employee,
            date=current,
            defaults={
                'status': 'leave',
                'remarks': remark,
            },
        )
        current += timedelta(days=1)
