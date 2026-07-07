from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0006_googleoauthsettings'),
        ('setting', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(
                    name='GoogleOAuthSettings',
                ),
            ],
        ),
    ]
