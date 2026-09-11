from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0008_add_digital_wallets_to_bank_account'),
        ('users', '0001_initial'),
        ('tenants', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CashAccount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('balance', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Current cash balance for this user', max_digits=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cash_accounts', to='tenants.tenant')),
                ('user', models.OneToOneField(help_text='The user/cashier who owns this cash account', on_delete=django.db.models.deletion.CASCADE, related_name='cash_account', to='users.user')),
            ],
            options={
                'db_table': 'accounting_cash_accounts',
            },
        ),
        migrations.CreateModel(
            name='CashTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('reference', models.CharField(help_text='Transaction reference (e.g., POS-000123)', max_length=100)),
                ('description', models.TextField()),
                ('type', models.CharField(choices=[('Credit', 'Credit (Money In)'), ('Debit', 'Debit (Money Out)')], max_length=10)),
                ('debit', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('credit', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('balance', models.DecimalField(decimal_places=2, help_text='Cash account balance after this transaction', max_digits=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('cash_account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='accounting.cashaccount')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cash_transactions', to='tenants.tenant')),
            ],
            options={
                'db_table': 'accounting_cash_transactions',
                'ordering': ['-date', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='cashaccount',
            index=models.Index(fields=['tenant', 'user'], name='accounting__tenant__cash_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='cashaccount',
            unique_together={('tenant', 'user')},
        ),
        migrations.AddIndex(
            model_name='cashtransaction',
            index=models.Index(fields=['tenant', 'cash_account', 'date'], name='accounting__tenant__cash_trx_idx'),
        ),
        migrations.AddIndex(
            model_name='cashtransaction',
            index=models.Index(fields=['reference'], name='accounting__reference_idx'),
        ),
    ]
