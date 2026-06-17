from rest_framework import serializers
from .models import (
    Supplier, PurchaseRequest, PurchaseRequestLine,
    PurchaseOrder, PurchaseOrderLine, PurchaseInvoice, DebitNote
)


class SupplierSerializer(serializers.ModelSerializer):
    total_orders = serializers.ReadOnlyField()
    total_purchased = serializers.ReadOnlyField()
    outstanding_amount = serializers.ReadOnlyField()
    
    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'phone', 'email', 'website', 'pan', 'address', 'type',
            'credit_limit', 'payment_terms', 'status', 'bank_name',
            'bank_account', 'lead_time_days', 'total_orders',
            'total_purchased', 'outstanding_amount', 'tenant', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant', 'created_at', 'updated_at']


class PurchaseRequestLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    
    class Meta:
        model = PurchaseRequestLine
        fields = [
            'id', 'product', 'product_name', 'product_sku', 'description',
            'quantity', 'estimated_unit_price', 'estimated_amount'
        ]
        read_only_fields = ['id', 'estimated_amount', 'product_name', 'product_sku']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make description optional
        if 'description' in self.fields:
            self.fields['description'].required = False
            self.fields['description'].allow_null = True
            self.fields['description'].allow_blank = True


class PurchaseRequestSerializer(serializers.ModelSerializer):
    lines = PurchaseRequestLineSerializer(many=True, read_only=True)
    requested_by_name = serializers.CharField(source='requested_by.username', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.username', read_only=True)
    items_count = serializers.ReadOnlyField()
    
    class Meta:
        model = PurchaseRequest
        fields = [
            'id', 'request_number', 'date', 'requested_by', 'requested_by_name',
            'department', 'required_by', 'estimated_amount', 'priority', 'status',
            'approved_by', 'approved_by_name', 'approved_at', 'rejection_reason',
            'notes', 'items_count', 'lines', 'tenant', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant', 'created_at', 'updated_at']


class PurchaseRequestCreateSerializer(serializers.ModelSerializer):
    lines = PurchaseRequestLineSerializer(many=True)
    
    class Meta:
        model = PurchaseRequest
        fields = [
            'id', 'request_number', 'date', 'department',
            'required_by', 'estimated_amount', 'priority', 'status',
            'notes', 'lines'
        ]
        read_only_fields = ['id', 'request_number']
    
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        
        # Generate request number
        from django.utils import timezone
        tenant = validated_data.get('tenant')
        if tenant:
            count = PurchaseRequest.objects.filter(tenant=tenant).count() + 1
            request_number = f"PR-{timezone.now().year}-{count:05d}"
            validated_data['request_number'] = request_number
        
        purchase_request = PurchaseRequest.objects.create(**validated_data)
        
        # Get tenant from the purchase request
        tenant = purchase_request.tenant
        
        for line_data in lines_data:
            PurchaseRequestLine.objects.create(
                tenant=tenant,
                purchase_request=purchase_request,
                **line_data
            )
        
        return purchase_request
    
    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        
        # Update purchase request fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update lines if provided
        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                PurchaseRequestLine.objects.create(
                    purchase_request=instance,
                    **line_data
                )
        
        return instance



class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    
    class Meta:
        model = PurchaseOrderLine
        fields = [
            'id', 'product', 'product_name', 'product_sku', 'description',
            'quantity', 'unit_price', 'tax_percent', 'amount', 'received_quantity'
        ]
        read_only_fields = ['id', 'amount', 'product_name', 'product_sku']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make optional fields not required
        for field_name in ['description', 'received_quantity']:
            if field_name in self.fields:
                self.fields[field_name].required = False
                self.fields[field_name].allow_null = True


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    items_count = serializers.ReadOnlyField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'po_number', 'date', 'supplier', 'supplier_name',
            'expected_delivery_date', 'reference', 'payment_terms', 'status',
            'subtotal', 'tax', 'total', 'purchase_request', 'notes',
            'items_count', 'lines', 'created_by', 'created_by_name', 'tenant',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant', 'created_at', 'updated_at']


class PurchaseOrderCreateSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True)
    
    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'po_number', 'date', 'supplier', 'expected_delivery_date',
            'reference', 'payment_terms', 'status', 'subtotal', 'tax', 'total',
            'purchase_request', 'notes', 'lines'
        ]
        read_only_fields = ['id', 'po_number', 'subtotal', 'tax', 'total']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make optional fields not required
        for field_name in ['reference', 'purchase_request', 'notes', 'subtotal', 'tax', 'total']:
            if field_name in self.fields:
                self.fields[field_name].required = False
                self.fields[field_name].allow_null = True
    
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        
        purchase_order = PurchaseOrder.objects.create(**validated_data)
        
        # Get tenant from the purchase order
        tenant = purchase_order.tenant
        
        for line_data in lines_data:
            # Don't pass received_quantity if it's in the data
            line_data.pop('received_quantity', None)
            
            PurchaseOrderLine.objects.create(
                tenant=tenant,
                purchase_order=purchase_order,
                **line_data
            )
        
        purchase_order.calculate_totals()
        return purchase_order
    
    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        
        # Update purchase order fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update lines if provided
        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                PurchaseOrderLine.objects.create(
                    purchase_order=instance,
                    **line_data
                )
            instance.calculate_totals()
        
        return instance


class PurchaseInvoiceSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    balance = serializers.ReadOnlyField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = PurchaseInvoice
        fields = [
            'id', 'invoice_number', 'date', 'due_date', 'supplier', 'supplier_name',
            'purchase_order', 'amount', 'paid_amount', 'balance', 'status', 'notes',
            'created_by', 'created_by_name', 'tenant', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'invoice_number', 'tenant', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        # Generate invoice number
        from django.utils import timezone
        tenant = validated_data.get('tenant')
        if tenant:
            count = PurchaseInvoice.objects.filter(tenant=tenant).count() + 1
            invoice_number = f"PINV-{timezone.now().year}-{count:05d}"
            validated_data['invoice_number'] = invoice_number
        return super().create(validated_data)


class DebitNoteSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = DebitNote
        fields = [
            'id', 'debit_note_number', 'date', 'supplier', 'supplier_name',
            'invoice', 'invoice_number', 'amount', 'reason', 'description',
            'status', 'created_by', 'created_by_name', 'tenant', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'debit_note_number', 'tenant', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        # Generate debit note number
        from django.utils import timezone
        tenant = validated_data.get('tenant')
        if tenant:
            count = DebitNote.objects.filter(tenant=tenant).count() + 1
            debit_note_number = f"DN-{timezone.now().year}-{count:05d}"
            validated_data['debit_note_number'] = debit_note_number
        return super().create(validated_data)
