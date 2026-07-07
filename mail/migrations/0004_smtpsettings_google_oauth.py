from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mail', '0003_seed_billing_email_templates'),
    ]

    operations = [
        migrations.AddField(
            model_name='smtpsettings',
            name='google_client_id',
            field=models.CharField(
                blank=True,
                help_text='OAuth 2.0 Client ID from Google Cloud Console.',
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name='smtpsettings',
            name='google_client_secret_encrypted',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='smtpsettings',
            name='google_oauth_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Allow users to sign in with Google on login and signup pages.',
            ),
        ),
    ]
