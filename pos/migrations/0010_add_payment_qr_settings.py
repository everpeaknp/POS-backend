# Generated migration for POS payment method QR codes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0007_loyalty_refund_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='possettings',
            name='esewa_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='possettings',
            name='esewa_qr',
            field=models.ImageField(blank=True, null=True, upload_to='pos/qr/'),
        ),
        migrations.AddField(
            model_name='possettings',
            name='esewa_number',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='possettings',
            name='khalti_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='possettings',
            name='khalti_qr',
            field=models.ImageField(blank=True, null=True, upload_to='pos/qr/'),
        ),
        migrations.AddField(
            model_name='possettings',
            name='khalti_number',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='possettings',
            name='fonepay_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='possettings',
            name='fonepay_qr',
            field=models.ImageField(blank=True, null=True, upload_to='pos/qr/'),
        ),
        migrations.AddField(
            model_name='possettings',
            name='fonepay_number',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='possettings',
            name='bank_transfer_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='possettings',
            name='bank_name',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='possettings',
            name='bank_account_number',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='possettings',
            name='bank_account_name',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
