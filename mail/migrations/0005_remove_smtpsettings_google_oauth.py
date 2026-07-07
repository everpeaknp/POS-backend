from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('mail', '0004_smtpsettings_google_oauth'),
        ('billing', '0006_googleoauthsettings'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='smtpsettings',
            name='google_client_id',
        ),
        migrations.RemoveField(
            model_name='smtpsettings',
            name='google_client_secret_encrypted',
        ),
        migrations.RemoveField(
            model_name='smtpsettings',
            name='google_oauth_enabled',
        ),
    ]
