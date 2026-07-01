from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0009_add_cashier_to_invitation_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='pan_vat_number',
            field=models.CharField(
                blank=True,
                help_text='PAN or VAT registration number',
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='tenant',
            name='website',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
