from rest_framework import serializers

from .models import SupportTicket


class SupportTicketSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            'id', 'user', 'user_name', 'subject', 'category', 'category_display',
            'priority', 'priority_display', 'status', 'status_display', 'message',
            'created_at', 'updated_at', 'resolved_at',
        ]
        read_only_fields = ['id', 'user', 'status', 'created_at', 'updated_at', 'resolved_at']

    def get_user_name(self, obj):
        if obj.user:
            return f'{obj.user.first_name} {obj.user.last_name}'.strip() or obj.user.username
        return 'Deleted user'

    def validate_subject(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Subject is required.')
        return value

    def validate_message(self, value):
        value = value.strip()
        if len(value) < 10:
            raise serializers.ValidationError('Please provide at least 10 characters describing your issue.')
        return value
