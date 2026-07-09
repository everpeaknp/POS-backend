# Generated manually for per-tenant invoice/credit note numbers

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0007_alter_paymentreceived_payment_number'),
        ('tenants', '0002_tenant_created_by'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='invoice_number',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='creditnote',
            name='credit_note_number',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterUniqueTogether(
            name='invoice',
            unique_together={('tenant', 'invoice_number')},
        ),
        migrations.AlterUniqueTogether(
            name='creditnote',
            unique_together={('tenant', 'credit_note_number')},
        ),
    ]
