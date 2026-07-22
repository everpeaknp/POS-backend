"""
Migration: POS production features
- pos_payments (split payment support)
- pos_held_orders (hold/park orders)
- pos_cash_movements (cash in/out)
- pos_settings (configurable tax + receipt)
"""

from decimal import Decimal
import django.db.models.deletion
import django.core.validators
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0004_nepal_payment_methods'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('sales', '0001_initial'),
        ('tenants', '0001_initial'),
    ]

    operations = [
        # ------------------------------------------------------------------ #
        # pos_payments
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='POSPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('payment_method', models.CharField(
                    choices=[
                        ('cash', 'Cash'),
                        ('card', 'Card'),
                        ('esewa', 'eSewa'),
                        ('khalti', 'Khalti'),
                        ('fonepay', 'Fonepay'),
                        ('credit', 'Credit'),
                    ],
                    max_length=20,
                )),
                ('amount', models.DecimalField(
                    decimal_places=2,
                    max_digits=12,
                    validators=[django.core.validators.MinValueValidator(Decimal('0.01'))],
                )),
                ('reference', models.CharField(
                    blank=True,
                    help_text='Card last-4, eSewa TXN ID, etc.',
                    max_length=100,
                )),
                ('transaction', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='payments',
                    to='pos.postransaction',
                )),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='pos_payments',
                    to='tenants.tenant',
                )),
            ],
            options={
                'db_table': 'pos_payments',
                'ordering': ['id'],
            },
        ),

        # ------------------------------------------------------------------ #
        # pos_held_orders
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='POSHeldOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer_name', models.CharField(blank=True, max_length=255)),
                ('items', models.JSONField(help_text='Snapshot of cart items')),
                ('notes', models.TextField(blank=True)),
                ('held_at', models.DateTimeField(auto_now_add=True)),
                ('is_resumed', models.BooleanField(default=False)),
                ('resumed_at', models.DateTimeField(blank=True, null=True)),
                ('customer', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='sales.customer',
                )),
                ('held_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
                ('session', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='held_orders',
                    to='pos.possession',
                )),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='pos_held_orders',
                    to='tenants.tenant',
                )),
            ],
            options={
                'db_table': 'pos_held_orders',
                'ordering': ['-held_at'],
            },
        ),

        # ------------------------------------------------------------------ #
        # pos_cash_movements
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='POSCashMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('movement_type', models.CharField(
                    choices=[('in', 'Cash In'), ('out', 'Cash Out')],
                    max_length=10,
                )),
                ('amount', models.DecimalField(
                    decimal_places=2,
                    max_digits=12,
                    validators=[django.core.validators.MinValueValidator(Decimal('0.01'))],
                )),
                ('reason', models.CharField(max_length=255)),
                ('performed_at', models.DateTimeField(auto_now_add=True)),
                ('performed_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
                ('session', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='cash_movements',
                    to='pos.possession',
                )),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='pos_cash_movements',
                    to='tenants.tenant',
                )),
            ],
            options={
                'db_table': 'pos_cash_movements',
                'ordering': ['-performed_at'],
            },
        ),

        # ------------------------------------------------------------------ #
        # pos_settings
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='POSSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tax_rate', models.DecimalField(decimal_places=2, default=Decimal('13.00'), max_digits=5)),
                ('tax_label', models.CharField(default='VAT', max_length=50)),
                ('tax_inclusive_pricing', models.BooleanField(default=False)),
                ('receipt_header', models.TextField(blank=True)),
                ('receipt_footer', models.TextField(blank=True, default='Thank you for your purchase!')),
                ('auto_print_receipt', models.BooleanField(default=True)),
                ('allow_zero_price_items', models.BooleanField(default=False)),
                ('require_customer_for_credit', models.BooleanField(default=True)),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='pos_settings',
                    to='tenants.tenant',
                )),
            ],
            options={
                'db_table': 'pos_settings',
            },
        ),
        migrations.AlterUniqueTogether(
            name='possettings',
            unique_together={('tenant',)},
        ),
    ]
