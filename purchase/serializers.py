from rest_framework import serializers
from decimal import Decimal
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
    linked_po_id = serializers.SerializerMethodField()
    linked_po_number = serializers.SerializerMethodField()
    
    class Meta:
        model = PurchaseRequest
        fields = [
            'id', 'request_number', 'date', 'requested_by', 'requested_by_name',
            'department', 'required_by', 'estimated_amount', 'priority', 'status',
            'approved_by', 'approved_by_name', 'approved_at', 'rejection_reason',
            'notes', 'items_count', 'lines', 'linked_po_id', 'linked_po_number',
            'tenant', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant', 'created_at', 'updated_at', 'status']

    def get_linked_po_id(self, obj):
        po = obj.purchase_orders.first()
        return po.id if po else None

    def get_linked_po_number(self, obj):
        po = obj.purchase_orders.first()
        return po.po_number if po else None


class PurchaseRequestCreateSerializer(serializers.ModelSerializer):
    lines = PurchaseRequestLineSerializer(many=True)
    
    class Meta:
        model = PurchaseRequest
        fields = [
            'id', 'request_number', 'date', 'department',
            'required_by', 'estimated_amount', 'priority', 'notes', 'lines'
        ]
        read_only_fields = ['id', 'request_number']
    
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        tenant = validated_data.get('tenant')
        if tenant:
            from purchase.numbering import next_document_number
            validated_data['request_number'] = next_document_number(
                tenant, PurchaseRequest, 'request_number', 'PR'
            )
        validated_data['status'] = 'Draft'
        purchase_request = PurchaseRequest.objects.create(**validated_data)
        tenant = purchase_request.tenant
        line_total = Decimal('0')
        for line_data in lines_data:
            PurchaseRequestLine.objects.create(
                tenant=tenant,
                purchase_request=purchase_request,
                **line_data
            )
            line_total += line_data['quantity'] * line_data['estimated_unit_price']
        if line_total > 0:
            purchase_request.estimated_amount = line_total
            purchase_request.save(update_fields=['estimated_amount', 'updated_at'])
        return purchase_request
    
    def update(self, instance, validated_data):
        if instance.status not in ('Draft', 'Pending Approval'):
            raise serializers.ValidationError({
                'detail': 'Only draft or pending requests can be edited.'
            })
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            line_total = Decimal('0')
            for line_data in lines_data:
                PurchaseRequestLine.objects.create(
                    tenant=instance.tenant,
                    purchase_request=instance,
                    **line_data
                )
                line_total += line_data['quantity'] * line_data['estimated_unit_price']
            if line_total > 0:
                instance.estimated_amount = line_total
                instance.save(update_fields=['estimated_amount', 'updated_at'])
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
        if instance.status in ('Partially Received', 'Received', 'Cancelled'):
            raise serializers.ValidationError({
                'detail': 'Cannot edit a received or cancelled purchase order.'
            })
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None:
            existing = {str(line.id): line for line in instance.lines.all()}
            seen_ids: set[str] = set()
            for line_data in lines_data:
                line_id = line_data.pop('id', None)
                received_qty = line_data.pop('received_quantity', None)
                line_key = str(line_id) if line_id else None
                if line_key and line_key in existing:
                    line = existing[line_key]
                    for attr, value in line_data.items():
                        setattr(line, attr, value)
                    if received_qty is not None:
                        line.received_quantity = received_qty
                    line.save()
                    seen_ids.add(line_key)
                else:
                    line_data.pop('received_quantity', None)
                    PurchaseOrderLine.objects.create(
                        tenant=instance.tenant,
                        purchase_order=instance,
                        **line_data
                    )
            for line_id, line in existing.items():
                if line_id not in seen_ids and line.received_quantity <= 0:
                    line.delete()
            instance.calculate_totals()
        return instance


class PurchaseInvoiceSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    purchase_order_number = serializers.CharField(source='purchase_order.po_number', read_only=True, allow_null=True)
    balance = serializers.ReadOnlyField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = PurchaseInvoice
        fields = [
            'id', 'invoice_number', 'date', 'due_date', 'supplier', 'supplier_name',
            'purchase_order', 'purchase_order_number', 'amount', 'paid_amount', 'balance', 'status', 'notes',
            'created_by', 'created_by_name', 'tenant', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'invoice_number', 'paid_amount', 'balance',
            'tenant', 'created_at', 'updated_at',
        ]
    
    def create(self, validated_data):
        tenant = validated_data.get('tenant')
        if tenant:
            from purchase.numbering import next_document_number
            validated_data['invoice_number'] = next_document_number(
                tenant, PurchaseInvoice, 'invoice_number', 'PINV'
            )
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

    def validate(self, data):
        invoice = data.get('invoice') or getattr(self.instance, 'invoice', None)
        supplier = data.get('supplier') or getattr(self.instance, 'supplier', None)
        amount = data.get('amount') or getattr(self.instance, 'amount', None)
        status = data.get('status', getattr(self.instance, 'status', 'Draft'))

        if status == 'Applied' and (not self.instance or self.instance.status == 'Draft'):
            raise serializers.ValidationError({
                'status': 'Debit notes must be issued before they can be applied.'
            })

        if invoice and supplier and invoice.supplier_id != supplier.id:
            raise serializers.ValidationError({
                'supplier': 'Supplier must match the linked invoice supplier.'
            })

        if invoice and amount and amount > invoice.balance:
            raise serializers.ValidationError({
                'amount': 'Debit note amount cannot exceed invoice balance.'
            })
        return data
    
    def create(self, validated_data):
        tenant = validated_data.get('tenant')
        if tenant:
            from purchase.numbering import next_document_number
            validated_data['debit_note_number'] = next_document_number(
                tenant, DebitNote, 'debit_note_number', 'DN'
            )
        if validated_data.get('status') == 'Applied':
            validated_data['status'] = 'Issued'
        return super().create(validated_data)
