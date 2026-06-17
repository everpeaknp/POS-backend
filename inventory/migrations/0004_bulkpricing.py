# Generated manually for bulk pricing

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0003_alter_product_unit'),
        ('tenants', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BulkPricing',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('min_quantity', models.DecimalField(decimal_places=2, help_text='Minimum quantity for this price tier', max_digits=10)),
                ('max_quantity', models.DecimalField(blank=True, decimal_places=2, help_text='Maximum quantity (null = unlimited)', max_digits=10, null=True)),
                ('unit_price', models.DecimalField(decimal_places=2, help_text='Price per unit for this quantity range', max_digits=12)),
                ('discount_percent', models.DecimalField(decimal_places=2, default=0, help_text='Discount percentage from base selling price', max_digits=5)),
                ('is_active', models.BooleanField(default=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bulk_prices', to='inventory.product')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)s_set', to='tenants.tenant')),
            ],
            options={
                'db_table': 'bulk_pricing',
                'ordering': ['product', 'min_quantity'],
                'unique_together': {('tenant', 'product', 'min_quantity')},
            },
        ),
        migrations.AddIndex(
            model_name='bulkpricing',
            index=models.Index(fields=['product', 'min_quantity'], name='bulk_pricin_product_idx'),
        ),
        migrations.AddIndex(
            model_name='bulkpricing',
            index=models.Index(fields=['tenant', 'product'], name='bulk_pricin_tenant_idx'),
        ),
    ]
