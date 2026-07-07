from django.db import migrations, models


def copy_google_oauth_from_smtp(apps, schema_editor):
    GoogleOAuthSettings = apps.get_model('billing', 'GoogleOAuthSettings')
    try:
        SmtpSettings = apps.get_model('mail', 'SmtpSettings')
        smtp = SmtpSettings.objects.filter(pk=1).first()
    except Exception:
        smtp = None

    defaults = {'pk': 1}
    if smtp:
        defaults.update({
            'enabled': getattr(smtp, 'google_oauth_enabled', False),
            'client_id': getattr(smtp, 'google_client_id', '') or '',
            'client_secret_encrypted': getattr(smtp, 'google_client_secret_encrypted', '') or '',
        })
    GoogleOAuthSettings.objects.update_or_create(pk=1, defaults=defaults)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0005_update_plan_features'),
        ('mail', '0004_smtpsettings_google_oauth'),
    ]

    operations = [
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
        migrations.RunPython(copy_google_oauth_from_smtp, migrations.RunPython.noop),
    ]
