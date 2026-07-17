"""
POS Serializers for API
"""

from rest_framework import serializers
from decimal import Decimal
from .models import POSSession, POSDiscount, POSTransaction, POSTransactionLine, POSDailySalesReport
from .utils import get_warehouse_stock, compute_pos_amounts, quantize_money
from inventory.models import Product, Warehouse


class POSSessionSerializer(serializers.ModelSerializer):
    """Serializer for POS Sessions"""
    cashier_name = serializers.CharField(source='cashier.username', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    
    class Meta:
        model = POSSession
        fields = [
            'id', 'session_number', 'cashier', 'cashier_name', 'warehouse', 'warehouse_name',
            'opened_at', 'closed_at', 'opening_cash', 'closing_cash', 'expected_cash',
            'cash_variance', 'total_transactions', 'total_sales', 'cash_sales',
            'card_sales', 'esewa_sales', 'khalti_sales', 'fonepay_sales', 'credit_sales', 'status', 'notes', 'created_at'
        ]
        read_only_fields = [
            'session_number', 'cashier', 'opened_at', 'closed_at', 'expected_cash', 'cash_variance',
            'total_transactions', 'total_sales', 'cash_sales', 'card_sales',
            'esewa_sales', 'khalti_sales', 'fonepay_sales', 'credit_sales', 'status', 'created_at'
        ]


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


class POSTransactionLineSerializer(serializers.ModelSerializer):
    """Serializer for POS Transaction Lines"""
    
    class Meta:
        model = POSTransactionLine
        fields = [
            'id', 'product', 'product_name', 'product_sku', 'quantity',
            'unit_price', 'discount_amount', 'line_total'
        ]
        read_only_fields = ['product_name', 'product_sku', 'line_total']


class POSTransactionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating POS transactions"""
    lines = POSTransactionLineSerializer(many=True)
    
    class Meta:
        model = POSTransaction
        fields = [
            'customer', 'customer_name', 'subtotal', 'discount_amount',
            'tax_amount', 'total', 'payment_method', 'amount_paid',
            'change_given', 'warehouse', 'notes', 'lines'
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

        try:
            amounts = compute_pos_amounts(lines, data.get('discount_amount', 0))
        except ValueError as exc:
            raise serializers.ValidationError({'discount_amount': str(exc)}) from exc

        data.update(amounts)

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
        """Create transaction with lines"""
        from django.db import transaction
        
        lines_data = validated_data.pop('lines')
        
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
            
            if validated_data.get('payment_method') == 'credit' and validated_data.get('customer'):
                from sales.models import Customer, CustomerLedger
                customer = Customer.objects.select_for_update().get(
                    pk=validated_data['customer'].pk
                )
                customer.current_balance += validated_data['total']
                customer.save(update_fields=['current_balance', 'updated_at'])
                
                CustomerLedger.objects.create(
                    tenant=self.context['request'].user.tenant,
                    customer=customer,
                    date=pos_transaction.date.date(),
                    transaction_type='sale',
                    reference_type='POSTransaction',
                    reference_number=pos_transaction.transaction_number,
                    reference_id=pos_transaction.id,
                    debit_amount=validated_data['total'],
                    credit_amount=Decimal('0.00'),
                    running_balance=customer.current_balance,
                    description=f'POS Credit Sale - {pos_transaction.transaction_number}'
                )
        
        return pos_transaction


class POSTransactionSerializer(serializers.ModelSerializer):
    """Serializer for reading POS transactions"""
    lines = POSTransactionLineSerializer(many=True, read_only=True)
    cashier_name = serializers.CharField(source='cashier.username', read_only=True)
    customer_display = serializers.SerializerMethodField()
    
    class Meta:
        model = POSTransaction
        fields = [
            'id', 'transaction_number', 'date', 'customer', 'customer_name',
            'customer_display', 'subtotal', 'discount_amount', 'tax_amount',
            'total', 'payment_method', 'amount_paid', 'change_given',
            'status', 'cashier', 'cashier_name', 'warehouse', 'notes',
            'lines', 'created_at'
        ]
        read_only_fields = ['transaction_number', 'date', 'cashier', 'created_at']
    
    def get_customer_display(self, obj):
        """Get customer display name"""
        if obj.customer:
            return obj.customer.name
        return obj.customer_name or 'Walk-in Customer'


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


class ProductSearchSerializer(serializers.ModelSerializer):
    """Lightweight serializer for product search in POS"""
    stock_quantity = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_id = serializers.IntegerField(read_only=True)
    unit_name = serializers.CharField(source='unit.abbreviation', read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'selling_price', 'stock_quantity',
            'category_id', 'category_name', 'unit_name', 'status'
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
