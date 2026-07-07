from django.db import migrations, models


PLAN_LIMITS = {
    'free': {
        'max_users': 1,
        'max_orgs': 1,
        'features': [
            '1 organization',
            '1 user',
            'Sales & Purchase',
            'Inventory',
            'Basic Reports',
            'Accounting',
        ],
    },
    'starter': {
        'max_users': 10,
        'max_orgs': 5,
        'features': [
            'Up to 10 users',
            'Up to 5 organizations',
            'Sales & Purchase',
            'Basic Reports',
            'Email Support',
            'Accounting',
        ],
    },
    'business': {
        'max_users': 50,
        'max_orgs': 10,
        'features': [
            'Up to 50 users',
            'Up to 10 organizations',
            'All Modules',
            'Advanced Reports',
            'Priority Support',
            'API Access',
        ],
    },
    'enterprise': {
        'max_users': None,
        'max_orgs': None,
        'features': [
            'Unlimited users',
            'Unlimited organizations',
            'All Modules',
            'Custom Reports',
            'Dedicated Support',
            'Custom Integrations',
            'SLA Guarantee',
        ],
    },
}


def update_plan_limits(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    for code, data in PLAN_LIMITS.items():
        SubscriptionPlan.objects.filter(code=code).update(**data)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0008_remove_esewasettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionplan',
            name='max_orgs',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Max organizations per account. Leave blank for unlimited.',
                null=True,
            ),
        ),
        migrations.RunPython(update_plan_limits, migrations.RunPython.noop),
    ]
