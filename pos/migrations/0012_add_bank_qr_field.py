# Generated migration for adding bank_qr field to POSSettings

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0011_possettings_esewa_name_possettings_khalti_name_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='possettings',
            name='bank_qr',
            field=models.ImageField(blank=True, null=True, upload_to='pos/qr/'),
        ),
    ]
