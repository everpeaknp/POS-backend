"""Document number generation for purchase module."""

import random
from django.db import transaction
from django.utils import timezone


def _max_sequence(numbers: list[str], prefix: str) -> int:
    max_num = 0
    for number in numbers:
        if not number or not number.startswith(prefix):
            continue
        parts = number.split('-')
        if len(parts) < 2:
            continue
        try:
            max_num = max(max_num, int(parts[-1]))
        except ValueError:
            continue
    return max_num


def next_document_number(tenant, model, field_name: str, prefix: str, *, year: bool = True) -> str:
    """Generate next tenant-scoped document number with locking."""
    year_part = timezone.now().year if year else None
    full_prefix = f'{prefix}-{year_part}-' if year else f'{prefix}-'

    with transaction.atomic():
        numbers = list(
            model.objects.filter(tenant=tenant)
            .select_for_update()
            .values_list(field_name, flat=True)
        )
        next_seq = _max_sequence(numbers, full_prefix) + 1
        if year:
            return f'{prefix}-{year_part}-{str(next_seq).zfill(5)}'
        return f'{prefix}-{str(next_seq).zfill(4)}'


def next_document_number_with_retry(
    tenant,
    model,
    field_name: str,
    prefix: str,
    *,
    year: bool = True,
    max_retries: int = 5,
) -> str:
    from django.db.utils import IntegrityError

    for attempt in range(max_retries):
        number = next_document_number(tenant, model, field_name, prefix, year=year)
        if attempt > 0:
            number = f'{number}-{random.randint(1, 99)}'
        if not model.objects.filter(tenant=tenant, **{field_name: number}).exists():
            return number
        try:
            with transaction.atomic():
                if not model.objects.filter(tenant=tenant, **{field_name: number}).exists():
                    return number
        except IntegrityError:
            continue
    return next_document_number(tenant, model, field_name, prefix, year=year)
