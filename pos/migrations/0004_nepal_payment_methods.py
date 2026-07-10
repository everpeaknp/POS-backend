from decimal import Decimal

from django.db import migrations, models
import django.core.validators


def migrate_upi_payment_method(apps, schema_editor):
    POSTransaction = apps.get_model('pos', 'POSTransaction')
    POSTransaction.objects.filter(payment_method='upi').update(payment_method='esewa')


def migrate_upi_sales_to_esewa(apps, schema_editor):
    for model_name in ('POSSession', 'POSDailySalesReport'):
        Model = apps.get_model('pos', model_name)
        for row in Model.objects.all():
            if hasattr(row, 'upi_sales') and hasattr(row, 'esewa_sales'):
                row.esewa_sales = row.upi_sales or Decimal('0.00')
                row.save(update_fields=['esewa_sales'])


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0003_tenant_scoped_pos_uniques'),
    ]

    operations = [
        migrations.AddField(
            model_name='possession',
            name='esewa_sales',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
            ),
        ),
        migrations.AddField(
            model_name='possession',
            name='khalti_sales',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
            ),
        ),
        migrations.AddField(
            model_name='possession',
            name='fonepay_sales',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
            ),
        ),
        migrations.AddField(
            model_name='posdailysalesreport',
            name='esewa_sales',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='posdailysalesreport',
            name='khalti_sales',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='posdailysalesreport',
            name='fonepay_sales',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.RunPython(migrate_upi_sales_to_esewa, migrations.RunPython.noop),
        migrations.RemoveField(model_name='possession', name='upi_sales'),
        migrations.RemoveField(model_name='posdailysalesreport', name='upi_sales'),
        migrations.RunPython(migrate_upi_payment_method, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='postransaction',
            name='payment_method',
            field=models.CharField(
                choices=[
                    ('cash', 'Cash'),
                    ('card', 'Card'),
                    ('esewa', 'eSewa'),
                    ('khalti', 'Khalti'),
                    ('fonepay', 'Fonepay'),
                    ('credit', 'Credit'),
                ],
                max_length=20,
            ),
        ),
    ]
