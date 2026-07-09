from django.db import migrations

BUSINESS_MODULES = [
    'sales', 'purchase', 'inventory', 'accounting',
    'reports', 'pos', 'hr', 'construction', 'hardware',
]

ENTERPRISE_MODULES = [
    'sales', 'purchase', 'inventory', 'accounting',
    'reports', 'pos', 'hr', 'construction', 'hardware',
]


def update_plan_modules(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    SubscriptionPlan.objects.filter(code='business').update(modules=BUSINESS_MODULES)
    SubscriptionPlan.objects.filter(code='enterprise').update(modules=ENTERPRISE_MODULES)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0010_usersubscription_and_account_billing'),
    ]

    operations = [
        migrations.RunPython(update_plan_modules, migrations.RunPython.noop),
    ]
