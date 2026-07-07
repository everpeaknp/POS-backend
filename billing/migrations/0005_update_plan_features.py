from django.db import migrations


PLAN_UPDATES = {
    'free': {
        'features': [
            '1 user',
            'Sales & Purchase',
            'Inventory',
            'Basic Reports',
            'Accounting',
        ],
        'modules': ['sales', 'purchase', 'inventory', 'reports', 'accounting'],
    },
    'starter': {
        'features': [
            'Up to 2 users',
            'Sales & Purchase',
            'Basic Reports',
            'Email Support',
            'Accounting',
        ],
        'modules': ['sales', 'purchase', 'inventory', 'reports', 'accounting'],
    },
    'business': {
        'features': [
            'Up to 10 users',
            'All Modules',
            'Advanced Reports',
            'Priority Support',
            'API Access',
        ],
    },
    'enterprise': {
        'features': [
            'Unlimited users',
            'All Modules',
            'Custom Reports',
            'Dedicated Support',
            'Custom Integrations',
            'SLA Guarantee',
        ],
    },
}


def update_plan_features(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    for code, data in PLAN_UPDATES.items():
        SubscriptionPlan.objects.filter(code=code).update(**data)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0004_subscription_plans'),
    ]

    operations = [
        migrations.RunPython(update_plan_features, migrations.RunPython.noop),
    ]
