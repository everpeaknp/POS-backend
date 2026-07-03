import uuid

from django.db import migrations, models


def populate_invitation_tokens(apps, schema_editor):
    OrganizationInvitation = apps.get_model('tenants', 'OrganizationInvitation')
    for invitation in OrganizationInvitation.objects.all().iterator():
        invitation.token = uuid.uuid4()
        invitation.save(update_fields=['token'])


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0011_alter_usertenantmembership_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizationinvitation',
            name='token',
            field=models.UUIDField(db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(populate_invitation_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='organizationinvitation',
            name='token',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
