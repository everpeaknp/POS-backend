from django.db import models
from django.utils import timezone
from rest_framework import serializers
from .models import Vehicle, Delivery, DeliveryItem, MaterialRate, RentalEquipment, Rental
from sales.models import Invoice, Customer
from inventory.models import Product
from tenants.utils import get_request_tenant


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            'id',
            'vehicle_number',
            'vehicle_type',
            'capacity_kg',
            'status',
            'last_service_date',
            'next_service_due',
            'is_owned',
            'notes',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DeliveryItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    product_unit = serializers.CharField(source='product.unit', read_only=True)
    pending_quantity = serializers.SerializerMethodField()
    is_fully_delivered = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()
    
    class Meta:
        model = DeliveryItem
        fields = [
            'id',
            'product',
            'product_name',
            'product_sku',
            'product_unit',
            'ordered_quantity',
            'delivered_quantity',
            'damaged_quantity',
            'pending_quantity',
            'is_fully_delivered',
            'unit_price',
            'line_total',
            'notes'
        ]
        read_only_fields = ['id', 'pending_quantity', 'is_fully_delivered', 'line_total']
    
    def get_pending_quantity(self, obj):
        return float(obj.get_pending_quantity())
    
    def get_is_fully_delivered(self, obj):
        return obj.is_fully_delivered()
    
    def get_line_total(self, obj):
        return float(obj.get_line_total())


class DeliveryListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for delivery list view"""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    vehicle_number = serializers.CharField(source='vehicle.vehicle_number', read_only=True)
    total_charges = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Delivery
        fields = [
            'id',
            'delivery_number',
            'challan_number',
            'customer',
            'customer_name',
            'invoice',
            'invoice_number',
            'delivery_address',
            'scheduled_date',
            'scheduled_time',
            'status',
            'vehicle',
            'vehicle_number',
            'driver_name',
            'driver_phone',
            'transport_charge',
            'loading_charge',
            'total_charges',
            'items_count',
            'created_at'
        ]
        read_only_fields = ['id', 'total_charges', 'items_count', 'created_at']
    
    def get_total_charges(self, obj):
        return float(obj.get_total_charges())
    
    def get_items_count(self, obj):
        return obj.items.count()


class DeliveryDetailSerializer(serializers.ModelSerializer):
    """Full delivery serializer with all details"""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    customer_phone = serializers.CharField(source='customer.phone', read_only=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    invoice_amount = serializers.DecimalField(
        source='invoice.amount',
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    vehicle_details = VehicleSerializer(source='vehicle', read_only=True)
    items = DeliveryItemSerializer(many=True, read_only=True)
    total_charges = serializers.SerializerMethodField()
    can_be_edited = serializers.SerializerMethodField()
    can_be_cancelled = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = Delivery
        fields = [
            'id',
            'delivery_number',
            'challan_number',
            'invoice',
            'invoice_number',
            'invoice_amount',
            'customer',
            'customer_name',
            'customer_phone',
            'delivery_address',
            'customer_contact_name',
            'customer_contact_phone',
            'scheduled_date',
            'scheduled_time',
            'loading_started_at',
            'dispatch_time',
            'delivery_completed_at',
            'vehicle',
            'vehicle_details',
            'driver_name',
            'driver_phone',
            'status',
            'transport_charge',
            'loading_charge',
            'total_charges',
            'delivery_notes',
            'driver_notes',
            'customer_signature',
            'delivery_photos',
            'failure_reason',
            'items',
            'can_be_edited',
            'can_be_cancelled',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id',
            'delivery_number',
            'total_charges',
            'can_be_edited',
            'can_be_cancelled',
            'created_at',
            'updated_at'
        ]
    
    def get_total_charges(self, obj):
        return float(obj.get_total_charges())
    
    def get_can_be_edited(self, obj):
        return obj.can_be_edited()
    
    def get_can_be_cancelled(self, obj):
        return obj.can_be_cancelled()


class DeliveryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating delivery from invoice"""
    items = DeliveryItemSerializer(many=True, required=False)
    # Both are auto-derived in create() when omitted (sequential number,
    # invoice's customer) — required=False here so that actually works
    # instead of being rejected by ModelSerializer's default validation.
    delivery_number = serializers.CharField(required=False, allow_blank=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False)

    class Meta:
        model = Delivery
        fields = [
            'invoice',
            'delivery_number',
            'challan_number',
            'customer',
            'delivery_address',
            'customer_contact_name',
            'customer_contact_phone',
            'scheduled_date',
            'scheduled_time',
            'vehicle',
            'driver_name',
            'driver_phone',
            'transport_charge',
            'loading_charge',
            'delivery_notes',
            'items'
        ]
    
    def validate_invoice(self, value):
        """Ensure invoice belongs to current tenant"""
        request = self.context.get('request')
        tenant = get_request_tenant(request.user) if request else None
        if tenant and value.tenant_id != tenant.id:
            raise serializers.ValidationError("Invoice does not belong to your organization")
        return value

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        request = self.context.get('request')
        tenant = get_request_tenant(request.user)

        # Set tenant and created_by
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user

        # Auto-set customer from invoice if not provided
        if 'customer' not in validated_data:
            validated_data['customer'] = validated_data['invoice'].customer

        # Generate delivery number if not provided
        if not validated_data.get('delivery_number'):
            # Simple sequential numbering
            last_delivery = Delivery.objects.filter(
                tenant=tenant
            ).order_by('-id').first()

            if last_delivery and last_delivery.delivery_number:
                try:
                    last_num = int(last_delivery.delivery_number.split('-')[-1])
                    validated_data['delivery_number'] = f"DEL-{last_num + 1:06d}"
                except:
                    validated_data['delivery_number'] = f"DEL-{Delivery.objects.filter(tenant=tenant).count() + 1:06d}"
            else:
                validated_data['delivery_number'] = "DEL-000001"

        delivery = Delivery.objects.create(**validated_data)

        # Create delivery items from the invoice's sales order lines if not
        # explicitly provided. Invoice itself carries no line items — it's a
        # flat amount/paid_amount record — only a linked sales_order does.
        if not items_data:
            sales_order = delivery.invoice.sales_order
            for line in (sales_order.lines.all() if sales_order else []):
                DeliveryItem.objects.create(
                    tenant=tenant,
                    delivery=delivery,
                    product=line.product,
                    ordered_quantity=line.quantity,
                    delivered_quantity=line.quantity,  # Default to full delivery
                    unit_price=line.unit_price
                )
        else:
            for item_data in items_data:
                DeliveryItem.objects.create(
                    tenant=tenant,
                    delivery=delivery,
                    **item_data
                )

        return delivery


class DeliveryStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating delivery status"""
    status = serializers.ChoiceField(choices=Delivery.STATUS_CHOICES)
    driver_notes = serializers.CharField(required=False, allow_blank=True)
    failure_reason = serializers.CharField(required=False, allow_blank=True)
    customer_signature = serializers.ImageField(required=False, allow_null=True)
    delivery_photos = serializers.ListField(
        child=serializers.URLField(),
        required=False,
        allow_empty=True
    )
    
    def validate(self, data):
        if data['status'] == 'failed' and not data.get('failure_reason'):
            raise serializers.ValidationError({
                'failure_reason': 'Failure reason is required when marking delivery as failed'
            })
        return data


class MaterialRateSerializer(serializers.ModelSerializer):
    """
    A single dated rate entry. `previous_rate`/`change` describe the delta
    against this product's last rate before this one, so the rate board can
    show up/down arrows without the frontend re-deriving history itself.
    """
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    unit_display = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default=None)
    previous_rate = serializers.SerializerMethodField()
    change = serializers.SerializerMethodField()

    class Meta:
        model = MaterialRate
        fields = [
            'id', 'product', 'product_name', 'product_sku',
            'rate', 'unit_label', 'unit_display', 'effective_date', 'notes',
            'created_by', 'created_by_name', 'previous_rate', 'change',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def get_unit_display(self, obj):
        if obj.unit_label:
            return obj.unit_label
        unit = getattr(obj.product, 'unit', None)
        return unit.abbreviation if unit else ''

    def _previous_entry(self, obj):
        return (
            MaterialRate._base_manager
            .filter(tenant=obj.tenant, product_id=obj.product_id)
            .exclude(pk=obj.pk)
            .filter(
                models.Q(effective_date__lt=obj.effective_date) |
                models.Q(effective_date=obj.effective_date, created_at__lt=obj.created_at)
            )
            .order_by('-effective_date', '-created_at')
            .first()
        )

    def get_previous_rate(self, obj):
        previous = self._previous_entry(obj)
        return previous.rate if previous else None

    def get_change(self, obj):
        previous = self._previous_entry(obj)
        if not previous:
            return None
        return obj.rate - previous.rate

    def validate_product(self, product):
        request = self.context.get('request')
        tenant = get_request_tenant(request.user) if request else None
        if tenant and product.tenant_id != tenant.id:
            raise serializers.ValidationError('Product not found')
        return product


class RentalEquipmentSerializer(serializers.ModelSerializer):
    """
    Rentable-tool catalogue entry. `units_out`/`units_available` are
    computed from active rentals so the count is always correct without
    a separate stock-adjustment step every checkout/return.
    """
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    units_out = serializers.SerializerMethodField()
    units_available = serializers.SerializerMethodField()

    class Meta:
        model = RentalEquipment
        fields = [
            'id', 'name', 'category', 'category_display', 'total_units',
            'daily_rate', 'deposit_amount', 'is_active', 'notes',
            'units_out', 'units_available', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_units_out(self, obj):
        return obj.units_out()

    def get_units_available(self, obj):
        return obj.units_available()


class RentalSerializer(serializers.ModelSerializer):
    """
    A single equipment checkout. `daily_rate`/`deposit_collected` default
    from the equipment's current settings when omitted, so the common
    case ("rent one out today, back tomorrow at the usual rate") needs
    almost no typing. `is_overdue`/`days_rented`/`total_charge` are
    derived at read time — nothing needs a background job to keep an
    "overdue" flag in sync.
    """
    equipment_name = serializers.CharField(source='equipment.name', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    customer_phone = serializers.CharField(source='customer.phone', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_overdue = serializers.SerializerMethodField()
    days_rented = serializers.SerializerMethodField()
    total_charge = serializers.SerializerMethodField()
    daily_rate = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    deposit_collected = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    due_date = serializers.DateField(required=False)

    class Meta:
        model = Rental
        fields = [
            'id', 'equipment', 'equipment_name', 'customer', 'customer_name', 'customer_phone',
            'quantity', 'daily_rate', 'deposit_collected', 'checkout_date', 'due_date',
            'return_date', 'status', 'status_display', 'is_overdue', 'days_rented',
            'total_charge', 'notes', 'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def get_is_overdue(self, obj):
        return obj.is_overdue()

    def get_days_rented(self, obj):
        return obj.days_rented()

    def get_total_charge(self, obj):
        return obj.get_total_charge()

    def validate(self, data):
        equipment = data.get('equipment', getattr(self.instance, 'equipment', None))
        quantity = data.get('quantity', getattr(self.instance, 'quantity', 1))

        if self.instance is None:
            if not data.get('daily_rate') and equipment:
                data['daily_rate'] = equipment.daily_rate
            if 'deposit_collected' not in data and equipment:
                data['deposit_collected'] = equipment.deposit_amount
            if not data.get('due_date'):
                data['due_date'] = data.get('checkout_date') or timezone.now().date()

        if equipment and self.instance is None:
            available = equipment.units_available()
            if quantity > available:
                raise serializers.ValidationError({
                    'quantity': f'Only {available} unit(s) of "{equipment.name}" available right now.'
                })

        return data

    def validate_customer(self, customer):
        request = self.context.get('request')
        tenant = get_request_tenant(request.user) if request else None
        if tenant and customer.tenant_id != tenant.id:
            raise serializers.ValidationError('Customer not found')
        return customer

    def validate_equipment(self, equipment):
        request = self.context.get('request')
        tenant = get_request_tenant(request.user) if request else None
        if tenant and equipment.tenant_id != tenant.id:
            raise serializers.ValidationError('Equipment not found')
        return equipment


class RentalReturnSerializer(serializers.Serializer):
    """Small payload for the `return` action — just the outcome, everything else stays as-is."""
    return_date = serializers.DateField(required=False)
    status = serializers.ChoiceField(choices=[('returned', 'Returned'), ('damaged', 'Damaged'), ('lost', 'Lost')], default='returned')
    notes = serializers.CharField(required=False, allow_blank=True)
