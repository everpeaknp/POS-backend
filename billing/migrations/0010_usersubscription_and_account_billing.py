from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_user_subscriptions(apps, schema_editor):
    User = apps.get_model('users', 'User')
    Tenant = apps.get_model('tenants', 'Tenant')
    Subscription = apps.get_model('billing', 'Subscription')
    UserSubscription = apps.get_model('billing', 'UserSubscription')
    BillingPayment = apps.get_model('billing', 'BillingPayment')

    plan_rank = {'free': 0, 'starter': 1, 'business': 2, 'enterprise': 3}

    for user in User.objects.all().iterator():
        best_code = 'free'
        best_rank = 0
        best_sub = None

        for tenant in Tenant.objects.filter(created_by_id=user.id):
            sub = Subscription.objects.filter(tenant_id=tenant.id).first()
            if not sub:
                continue
            rank = plan_rank.get(sub.plan_code, 0)
            if rank >= best_rank:
                best_rank = rank
                best_code = sub.plan_code
                best_sub = sub

        payment = (
            BillingPayment.objects.filter(initiated_by_id=user.id, status='completed')
            .order_by('-completed_at', '-created_at')
            .first()
        )
        if payment and plan_rank.get(payment.plan_code, 0) > best_rank:
            best_code = payment.plan_code
            best_sub = None

        defaults = {
            'plan_code': best_code,
            'status': 'trialing' if best_code == 'free' else 'active',
            'current_period_start': None,
            'current_period_end': None,
            'auto_renew': True,
        }
        if best_sub:
            defaults.update({
                'status': best_sub.status,
                'current_period_start': best_sub.current_period_start,
                'current_period_end': best_sub.current_period_end,
                'auto_renew': best_sub.auto_renew,
            })

        UserSubscription.objects.update_or_create(user_id=user.id, defaults=defaults)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0009_subscriptionplan_max_orgs_and_limits'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tenants', '0012_organizationinvitation_token'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plan_code', models.CharField(default='free', max_length=32)),
                ('status', models.CharField(
                    choices=[
                        ('trialing', 'Trialing'),
                        ('active', 'Active'),
                        ('past_due', 'Past Due'),
                        ('cancelled', 'Cancelled'),
                    ],
                    default='trialing',
                    max_length=20,
                )),
                ('current_period_start', models.DateField(blank=True, null=True)),
                ('current_period_end', models.DateField(blank=True, null=True)),
                ('auto_renew', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='account_subscription',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Account subscription',
                'verbose_name_plural': 'Account subscriptions',
                'db_table': 'billing_user_subscriptions',
            },
        ),
        migrations.AlterField(
            model_name='billingpayment',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                help_text='Optional workspace linked to this payment record',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='billing_payments',
                to='tenants.tenant',
            ),
        ),
        migrations.RunPython(backfill_user_subscriptions, migrations.RunPython.noop),
    ]
