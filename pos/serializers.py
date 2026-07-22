"""
POS Serializers for API
"""

from rest_framework import serializers
from decimal import Decimal
from .models import (
    POSSession, POSDiscount, POSTransaction, POSTransactionLine, POSDailySalesReport,
    POSPayment, POSHeldOrder, POSCashMovement, POSSettings,
    POSRefund, POSRefundLine, LoyaltyProgram, CustomerLoyaltyPoints, LoyaltyTransaction,
)
from .constants import PAYMENT_METHOD_CHOICES
from .utils import get_warehouse_stock, compute_pos_amounts, quantize_money, get_tenant_tax_rate
from inventory.models import Product, Warehouse


# ---------------------------------------------------------------------------
# POSPayment
# ---------------------------------------------------------------------------

class POSPaymentSerializer(serializers.ModelSerializer):
    """Serializer for individual payments in a split payment."""

    class Meta:
        model = POSPayment
        fields = ['id', 'payment_method', 'amount', 'reference']


class POSPaymentCreateSerializer(serializers.Serializer):
    """Write-only serializer for payment entries sent during transaction creation."""
    payment_method = serializers.ChoiceField(choices=PAYMENT_METHOD_CHOICES)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')


# ---------------------------------------------------------------------------
# POSCashMovement
# ---------------------------------------------------------------------------

class POSCashMovementSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.CharField(source='performed_by.username', read_only=True)

    class Meta:
        model = POSCashMovement
        fields = [
            'id', 'session', 'movement_type', 'amount', 'reason',
            'performed_by', 'performed_by_name', 'performed_at', 'created_at',
        ]
        read_only_fields = ['performed_by', 'performed_at', 'created_at']


# ---------------------------------------------------------------------------
# POSHeldOrder
# ---------------------------------------------------------------------------

class POSHeldOrderSerializer(serializers.ModelSerializer):
    held_by_name = serializers.CharField(source='held_by.username', read_only=True)

    class Meta:
        model = POSHeldOrder
        fields = [
            'id', 'session', 'customer', 'customer_name', 'items', 'notes',
            'held_by', 'held_by_name', 'held_at', 'is_resumed', 'resumed_at', 'created_at',
        ]
        read_only_fields = ['held_by', 'held_at', 'is_resumed', 'resumed_at', 'created_at']


# ---------------------------------------------------------------------------
# POSSettings
# ---------------------------------------------------------------------------

class POSSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = POSSettings
        fields = [
            'id', 'tax_rate', 'tax_label', 'tax_inclusive_pricing',
            'receipt_header', 'receipt_footer', 'auto_print_receipt',
            'allow_zero_price_items', 'require_customer_for_credit',
        ]


# ---------------------------------------------------------------------------
# POSSession
# ---------------------------------------------------------------------------

class POSSessionSerializer(serializers.ModelSerializer):
    """Serializer for POS Sessions"""
    cashier_name = serializers.CharField(source='cashier.username', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    cash_movements = serializers.SerializerMethodField()
    total_cash_in = serializers.SerializerMethodField()
    total_cash_out = serializers.SerializerMethodField()

    class Meta:
        model = POSSession
        fields = [
            'id', 'session_number', 'cashier', 'cashier_name', 'warehouse', 'warehouse_name',
            'opened_at', 'closed_at', 'opening_cash', 'closing_cash', 'expected_cash',
            'cash_variance', 'total_transactions', 'total_sales', 'cash_sales',
            'card_sales', 'esewa_sales', 'khalti_sales', 'fonepay_sales', 'credit_sales',
            'status', 'notes', 'cash_movements', 'total_cash_in', 'total_cash_out', 'created_at',
        ]
        read_only_fields = [
            'session_number', 'cashier', 'opened_at', 'closed_at', 'expected_cash', 'cash_variance',
            'total_transactions', 'total_sales', 'cash_sales', 'card_sales',
            'esewa_sales', 'khalti_sales', 'fonepay_sales', 'credit_sales', 'status', 'created_at',
        ]

    def get_cash_movements(self, obj):
        movements = obj.cash_movements.all()
        return POSCashMovementSerializer(movements, many=True).data

    def get_total_cash_in(self, obj):
        from django.db.models import Sum
        result = obj.cash_movements.filter(movement_type='in').aggregate(total=Sum('amount'))['total']
        return result or Decimal('0.00')

    def get_total_cash_out(self, obj):
        from django.db.models import Sum
        result = obj.cash_movements.filter(movement_type='out').aggregate(total=Sum('amount'))['total']
        return result or Decimal('0.00')


# ---------------------------------------------------------------------------
# POSDiscount
# ---------------------------------------------------------------------------

class POSDiscountSerializer(serializers.ModelSerializer):
    """Serializer for POS Discounts"""
    
    class Meta:
        model = POSDiscount
        fields = [
            'id', 'name', 'code', 'description', 'discount_type', 'discount_value',
            'apply_to', 'category', 'product', 'start_date', 'end_date',
            'min_quantity', 'min_amount', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_code(self, value):
        tenant = self.context['request'].user.tenant
        qs = POSDiscount.objects.filter(tenant=tenant, code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A discount with this code already exists.')
        return value


# ---------------------------------------------------------------------------
# POSTransactionLine
# ---------------------------------------------------------------------------

class POSTransactionLineSerializer(serializers.ModelSerializer):
    """Serializer for POS Transaction Lines"""
    refunded_quantity = serializers.SerializerMethodField()
    
    class Meta:
        model = POSTransactionLine
        fields = [
            'id', 'product', 'product_name', 'product_sku', 'quantity',
            'unit_price', 'discount_amount', 'line_total', 'refunded_quantity'
        ]
        read_only_fields = ['product_name', 'product_sku', 'line_total', 'refunded_quantity']

    def get_refunded_quantity(self, obj):
        from django.db.models import Sum
        result = obj.refund_lines.aggregate(total=Sum('quantity'))['total']
        return float(result or 0.0)


# ---------------------------------------------------------------------------
# POSTransactionCreate (write)
# ---------------------------------------------------------------------------

class POSTransactionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating POS transactions — now supports split payments."""
    lines = POSTransactionLineSerializer(many=True)
    payments = POSPaymentCreateSerializer(many=True, required=False)
    
    class Meta:
        model = POSTransaction
        fields = [
            'customer', 'customer_name', 'subtotal', 'discount_amount',
            'tax_amount', 'total', 'payment_method', 'amount_paid',
            'change_given', 'warehouse', 'notes', 'lines', 'payments',
        ]
        extra_kwargs = {
            'subtotal': {'required': False},
            'tax_amount': {'required': False},
            'total': {'required': False},
        }
    
    def validate(self, data):
        """Validate transaction data and recalculate totals server-side."""
        from sales.credit_utils import check_credit_available

        request = self.context['request']
        tenant = request.user.tenant
        warehouse = data.get('warehouse')
        if not warehouse:
            raise serializers.ValidationError({'warehouse': 'Warehouse is required'})

        lines = data.get('lines') or []
        if not lines:
            raise serializers.ValidationError({'lines': 'At least one item is required'})

        open_session = POSSession.objects.filter(
            tenant=tenant,
            cashier=request.user,
            status='open',
        ).first()
        if not open_session:
            raise serializers.ValidationError({
                'detail': 'Open a POS session before completing sales.'
            })
        data['session'] = open_session

        for line_data in lines:
            product = line_data.get('product')
            quantity = line_data.get('quantity')
            if not product:
                continue

            available = get_warehouse_stock(product, warehouse)
            if available <= 0:
                raise serializers.ValidationError({
                    'lines': f'{product.name} is out of stock at the selected warehouse.'
                })
            if available < quantity:
                raise serializers.ValidationError({
                    'lines': (
                        f'Insufficient stock for {product.name} at {warehouse.name}. '
                        f'Available: {available}, Requested: {quantity}'
                    )
                })

            line_subtotal = quantize_money(quantity * line_data['unit_price'])
            line_discount = quantize_money(line_data.get('discount_amount', 0))
            if line_discount > line_subtotal:
                raise serializers.ValidationError({
                    'lines': f'Line discount exceeds subtotal for {product.name}.'
                })
            line_data['line_total'] = line_subtotal - line_discount

        # Use tenant-specific tax rate
        tax_rate = get_tenant_tax_rate(tenant)
        try:
            amounts = compute_pos_amounts(lines, data.get('discount_amount', 0), tax_rate=tax_rate)
        except ValueError as exc:
            raise serializers.ValidationError({'discount_amount': str(exc)}) from exc

        data.update(amounts)

        # ---- Split-payment validation ----
        payments_data = data.get('payments') or []
        if payments_data:
            payments_total = sum(Decimal(str(p['amount'])) for p in payments_data)
            if payments_total < data['total']:
                raise serializers.ValidationError({
                    'payments': f'Sum of payment amounts ({payments_total}) must be ≥ total ({data["total"]}).'
                })
            # Use first payment as the primary payment_method for backward compat
            data['payment_method'] = payments_data[0]['payment_method']
            data['amount_paid'] = payments_total
            data['change_given'] = payments_total - data['total']

            # Credit check: if any payment entry is credit
            for p in payments_data:
                if p['payment_method'] == 'credit':
                    customer = data.get('customer')
                    if not customer:
                        raise serializers.ValidationError({
                            'customer': 'Customer is required for credit payments.'
                        })
                    try:
                        check_credit_available(customer, Decimal(str(p['amount'])))
                    except ValueError as exc:
                        raise serializers.ValidationError({'customer': str(exc)}) from exc
        else:
            # Traditional single-payment flow
            if data['payment_method'] == 'credit':
                customer = data.get('customer')
                if not customer:
                    raise serializers.ValidationError({
                        'customer': 'Customer is required for credit sales.'
                    })
                try:
                    check_credit_available(customer, amounts['total'])
                except ValueError as exc:
                    raise serializers.ValidationError({'customer': str(exc)}) from exc

            if data['amount_paid'] < data['total']:
                raise serializers.ValidationError({
                    'amount_paid': 'Amount paid must be greater than or equal to total'
                })

            data['change_given'] = data['amount_paid'] - data['total']

        return data
    
    def create(self, validated_data):
        """Create transaction with lines and optional split payments."""
        from django.db import transaction
        
        lines_data = validated_data.pop('lines')
        payments_data = validated_data.pop('payments', [])
        
        with transaction.atomic():
            pos_transaction = POSTransaction.objects.create(
                **validated_data,
                cashier=self.context['request'].user,
                tenant=self.context['request'].user.tenant
            )
            
            created_lines = []
            for line_data in lines_data:
                product = line_data['product']
                
                line_data['product_name'] = product.name
                line_data['product_sku'] = product.sku
                
                line = POSTransactionLine.objects.create(
                    transaction=pos_transaction,
                    tenant=self.context['request'].user.tenant,
                    **line_data
                )
                line.product = product
                created_lines.append(line)
                
                from inventory.models import Stock, StockMovement
                warehouse = validated_data.get('warehouse')
                
                if warehouse:
                    stock, _created = Stock.objects.get_or_create(
                        tenant=self.context['request'].user.tenant,
                        product=product,
                        warehouse=warehouse,
                        defaults={'quantity': Decimal('0.00')}
                    )
                    
                    stock.quantity -= line_data['quantity']
                    stock.save()
                    
                    StockMovement.objects.create(
                        tenant=self.context['request'].user.tenant,
                        product=product,
                        warehouse=warehouse,
                        movement_type='out',
                        quantity=line_data['quantity'],
                        reference_type='POSTransaction',
                        reference_id=pos_transaction.id,
                        reason=f'POS Sale - {pos_transaction.transaction_number}',
                        performed_by=self.context['request'].user
                    )

            from sales.accounting_integration import post_pos_sale
            post_pos_sale(pos_transaction, created_lines)

            # Create split-payment records
            if payments_data:
                for p in payments_data:
                    POSPayment.objects.create(
                        transaction=pos_transaction,
                        tenant=self.context['request'].user.tenant,
                        payment_method=p['payment_method'],
                        amount=p['amount'],
                        reference=p.get('reference', ''),
                    )

            # Handle credit entries (single or split)
            credit_amount = Decimal('0')
            if payments_data:
                credit_amount = sum(
                    Decimal(str(p['amount']))
                    for p in payments_data
                    if p['payment_method'] == 'credit'
                )
            elif validated_data.get('payment_method') == 'credit':
                credit_amount = validated_data['total']

            if credit_amount > 0 and validated_data.get('customer'):
                from sales.models import Customer, CustomerLedger
                customer = Customer.objects.select_for_update().get(
                    pk=validated_data['customer'].pk
                )
                customer.current_balance += credit_amount
                customer.save(update_fields=['current_balance', 'updated_at'])
                
                CustomerLedger.objects.create(
                    tenant=self.context['request'].user.tenant,
                    customer=customer,
                    date=pos_transaction.date.date(),
                    transaction_type='sale',
                    reference_type='POSTransaction',
                    reference_number=pos_transaction.transaction_number,
                    reference_id=pos_transaction.id,
                    debit_amount=credit_amount,
                    credit_amount=Decimal('0.00'),
                    running_balance=customer.current_balance,
                    description=f'POS Credit Sale - {pos_transaction.transaction_number}'
                )

            # ---- Award loyalty points ----
            if pos_transaction.customer_id:
                try:
                    from .models import LoyaltyProgram, CustomerLoyaltyPoints, LoyaltyTransaction
                    tenant = self.context['request'].user.tenant
                    program = LoyaltyProgram.get_for_tenant(tenant)
                    if program.is_active:
                        points_earned = int(pos_transaction.total * program.points_per_rupee)
                        if points_earned > 0:
                            pts, _ = CustomerLoyaltyPoints._base_manager.get_or_create(
                                tenant=tenant,
                                customer_id=pos_transaction.customer_id,
                            )
                            pts.points_balance += points_earned
                            pts.total_earned += points_earned
                            pts.save()
                            LoyaltyTransaction.objects.create(
                                tenant=tenant,
                                customer_points=pts,
                                transaction_type='earn',
                                points=points_earned,
                                reference=pos_transaction.transaction_number,
                                description=f'Earned from POS sale Rs. {pos_transaction.total}',
                            )
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).error(f'Loyalty award failed: {exc}')

            # ---- Reorder alerts ----
            try:
                from inventory.models import Stock
                reorder_alerts = []
                warehouse = validated_data.get('warehouse')
                for line in created_lines:
                    if warehouse:
                        stock = Stock.objects.filter(
                            tenant=pos_transaction.tenant,
                            product=line.product,
                            warehouse=warehouse,
                        ).first()
                        if stock and stock.quantity <= line.product.reorder_level:
                            reorder_alerts.append({
                                'product_id': str(line.product.id),
                                'product_name': line.product.name,
                                'current_stock': float(stock.quantity),
                                'reorder_level': float(line.product.reorder_level),
                            })
                if reorder_alerts:
                    pos_transaction._reorder_alerts = reorder_alerts
            except Exception:
                pass

        return pos_transaction


# ---------------------------------------------------------------------------
# POSTransaction (read)
# ---------------------------------------------------------------------------

class POSTransactionSerializer(serializers.ModelSerializer):
    """Serializer for reading POS transactions"""
    lines = POSTransactionLineSerializer(many=True, read_only=True)
    payments = POSPaymentSerializer(many=True, read_only=True)
    cashier_name = serializers.CharField(source='cashier.username', read_only=True)
    customer_display = serializers.SerializerMethodField()
    session_number = serializers.CharField(source='session.session_number', read_only=True)

    class Meta:
        model = POSTransaction
        fields = [
            'id', 'transaction_number', 'date', 'session', 'session_number',
            'customer', 'customer_name', 'customer_display',
            'subtotal', 'discount_amount', 'tax_amount',
            'total', 'payment_method', 'amount_paid', 'change_given',
            'status', 'cashier', 'cashier_name', 'warehouse', 'notes',
            'lines', 'payments', 'created_at',
        ]
        read_only_fields = ['transaction_number', 'date', 'cashier', 'created_at', 'session']
    
    def get_customer_display(self, obj):
        """Get customer display name"""
        if obj.customer:
            return obj.customer.name
        return obj.customer_name or 'Walk-in Customer'


# ---------------------------------------------------------------------------
# POSDailySalesReport
# ---------------------------------------------------------------------------

class POSDailySalesReportSerializer(serializers.ModelSerializer):
    """Serializer for daily sales reports"""
    cashier_name = serializers.CharField(source='cashier.username', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    
    class Meta:
        model = POSDailySalesReport
        fields = [
            'id', 'date', 'cashier', 'cashier_name', 'warehouse', 'warehouse_name',
            'total_transactions', 'total_items_sold', 'gross_sales',
            'total_discounts', 'total_tax', 'net_sales', 'cash_sales',
            'card_sales', 'esewa_sales', 'khalti_sales', 'fonepay_sales', 'credit_sales', 'cancelled_transactions',
            'refunded_amount', 'generated_at', 'generated_by'
        ]
        read_only_fields = ['generated_at', 'generated_by']


# ---------------------------------------------------------------------------
# ProductSearch (POS)
# ---------------------------------------------------------------------------

class ProductSearchSerializer(serializers.ModelSerializer):
    """Lightweight serializer for product search in POS"""
    stock_quantity = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_id = serializers.IntegerField(read_only=True)
    unit_name = serializers.CharField(source='unit.abbreviation', read_only=True)
    image = serializers.ImageField(read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'selling_price', 'stock_quantity',
            'category_id', 'category_name', 'unit_name', 'image', 'status'
        ]
    
    def get_stock_quantity(self, obj):
        """Stock at selected warehouse, or total when no warehouse filter."""
        request = self.context.get('request')
        warehouse_id = request.query_params.get('warehouse') if request else None
        if warehouse_id:
            from inventory.models import Warehouse
            try:
                warehouse = Warehouse.objects.get(
                    id=warehouse_id,
                    tenant=obj.tenant,
                )
            except Warehouse.DoesNotExist:
                return 0.0
            return float(get_warehouse_stock(obj, warehouse))
        return float(obj.get_total_stock())


# ---------------------------------------------------------------------------
# Feature 1: Refund Serializers
# ---------------------------------------------------------------------------

class POSRefundLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='original_line.product_name', read_only=True)
    product_sku = serializers.CharField(source='original_line.product_sku', read_only=True)

    class Meta:
        model = POSRefundLine
        fields = ['id', 'original_line', 'product_name', 'product_sku', 'quantity', 'refund_amount']


class POSRefundSerializer(serializers.ModelSerializer):
    lines = POSRefundLineSerializer(many=True, read_only=True)
    refunded_by_name = serializers.CharField(source='refunded_by.username', read_only=True)
    original_transaction_number = serializers.CharField(
        source='original_transaction.transaction_number', read_only=True
    )

    class Meta:
        model = POSRefund
        fields = [
            'id', 'original_transaction', 'original_transaction_number',
            'reason', 'refund_method', 'refunded_by', 'refunded_by_name',
            'refunded_at', 'lines', 'created_at',
        ]
        read_only_fields = ['refunded_by', 'refunded_at', 'created_at']


class POSRefundLineCreateSerializer(serializers.Serializer):
    original_line = serializers.PrimaryKeyRelatedField(queryset=POSTransactionLine.objects.all())
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))


class POSRefundCreateSerializer(serializers.Serializer):
    original_transaction = serializers.PrimaryKeyRelatedField(queryset=POSTransaction.objects.all())
    lines = POSRefundLineCreateSerializer(many=True)
    reason = serializers.CharField(required=False, allow_blank=True, default='')
    refund_method = serializers.ChoiceField(choices=PAYMENT_METHOD_CHOICES)

    def validate_original_transaction(self, txn):
        if txn.status != 'completed':
            raise serializers.ValidationError('Refunds are only allowed for completed transactions.')
        request = self.context.get('request')
        if request and txn.tenant != request.user.tenant:
            raise serializers.ValidationError('Transaction not found.')
        return txn


# ---------------------------------------------------------------------------
# Feature 2: Loyalty Serializers
# ---------------------------------------------------------------------------

class LoyaltyProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoyaltyProgram
        fields = [
            'id', 'points_per_rupee', 'rupees_per_point',
            'min_redemption_points', 'is_active',
        ]


class CustomerLoyaltySerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)

    class Meta:
        model = CustomerLoyaltyPoints
        fields = ['id', 'customer', 'customer_name', 'points_balance', 'total_earned', 'total_redeemed']
