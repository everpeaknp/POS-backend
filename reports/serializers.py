from rest_framework import serializers
from .models import CustomReport


class CustomReportSerializer(serializers.ModelSerializer):
    """Serializer for Custom Report model"""
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    last_run_display = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomReport
        fields = [
            'id', 'name', 'description', 'report_type', 'module',
            'fields', 'filters', 'grouping', 'sorting', 'chart_config',
            'schedule', 'last_run', 'last_run_display',
            'created_by', 'created_by_name', 'is_shared',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at', 'last_run']
        extra_kwargs = {
            'module': {'required': False},  # Allow partial updates without module
        }
    
    def get_last_run_display(self, obj):
        """Format last run date in Nepali format"""
        if obj.last_run:
            return obj.last_run.strftime('%Y-%m-%d')
        return None
    
    def create(self, validated_data):
        """Set created_by to current user"""
        validated_data['created_by'] = self.context['request'].user
        validated_data['tenant'] = self.context['request'].user.tenant
        return super().create(validated_data)


class CustomReportRunSerializer(serializers.Serializer):
    """Serializer for running a custom report with parameters"""
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    additional_filters = serializers.JSONField(required=False, default=dict)
