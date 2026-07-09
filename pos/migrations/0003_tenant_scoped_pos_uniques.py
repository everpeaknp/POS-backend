# Generated manually for tenant-scoped POS unique fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0002_possession_postransaction_session_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='posdiscount',
            name='code',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='possession',
            name='session_number',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='postransaction',
            name='transaction_number',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterUniqueTogether(
            name='posdiscount',
            unique_together={('tenant', 'code')},
        ),
        migrations.AlterUniqueTogether(
            name='possession',
            unique_together={('tenant', 'session_number')},
        ),
        migrations.AlterUniqueTogether(
            name='postransaction',
            unique_together={('tenant', 'transaction_number')},
        ),
    ]
