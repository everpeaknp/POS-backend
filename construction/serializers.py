from rest_framework import serializers
from .models import Site, Worker, Attendance, DailyLog, MaterialConsumption, Equipment, EquipmentUsageLog
from decimal import Decimal


class SiteSerializer(serializers.ModelSerializer):
    """Serializer for Construction Sites with calculated fields"""
    manager_name = serializers.CharField(source='manager.name', read_only=True)
    manager_designation = serializers.CharField(source='manager.designation', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    
    # Calculated fields
    material_cost = serializers.SerializerMethodField()
    labor_cost = serializers.SerializerMethodField()
    other_expenses = serializers.SerializerMethodField()
    actual_spend = serializers.SerializerMethodField()
    remaining_budget = serializers.SerializerMethodField()
    budget_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = Site
        fields = [
            'id', 'name', 'location', 'client_name', 'allocated_budget',
            'start_date', 'estimated_end_date', 'actual_end_date',
            'manager', 'manager_name', 'manager_designation', 'status', 'warehouse', 'warehouse_name',
            'description', 'created_at', 'updated_at',
            # Calculated fields
            'material_cost', 'labor_cost', 'other_expenses', 'actual_spend',
            'remaining_budget', 'budget_percentage'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'manager_name', 'manager_designation', 'warehouse_name',
            'material_cost', 'labor_cost', 'other_expenses', 'actual_spend',
            'remaining_budget', 'budget_percentage'
        ]
    
    def get_material_cost(self, obj):
        return float(obj.get_material_cost())
    
    def get_labor_cost(self, obj):
        return float(obj.get_labor_cost())
    
    def get_other_expenses(self, obj):
        return float(obj.get_other_expenses())
    
    def get_actual_spend(self, obj):
        return float(obj.get_actual_spend())
    
    def get_remaining_budget(self, obj):
        return float(obj.get_remaining_budget())
    
    def get_budget_percentage(self, obj):
        return float(obj.get_budget_percentage())


class WorkerSerializer(serializers.ModelSerializer):
    """Serializer for Construction Workers"""
    assigned_site_name = serializers.CharField(source='assigned_site.name', read_only=True)
    
    class Meta:
        model = Worker
        fields = [
            'id', 'name', 'phone', 'address', 'category', 'daily_wage',
            'assigned_site', 'assigned_site_name', 'status', 'id_number',
            'emergency_contact', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'assigned_site_name']


class AttendanceSerializer(serializers.ModelSerializer):
    """Serializer for Worker Attendance"""
    worker_name = serializers.CharField(source='worker.name', read_only=True)
    worker_category = serializers.CharField(source='worker.category', read_only=True)
    site_name = serializers.CharField(source='site.name', read_only=True)
    marked_by_name = serializers.CharField(source='marked_by.username', read_only=True)
    
    class Meta:
        model = Attendance
        fields = [
            'id', 'worker', 'worker_name', 'worker_category', 'site', 'site_name',
            'date', 'status', 'check_in', 'check_out', 'wage_amount',
            'notes', 'marked_by', 'marked_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'wage_amount', 'marked_by', 'marked_by_name', 'created_at',
            'updated_at', 'worker_name', 'worker_category', 'site_name'
        ]
    
    def create(self, validated_data):
        # Set marked_by from request user
        validated_data['marked_by'] = self.context['request'].user
        return super().create(validated_data)


class MaterialConsumptionSerializer(serializers.ModelSerializer):
    """Serializer for Material Consumption"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    product_unit = serializers.CharField(source='product.unit.abbreviation', read_only=True)
    site_name = serializers.CharField(source='site.name', read_only=True)
    
    class Meta:
        model = MaterialConsumption
        fields = [
            'id', 'daily_log', 'site', 'site_name', 'product', 'product_name', 'product_sku',
            'product_unit', 'quantity', 'unit_cost', 'total_cost', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'total_cost', 'created_at', 'updated_at',
            'product_name', 'product_sku', 'product_unit', 'site_name'
        ]
        extra_kwargs = {
            'daily_log': {'required': False, 'allow_null': True},
        }
    
    def validate(self, data):
        """Validate that sufficient stock is available"""
        from inventory.models import Stock
        
        product = data.get('product')
        site = data.get('site')
        quantity = data.get('quantity')
        
        # Check stock availability
        try:
            stock = Stock.objects.get(
                tenant=self.context['request'].user.tenant,
                product=product,
                warehouse=site.warehouse
            )
            if stock.quantity < quantity:
                raise serializers.ValidationError(
                    f"Insufficient stock. Available: {stock.quantity}, Requested: {quantity}"
                )
        except Stock.DoesNotExist:
            raise serializers.ValidationError(
                f"No stock available for {product.name} at {site.warehouse.name}"
            )
        
        return data


class DailyLogSerializer(serializers.ModelSerializer):
    """Serializer for Daily Site Logs with nested material consumption"""
    site_name = serializers.CharField(source='site.name', read_only=True)
    submitted_by_name = serializers.CharField(source='submitted_by.username', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.username', read_only=True)
    material_consumptions = MaterialConsumptionSerializer(many=True, read_only=True)
    is_editable = serializers.SerializerMethodField()
    hours_until_immutable = serializers.SerializerMethodField()
    
    class Meta:
        model = DailyLog
        fields = [
            'id', 'site', 'site_name', 'date', 'work_description', 'progress_notes',
            'progress_photos', 'weather', 'other_expenses', 'other_expenses_description',
            'submitted_by', 'submitted_by_name', 'reviewed_by', 'reviewed_by_name',
            'reviewed_at', 'manager_comments', 'material_consumptions',
            'is_editable', 'hours_until_immutable',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'submitted_by', 'submitted_by_name', 'reviewed_by', 'reviewed_by_name',
            'reviewed_at', 'created_at', 'updated_at', 'site_name', 'material_consumptions',
            'is_editable', 'hours_until_immutable'
        ]
    
    def get_is_editable(self, obj):
        """Check if log can be edited (within 24 hours)"""
        return obj.is_editable()
    
    def get_hours_until_immutable(self, obj):
        """Get hours remaining until log becomes immutable"""
        return round(obj.get_hours_until_immutable(), 1)
    
    def create(self, validated_data):
        # Set submitted_by from request user
        validated_data['submitted_by'] = self.context['request'].user
        return super().create(validated_data)


class EquipmentSerializer(serializers.ModelSerializer):
    """Serializer for Construction Equipment"""
    assigned_site_name = serializers.CharField(source='assigned_site.name', read_only=True)
    
    class Meta:
        model = Equipment
        fields = [
            'id', 'name', 'equipment_type', 'ownership_type', 'purchase_cost',
            'rental_cost_per_day', 'assigned_site', 'assigned_site_name', 'status',
            'registration_number', 'purchase_date', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'assigned_site_name']


class EquipmentUsageLogSerializer(serializers.ModelSerializer):
    """Serializer for Equipment Usage Logs"""
    equipment_name = serializers.CharField(source='equipment.name', read_only=True)
    site_name = serializers.CharField(source='site.name', read_only=True)
    
    class Meta:
        model = EquipmentUsageLog
        fields = [
            'id', 'equipment', 'equipment_name', 'site', 'site_name', 'daily_log',
            'date', 'hours_used', 'cost', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'cost', 'created_at', 'updated_at',
            'equipment_name', 'site_name'
        ]


# Nested serializer for creating daily logs with material consumption
class DailyLogCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating daily logs with nested material consumption"""
    
    # Nested serializer for material consumption (without required fields)
    class MaterialConsumptionNestedSerializer(serializers.Serializer):
        product = serializers.CharField()  # Will be converted to Product instance
        quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
        unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2)
        notes = serializers.CharField(required=False, allow_blank=True, default='')
        
        def validate_product(self, value):
            """Validate and convert product ID to Product instance"""
            from inventory.models import Product
            try:
                product = Product.objects.get(
                    id=value,
                    tenant=self.context['request'].user.tenant
                )
                return product
            except Product.DoesNotExist:
                raise serializers.ValidationError(f"Product with ID {value} not found")
    
    material_consumptions = MaterialConsumptionNestedSerializer(many=True, required=False)
    
    class Meta:
        model = DailyLog
        fields = [
            'site', 'date', 'work_description', 'progress_notes', 'progress_photos',
            'weather', 'other_expenses', 'other_expenses_description',
            'material_consumptions'
        ]
    
    def validate(self, data):
        """Validate that no daily log exists for this site and date"""
        site = data.get('site')
        date = data.get('date')
        tenant = self.context['request'].user.tenant
        
        # Check if daily log already exists for this site and date
        if DailyLog.objects.filter(tenant=tenant, site=site, date=date).exists():
            raise serializers.ValidationError({
                'date': f'A daily log already exists for {site.name} on {date}. Only one log per site per day is allowed.'
            })
        
        return data
    
    def create(self, validated_data):
        material_consumptions_data = validated_data.pop('material_consumptions', [])
        
        # Set submitted_by from request user
        validated_data['submitted_by'] = self.context['request'].user
        validated_data['tenant'] = self.context['request'].user.tenant
        
        # Create daily log
        daily_log = DailyLog.objects.create(**validated_data)
        
        # Create material consumptions
        for consumption_data in material_consumptions_data:
            MaterialConsumption.objects.create(
                daily_log=daily_log,
                site=daily_log.site,
                tenant=daily_log.tenant,
                **consumption_data
            )
        
        return daily_log
