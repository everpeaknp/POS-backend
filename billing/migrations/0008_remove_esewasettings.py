from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_remove_googleoauthsettings'),
        ('setting', '0002_esewasettings'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(
                    name='EsewaSettings',
                ),
            ],
        ),
    ]
