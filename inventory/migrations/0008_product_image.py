"""
Migration: Add image field to Product model.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0007_product_expiry_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='image',
            field=models.ImageField(
                blank=True,
                help_text='Product image for POS display and catalog',
                null=True,
                upload_to='products/',
            ),
        ),
    ]
