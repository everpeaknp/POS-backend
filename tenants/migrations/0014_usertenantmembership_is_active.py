from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0013_organizationinvitation_email_invite'),
    ]

    operations = [
        migrations.AddField(
            model_name='usertenantmembership',
            name='is_active',
            field=models.BooleanField(
                default=True,
                help_text='If false, the user cannot open or switch into this organization.',
            ),
        ),
    ]
