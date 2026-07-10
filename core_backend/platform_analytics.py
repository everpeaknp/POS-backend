"""Platform operations analytics for KHATA admin dashboard."""

from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from billing.models import BillingPayment, Subscription
from core_backend.platform_constants import AVAILABLE_MODULES
from mail.models import EmailLog, EmailQueue
from tenants.invitation_models import OrganizationInvitation
from tenants.models import Tenant


def _last_n_days(n: int = 30):
    start = timezone.now().date() - timedelta(days=n - 1)
    return start


def platform_dashboard_stats() -> dict:
    today = timezone.now().date()
    month_start = today.replace(day=1)
    thirty_days_ago = _last_n_days(30)

    tenants = Tenant.objects.all()
    total_tenants = tenants.count()
    active_tenants = tenants.filter(is_active=True).count()
    inactive_tenants = total_tenants - active_tenants
    new_tenants_month = tenants.filter(created_at__date__gte=month_start).count()
    registration_tenants = tenants.filter(created_from_registration=True).count()

    from django.contrib.auth import get_user_model
    User = get_user_model()
    total_users = User.objects.filter(is_active=True).count()
    new_users_month = User.objects.filter(date_joined__date__gte=month_start).count()

    subs = Subscription._base_manager.select_related('tenant').all()
    subs_by_status = dict(
        subs.values('status').annotate(c=Count('id')).values_list('status', 'c')
    )
    subs_by_plan = dict(
        subs.values('plan_code').annotate(c=Count('id')).values_list('plan_code', 'c')
    )

    payments = BillingPayment.objects.select_related('initiated_by').all()
    payments_by_status = dict(
        payments.values('status').annotate(c=Count('id')).values_list('status', 'c')
    )
    revenue_month = payments.filter(
        status='completed',
        completed_at__date__gte=month_start,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    revenue_all = payments.filter(status='completed').aggregate(total=Sum('amount'))['total'] or Decimal('0')
    pending_payments = payments.filter(status='pending').count()
    failed_payments = payments.filter(status='failed').count()

    pending_invitations = OrganizationInvitation.objects.filter(status='pending').count()

    mail_queued = EmailQueue.objects.filter(status='queued').count()
    mail_failed = EmailQueue.objects.filter(status='failed').count()
    emails_sent_month = EmailLog.objects.filter(
        status__in=('sent', 'delivered', 'opened'),
        created_at__date__gte=month_start,
    ).count()

    # Signups per day (last 30 days)
    signup_rows = (
        tenants.filter(created_at__date__gte=thirty_days_ago)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    signup_map = {row['day']: row['count'] for row in signup_rows}
    signup_labels = []
    signup_values = []
    for i in range(30):
        d = thirty_days_ago + timedelta(days=i)
        signup_labels.append(d.strftime('%b %d'))
        signup_values.append(signup_map.get(d, 0))

    # Revenue per day (last 30 days)
    revenue_rows = (
        payments.filter(status='completed', completed_at__date__gte=thirty_days_ago)
        .annotate(day=TruncDate('completed_at'))
        .values('day')
        .annotate(total=Sum('amount'))
        .order_by('day')
    )
    revenue_map = {row['day']: float(row['total'] or 0) for row in revenue_rows}
    revenue_labels = signup_labels[:]
    revenue_values = []
    for i in range(30):
        d = thirty_days_ago + timedelta(days=i)
        revenue_values.append(revenue_map.get(d, 0))

    # Module adoption
    module_counts = Counter()
    for tenant in tenants.only('active_modules'):
        for mod in tenant.active_modules or []:
            module_counts[mod] += 1
    module_labels = [label for key, label in AVAILABLE_MODULES if module_counts.get(key)]
    module_keys = [key for key, _ in AVAILABLE_MODULES if module_counts.get(key)]
    module_values = [module_counts.get(k, 0) for k in module_keys]

    # Business type distribution
    biz_rows = tenants.values('business_type').annotate(c=Count('id')).order_by('-c')
    biz_labels = [r['business_type'].replace('_', ' ').title() for r in biz_rows]
    biz_values = [r['c'] for r in biz_rows]

    # Plan type on tenant model
    plan_type_rows = tenants.values('plan_type').annotate(c=Count('id')).order_by('-c')
    plan_type_labels = [r['plan_type'].title() for r in plan_type_rows]
    plan_type_values = [r['c'] for r in plan_type_rows]

    recent_tenants = list(
        tenants.order_by('-created_at')[:8].values(
            'id', 'name', 'slug', 'plan_type', 'is_active', 'created_at'
        )
    )
    recent_payments = list(
        payments.order_by('-created_at')[:8].values(
            'transaction_uuid',
            'initiated_by__first_name',
            'initiated_by__last_name',
            'initiated_by__email',
            'plan_code',
            'amount',
            'status',
            'created_at',
        )
    )

    return {
        'kpis': {
            'total_tenants': total_tenants,
            'active_tenants': active_tenants,
            'inactive_tenants': inactive_tenants,
            'new_tenants_month': new_tenants_month,
            'registration_tenants': registration_tenants,
            'total_users': total_users,
            'new_users_month': new_users_month,
            'pending_payments': pending_payments,
            'failed_payments': failed_payments,
            'revenue_month': float(revenue_month),
            'revenue_all': float(revenue_all),
            'pending_invitations': pending_invitations,
            'mail_queued': mail_queued,
            'mail_failed': mail_failed,
            'emails_sent_month': emails_sent_month,
            'active_subscriptions': subs_by_status.get('active', 0) + subs_by_status.get('trialing', 0),
        },
        'charts': {
            'signups': {'labels': signup_labels, 'values': signup_values},
            'revenue': {'labels': revenue_labels, 'values': revenue_values},
            'subscriptions_status': {
                'labels': [k.replace('_', ' ').title() for k in subs_by_status.keys()],
                'values': list(subs_by_status.values()),
            },
            'subscriptions_plan': {
                'labels': [k.title() for k in subs_by_plan.keys()],
                'values': list(subs_by_plan.values()),
            },
            'payments_status': {
                'labels': [k.title() for k in payments_by_status.keys()],
                'values': list(payments_by_status.values()),
            },
            'modules': {'labels': module_labels, 'values': module_values},
            'business_types': {'labels': biz_labels, 'values': biz_values},
            'plan_types': {'labels': plan_type_labels, 'values': plan_type_values},
        },
        'recent_tenants': recent_tenants,
        'recent_payments': recent_payments,
    }
