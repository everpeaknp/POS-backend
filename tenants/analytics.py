"""Business (tenant/workplace) analytics for the dedicated admin dashboard."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from billing.models import BillingPayment
from core_backend.platform_analytics import unfold_bar_chart, unfold_line_chart
from core_backend.platform_constants import AVAILABLE_MODULES
from tenants.models import Tenant


def _last_n_days(n: int = 30):
    return timezone.now().date() - timedelta(days=n - 1)


def business_dashboard_stats() -> dict:
    today = timezone.now().date()
    month_start = today.replace(day=1)
    thirty_days_ago = _last_n_days(30)

    tenants = Tenant.objects.all()
    total_businesses = tenants.count()
    active_businesses = tenants.filter(is_active=True).count()
    inactive_businesses = total_businesses - active_businesses
    new_businesses_month = tenants.filter(created_at__date__gte=month_start).count()

    account_type_rows = tenants.values('account_type').annotate(c=Count('id')).order_by('-c')
    personal_businesses = next((r['c'] for r in account_type_rows if r['account_type'] == 'personal'), 0)
    organization_businesses = total_businesses - personal_businesses

    payments = BillingPayment.objects.filter(status='completed', tenant__isnull=False)
    revenue_from_businesses = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    businesses_with_payment = payments.values('tenant').distinct().count()

    # Growth: businesses created per day, last 30 days
    growth_rows = (
        tenants.filter(created_at__date__gte=thirty_days_ago)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    growth_map = {row['day']: row['count'] for row in growth_rows}
    growth_labels, growth_values = [], []
    for i in range(30):
        d = thirty_days_ago + timedelta(days=i)
        growth_labels.append(d.strftime('%b %d'))
        growth_values.append(growth_map.get(d, 0))

    account_type_labels = [(r['account_type'] or 'other').title() for r in account_type_rows]
    account_type_values = [r['c'] for r in account_type_rows]

    biz_rows = tenants.values('business_type').annotate(c=Count('id')).order_by('-c')
    biz_labels = [r['business_type'].replace('_', ' ').title() for r in biz_rows]
    biz_values = [r['c'] for r in biz_rows]

    plan_rows = tenants.values('plan_type').annotate(c=Count('id')).order_by('-c')
    plan_labels = [r['plan_type'].title() for r in plan_rows]
    plan_values = [r['c'] for r in plan_rows]

    module_counts: dict[str, int] = {}
    for tenant in tenants.only('active_modules'):
        for mod in tenant.active_modules or []:
            module_counts[mod] = module_counts.get(mod, 0) + 1
    module_labels = [label for key, label in AVAILABLE_MODULES if module_counts.get(key)]
    module_keys = [key for key, _ in AVAILABLE_MODULES if module_counts.get(key)]
    module_values = [module_counts.get(k, 0) for k in module_keys]

    top_by_members = list(
        tenants.annotate(member_count=Count('user_memberships'))
        .order_by('-member_count')[:8]
        .values('id', 'name', 'slug', 'business_type', 'plan_type', 'member_count')
    )

    top_by_revenue_rows = (
        payments.values('tenant', 'tenant__name', 'tenant__slug', 'tenant__business_type')
        .annotate(total=Sum('amount'))
        .order_by('-total')[:8]
    )
    top_by_revenue = [
        {
            'id': r['tenant'],
            'name': r['tenant__name'],
            'slug': r['tenant__slug'],
            'business_type': r['tenant__business_type'],
            'total': float(r['total'] or 0),
        }
        for r in top_by_revenue_rows
    ]

    return {
        'kpis': {
            'total_businesses': total_businesses,
            'active_businesses': active_businesses,
            'inactive_businesses': inactive_businesses,
            'new_businesses_month': new_businesses_month,
            'personal_businesses': personal_businesses,
            'organization_businesses': organization_businesses,
            'revenue_from_businesses': float(revenue_from_businesses),
            'businesses_with_payment': businesses_with_payment,
        },
        'charts': {
            'growth': {'labels': growth_labels, 'values': growth_values},
            'growth_unfold': unfold_line_chart(growth_labels, growth_values),
            'account_types': {'labels': account_type_labels, 'values': account_type_values},
            'business_types': {'labels': biz_labels, 'values': biz_values},
            'plan_types': {'labels': plan_labels, 'values': plan_values},
            'modules': {'labels': module_labels, 'values': module_values},
            'modules_unfold': unfold_bar_chart(module_labels, module_values),
        },
        'top_by_members': top_by_members,
        'top_by_revenue': top_by_revenue,
    }
