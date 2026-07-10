# Generated migration for fiscal year and tenant-scoped document numbers

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='journalentry',
            name='entry_number',
            field=models.CharField(db_index=True, max_length=50),
        ),
        migrations.AlterField(
            model_name='journalentry',
            name='type',
            field=models.CharField(
                choices=[
                    ('Manual', 'Manual'),
                    ('Sales', 'Sales'),
                    ('Purchase', 'Purchase'),
                    ('Payment', 'Payment'),
                    ('Receipt', 'Receipt'),
                    ('Adjustment', 'Adjustment'),
                    ('Construction', 'Construction'),
                    ('Payroll', 'Payroll'),
                    ('Contra', 'Contra'),
                    ('Opening', 'Opening'),
                    ('Closing', 'Closing'),
                ],
                default='Manual',
                max_length=20,
            ),
        ),
        migrations.AlterUniqueTogether(
            name='journalentry',
            unique_together={('tenant', 'entry_number')},
        ),
        migrations.AlterField(
            model_name='vatreturn',
            name='return_number',
            field=models.CharField(db_index=True, max_length=50),
        ),
        migrations.AlterUniqueTogether(
            name='vatreturn',
            unique_together={('tenant', 'return_number')},
        ),
        migrations.CreateModel(
            name='FiscalYear',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('bs_start_year', models.PositiveIntegerField(help_text='Bikram Sambat year when fiscal year starts (Shrawan)')),
                ('label', models.CharField(help_text='e.g. 2081/82', max_length=20)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('is_closed', models.BooleanField(default=False)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenants.tenant')),
            ],
            options={
                'db_table': 'accounting_fiscal_years',
                'ordering': ['-start_date'],
                'unique_together': {('tenant', 'bs_start_year')},
            },
        ),
    ]
