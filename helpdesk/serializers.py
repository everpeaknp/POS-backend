from rest_framework import serializers

from .models import SupportTicket, SupportTicketMessage

MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf'}


def validate_attachment_file(attachment):
    """Shared validation for a message/ticket attachment upload."""
    if not attachment:
        return
    if attachment.size > MAX_ATTACHMENT_SIZE:
        raise serializers.ValidationError('Attachment must be smaller than 10MB.')
    if attachment.content_type not in ALLOWED_ATTACHMENT_TYPES:
        raise serializers.ValidationError('Attach an image (JPG, PNG, GIF, WEBP) or PDF file.')


class SupportTicketMessageSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    message_type_display = serializers.CharField(source='get_message_type_display', read_only=True)
    attachment_url = serializers.SerializerMethodField()
    attachment_name = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicketMessage
        fields = [
            'id', 'ticket', 'author', 'author_name', 'is_staff',
            'message_type', 'message_type_display', 'body',
            'attachment', 'attachment_url', 'attachment_name',
            'old_status', 'new_status', 'created_at',
        ]
        read_only_fields = fields

    def get_author_name(self, obj):
        if obj.author:
            return f'{obj.author.first_name} {obj.author.last_name}'.strip() or obj.author.username
        return 'Support' if obj.is_staff else 'System'

    def get_attachment_url(self, obj):
        if obj.attachment:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.attachment.url)
            return obj.attachment.url
        return None

    def get_attachment_name(self, obj):
        if obj.attachment:
            return obj.attachment.name.rsplit('/', 1)[-1]
        return None


class SupportTicketMessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True, default='')
    attachment = serializers.FileField(required=False, allow_null=True)

    def validate(self, attrs):
        body = (attrs.get('body') or '').strip()
        attachment = attrs.get('attachment')
        if not body and not attachment:
            raise serializers.ValidationError('Write a message or attach a file.')
        validate_attachment_file(attachment)
        attrs['body'] = body
        return attrs


class SupportTicketSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    message_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            'id', 'user', 'user_name', 'subject', 'category', 'category_display',
            'priority', 'priority_display', 'status', 'status_display', 'message',
            'message_count', 'last_message', 'created_at', 'updated_at', 'resolved_at',
        ]
        read_only_fields = ['id', 'user', 'status', 'created_at', 'updated_at', 'resolved_at']

    def get_user_name(self, obj):
        if obj.user:
            return f'{obj.user.first_name} {obj.user.last_name}'.strip() or obj.user.username
        return 'Deleted user'

    def get_message_count(self, obj):
        return obj.messages.filter(message_type=SupportTicketMessage.TYPE_MESSAGE).count()

    def get_last_message(self, obj):
        last = obj.messages.filter(message_type=SupportTicketMessage.TYPE_MESSAGE).order_by('-created_at').first()
        if not last:
            return None
        return {
            'body': last.body[:140],
            'is_staff': last.is_staff,
            'created_at': last.created_at,
        }

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


class SupportTicketDetailSerializer(SupportTicketSerializer):
    messages = SupportTicketMessageSerializer(many=True, read_only=True)

    class Meta(SupportTicketSerializer.Meta):
        fields = SupportTicketSerializer.Meta.fields + ['messages']
