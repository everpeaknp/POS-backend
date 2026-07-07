from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_remove_googleoauthsettings'),
        ('setting', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='EsewaSettings',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('enabled', models.BooleanField(
                            default=True,
                            help_text='Enable eSewa payments for subscription billing',
                        )),
                        ('use_sandbox', models.BooleanField(
                            default=True,
                            help_text='Use eSewa test/sandbox environment (disable for live payments)',
                        )),
                        ('product_code', models.CharField(
                            blank=True,
                            help_text='Merchant product code from eSewa (e.g. EPAYTEST for sandbox)',
                            max_length=100,
                        )),
                        ('secret_key', models.CharField(
                            blank=True,
                            help_text='eSewa HMAC secret key — keep confidential',
                            max_length=255,
                        )),
                        ('frontend_url', models.URLField(
                            blank=True,
                            help_text='Customer app base URL (e.g. http://localhost:3000)',
                        )),
                        ('success_url', models.URLField(
                            blank=True,
                            help_text='Where eSewa redirects after successful payment. Leave blank to auto-use {frontend}/settings/billing/success',
                        )),
                        ('failure_url', models.URLField(
                            blank=True,
                            help_text='Where eSewa redirects after failed/cancelled payment. Leave blank to auto-use {frontend}/settings/billing/failure',
                        )),
                        ('payment_url', models.URLField(
                            blank=True,
                            help_text='eSewa payment form POST URL. Leave blank for sandbox/production default.',
                        )),
                        ('status_url', models.URLField(
                            blank=True,
                            help_text='eSewa transaction verification API URL. Leave blank for sandbox/production default.',
                        )),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        'verbose_name': 'eSewa integration',
                        'verbose_name_plural': 'eSewa integration',
                        'db_table': 'billing_esewa_settings',
                    },
                ),
            ],
        ),
    ]
