from rest_framework import serializers
from django.db import transaction
from .models import (
    Customer, SalesOrder, SalesOrderLine, Quotation, QuotationLine, Invoice, CreditNote,
    CustomerLedger, PaymentReceived
)


class CustomerSerializer(serializers.ModelSerializer):
    total_orders = serializers.ReadOnlyField()
    total_spent = serializers.ReadOnlyField()
    
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'phone', 'email', 'pan', 'address', 'type',
            'credit_limit', 'payment_terms', 'status', 'total_orders',
            'total_spent', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SalesOrderLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    
    class Meta:
        model = SalesOrderLine
        fields = [
            'id', 'product', 'product_name', 'product_sku', 'description',
            'quantity', 'unit_price', 'discount_percent', 'tax_percent', 'amount'
        ]
        read_only_fields = ['id', 'amount']
    
    def validate(self, data):
        """Validate stock availability"""
        product = data.get('product')
        quantity = data.get('quantity')
        
        if product and quantity:
            total_stock = product.get_total_stock()
            if total_stock <= 0:
                raise serializers.ValidationError({
                    'product': f'{product.name} is out of stock. Cannot create sales order.'
                })
            if total_stock < quantity:
                raise serializers.ValidationError({
                    'quantity': f'Insufficient stock for {product.name}. Available: {total_stock}, Requested: {quantity}'
                })
        
        return data


class SalesOrderSerializer(serializers.ModelSerializer):
    lines = SalesOrderLineSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    items_count = serializers.ReadOnlyField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = SalesOrder
        fields = [
            'id', 'order_number', 'date', 'customer', 'customer_name',
            'reference', 'status', 'payment_type', 'subtotal', 'discount', 'tax', 'total',
            'notes', 'items_count', 'lines', 'created_by', 'created_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SalesOrderCreateSerializer(serializers.ModelSerializer):
    lines = SalesOrderLineSerializer(many=True)
    
    class Meta:
        model = SalesOrder
        fields = [
            'id', 'order_number', 'date', 'customer', 'reference', 'status',
            'payment_type', 'subtotal', 'discount', 'tax', 'total', 'notes', 'lines'
        ]
        read_only_fields = ['id', 'order_number']
    
    def validate_lines(self, lines_data):
        """Validate all line items have sufficient stock"""
        from inventory.models import Product
        
        for line_data in lines_data:
            product = line_data.get('product')
            quantity = line_data.get('quantity')
            
            if product and quantity:
                total_stock = product.get_total_stock()
                if total_stock <= 0:
                    raise serializers.ValidationError(
                        f'{product.name} is out of stock. Cannot create sales order.'
                    )
                if total_stock < quantity:
                    raise serializers.ValidationError(
                        f'Insufficient stock for {product.name}. Available: {total_stock}, Requested: {quantity}'
                    )
        
        return lines_data
    
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        status_value = validated_data.get('status', 'Draft')
        warehouse_id = self.context.get('warehouse_id')

        with transaction.atomic():
            sales_order = SalesOrder.objects.create(**validated_data)

            for line_data in lines_data:
                SalesOrderLine.objects.create(
                    sales_order=sales_order,
                    tenant=sales_order.tenant,
                    **line_data
                )

            sales_order.calculate_totals()

            if status_value in ('Confirmed', 'Delivered'):
                from sales.stock_integration import handle_sales_order_status_change
                request = self.context.get('request')
                performed_by = request.user if request else None
                handle_sales_order_status_change(
                    sales_order,
                    old_status='Draft',
                    new_status=status_value,
                    performed_by=performed_by,
                    warehouse_id=warehouse_id,
                )

        return sales_order
    
    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        
        # Update sales order fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update lines if provided
        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                SalesOrderLine.objects.create(sales_order=instance, **line_data)
            instance.calculate_totals()
        
        return instance


class QuotationLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    
    class Meta:
        model = QuotationLine
        fields = [
            'id', 'product', 'product_name', 'product_sku', 'description',
            'quantity', 'unit_price', 'discount_percent', 'tax_percent', 'amount'
        ]
        read_only_fields = ['id', 'amount']


class QuotationSerializer(serializers.ModelSerializer):
    lines = QuotationLineSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    items_count = serializers.ReadOnlyField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = Quotation
        fields = [
            'id', 'quotation_number', 'date', 'customer', 'customer_name',
            'valid_until', 'subtotal', 'discount', 'tax', 'total', 'status', 'notes',
            'items_count', 'lines', 'created_by', 'created_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class QuotationCreateSerializer(serializers.ModelSerializer):
    lines = QuotationLineSerializer(many=True)
    
    class Meta:
        model = Quotation
        fields = [
            'id', 'quotation_number', 'date', 'customer', 'valid_until',
            'subtotal', 'discount', 'tax', 'total', 'status', 'notes', 'lines'
        ]
        read_only_fields = ['id', 'quotation_number']
    
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        quotation = Quotation.objects.create(**validated_data)
        
        # Create line items with explicit tenant
        for line_data in lines_data:
            QuotationLine.objects.create(
                quotation=quotation,
                tenant=quotation.tenant,
                **line_data
            )
        
        quotation.calculate_totals()
        return quotation
    
    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        
        # Update quotation fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update lines if provided
        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                QuotationLine.objects.create(
                    quotation=instance,
                    tenant=instance.tenant,
                    **line_data
                )
            instance.calculate_totals()
        
        return instance


class InvoiceSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    balance = serializers.ReadOnlyField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'date', 'due_date', 'customer', 'customer_name',
            'sales_order', 'amount', 'paid_amount', 'balance', 'payment_type', 'status',
            'notes', 'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'invoice_number', 'balance', 'created_at', 'updated_at']


class CreditNoteSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = CreditNote
        fields = [
            'id', 'credit_note_number', 'date', 'customer', 'customer_name',
            'invoice', 'invoice_number', 'amount', 'reason', 'status',
            'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'credit_note_number', 'created_at', 'updated_at']



class CustomerLedgerSerializer(serializers.ModelSerializer):
    """Serializer for Customer Ledger entries"""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    
    class Meta:
        model = CustomerLedger
        fields = [
            'id', 'customer', 'customer_name', 'date', 'transaction_type',
            'reference_type', 'reference_number', 'reference_id',
            'debit_amount', 'credit_amount', 'running_balance', 'description',
            'created_at'
        ]
        read_only_fields = ['id', 'running_balance', 'created_at', 'customer_name']


class PaymentReceivedSerializer(serializers.ModelSerializer):
    """Serializer for Payment Received"""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    received_by_name = serializers.CharField(source='received_by.username', read_only=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    
    class Meta:
        model = PaymentReceived
        fields = [
            'id', 'payment_number', 'date', 'customer', 'customer_name',
            'amount', 'payment_method', 'reference_number', 'bank_name',
            'invoice', 'invoice_number', 'notes', 'received_by', 'received_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'payment_number', 'received_by', 'received_by_name',
            'created_at', 'updated_at', 'customer_name', 'invoice_number'
        ]


class CustomerDetailSerializer(serializers.ModelSerializer):
    """Extended Customer serializer with credit information"""
    total_orders = serializers.ReadOnlyField()
    total_spent = serializers.ReadOnlyField()
    is_over_limit = serializers.ReadOnlyField()
    available_credit = serializers.ReadOnlyField()
    
    # Recent ledger entries
    recent_ledger = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'phone', 'email', 'pan', 'address', 'type',
            'credit_limit', 'current_balance', 'payment_terms', 'status',
            'total_orders', 'total_spent', 'is_over_limit', 'available_credit',
            'recent_ledger', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'current_balance', 'created_at', 'updated_at',
            'is_over_limit', 'available_credit'
        ]
    
    def get_recent_ledger(self, obj):
        """Get last 5 ledger entries"""
        recent = obj.ledger_entries.all()[:5]
        return CustomerLedgerSerializer(recent, many=True).data


# Update CustomerSerializer to include new fields
class CustomerSerializer(serializers.ModelSerializer):
    total_orders = serializers.ReadOnlyField()
    total_spent = serializers.ReadOnlyField()
    is_over_limit = serializers.ReadOnlyField()
    available_credit = serializers.ReadOnlyField()
    
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'phone', 'email', 'pan', 'address', 'type',
            'credit_limit', 'current_balance', 'payment_terms', 'status',
            'total_orders', 'total_spent', 'is_over_limit', 'available_credit',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'current_balance', 'created_at', 'updated_at']
