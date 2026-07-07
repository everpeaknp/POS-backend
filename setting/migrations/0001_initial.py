from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('billing', '0006_googleoauthsettings'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='GoogleOAuthSettings',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('enabled', models.BooleanField(
                            default=False,
                            help_text='Allow users to sign in with Google on /auth/login and /auth/signup',
                        )),
                        ('client_id', models.CharField(
                            blank=True,
                            help_text='OAuth 2.0 Client ID from Google Cloud Console (Web application)',
                            max_length=255,
                        )),
                        ('client_secret_encrypted', models.TextField(blank=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        'verbose_name': 'Google sign-in',
                        'verbose_name_plural': 'Google sign-in',
                        'db_table': 'billing_google_oauth_settings',
                    },
                ),
            ],
        ),
    ]
