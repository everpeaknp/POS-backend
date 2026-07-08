from django.db import migrations, models


def backfill_hr_configure(apps, schema_editor):
    """Enable HR Configure (set permissions) for admin and manager."""
    RolePermission = apps.get_model('users', 'RolePermission')
    Tenant = apps.get_model('tenants', 'Tenant')

    for tenant in Tenant.objects.all().iterator():
        for role in ('admin', 'manager'):
            RolePermission.objects.get_or_create(
                tenant_id=tenant.id,
                role=role,
                module='hr',
                action='configure',
                defaults={'allowed': True},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0016_rolepermission_hr_invite_assign'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rolepermission',
            name='action',
            field=models.CharField(
                choices=[
                    ('view', 'View'),
                    ('create', 'Create'),
                    ('edit', 'Edit'),
                    ('delete', 'Delete'),
                    ('export', 'Export'),
                    ('approve', 'Approve'),
                    ('invite', 'Invite'),
                    ('assign', 'Assign'),
                    ('configure', 'Configure'),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_hr_configure, migrations.RunPython.noop),
    ]
