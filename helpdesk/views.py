from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from .models import SupportTicket, SupportTicketMessage
from .serializers import (
    SupportTicketSerializer,
    SupportTicketDetailSerializer,
    SupportTicketMessageSerializer,
    SupportTicketMessageCreateSerializer,
    validate_attachment_file,
)

REOPENABLE_STATUSES = ('resolved',)


class SupportTicketViewSet(viewsets.ModelViewSet):
    """
    Support tickets for the current tenant. Admins/managers see every ticket
    raised in the workspace; everyone else only sees their own submissions.
    """
    serializer_class = SupportTicketSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return SupportTicketDetailSerializer
        return SupportTicketSerializer

    def get_queryset(self):
        from tenants.utils import get_request_tenant, is_tenant_admin

        user = self.request.user
        tenant = get_request_tenant(user)
        if not tenant:
            return SupportTicket.objects.none()

        qs = SupportTicket.objects.filter(tenant=tenant).select_related('user')
        if is_tenant_admin(user, tenant):
            return qs
        return qs.filter(user=user)

    def create(self, request, *args, **kwargs):
        from tenants.utils import get_request_tenant

        tenant = get_request_tenant(request.user)
        if not tenant:
            return Response(
                {'detail': 'You must be assigned to a workplace to submit a support ticket.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        attachment = request.FILES.get('attachment')
        validate_attachment_file(attachment)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = serializer.save(tenant=tenant, user=request.user)

        # The initial description becomes the first entry in the timeline,
        # so the detail/chat view can just render ticket.messages in order.
        SupportTicketMessage.objects.create(
            ticket=ticket,
            author=request.user,
            is_staff=False,
            message_type=SupportTicketMessage.TYPE_MESSAGE,
            body=ticket.message,
            attachment=attachment,
        )

        from users.audit_utils import audit_log
        audit_log(
            request, 'create', 'settings',
            f'Submitted support ticket: {ticket.subject}',
            tenant=tenant, user=request.user,
        )

        return Response(self.get_serializer(ticket).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'])
    def messages(self, request, pk=None):
        ticket = self.get_object()

        if request.method == 'GET':
            msgs = ticket.messages.select_related('author').order_by('created_at')
            serializer = SupportTicketMessageSerializer(msgs, many=True, context={'request': request})
            return Response(serializer.data)

        if ticket.status == 'closed':
            return Response(
                {'detail': 'This ticket is closed and no longer accepts new messages.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        create_serializer = SupportTicketMessageCreateSerializer(data=request.data)
        create_serializer.is_valid(raise_exception=True)

        msg = SupportTicketMessage.objects.create(
            ticket=ticket,
            author=request.user,
            is_staff=False,
            message_type=SupportTicketMessage.TYPE_MESSAGE,
            body=create_serializer.validated_data['body'],
            attachment=create_serializer.validated_data.get('attachment'),
        )

        if ticket.status in REOPENABLE_STATUSES:
            old_status = ticket.status
            ticket.status = 'open'
            ticket.save(update_fields=['status', 'updated_at'])
            SupportTicketMessage.objects.create(
                ticket=ticket,
                message_type=SupportTicketMessage.TYPE_STATUS_CHANGE,
                old_status=old_status,
                new_status='open',
                body='Ticket reopened after a new reply.',
            )

        serializer = SupportTicketMessageSerializer(msg, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)
