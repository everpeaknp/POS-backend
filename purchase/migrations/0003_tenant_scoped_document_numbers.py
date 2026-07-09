from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchase', '0002_supplier_website'),
        ('tenants', '0002_tenant_created_by'),
    ]

    operations = [
        migrations.AlterField(
            model_name='purchaserequest',
            name='request_number',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='purchaseorder',
            name='po_number',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='purchaseinvoice',
            name='invoice_number',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='debitnote',
            name='debit_note_number',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterUniqueTogether(
            name='purchaserequest',
            unique_together={('tenant', 'request_number')},
        ),
        migrations.AlterUniqueTogether(
            name='purchaseorder',
            unique_together={('tenant', 'po_number')},
        ),
        migrations.AlterUniqueTogether(
            name='purchaseinvoice',
            unique_together={('tenant', 'invoice_number')},
        ),
        migrations.AlterUniqueTogether(
            name='debitnote',
            unique_together={('tenant', 'debit_note_number')},
        ),
    ]
