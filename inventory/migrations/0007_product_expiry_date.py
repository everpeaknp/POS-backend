from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0006_customerspecificprice_pricehistory'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='expiry_date',
            field=models.DateField(
                blank=True,
                help_text='Optional expiry date for perishable products',
                null=True,
            ),
        ),
    ]
