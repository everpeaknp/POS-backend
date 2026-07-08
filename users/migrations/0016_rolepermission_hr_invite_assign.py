from django.db import migrations, models


def backfill_hr_invite_assign(apps, schema_editor):
    """Enable HR Invite/Assign for admin and manager on existing tenants."""
    RolePermission = apps.get_model('users', 'RolePermission')
    Tenant = apps.get_model('tenants', 'Tenant')

    defaults = {
        'admin': ['invite', 'assign'],
        'manager': ['invite', 'assign'],
    }
    for tenant in Tenant.objects.all().iterator():
        for role, actions in defaults.items():
            for action in actions:
                RolePermission.objects.get_or_create(
                    tenant_id=tenant.id,
                    role=role,
                    module='hr',
                    action=action,
                    defaults={'allowed': True},
                )


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0015_user_google_id'),
        ('tenants', '0014_usertenantmembership_is_active'),
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
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_hr_invite_assign, migrations.RunPython.noop),
    ]
