from rest_framework import viewsets, permissions, status
from rest_framework.response import Response

from .models import SupportTicket
from .serializers import SupportTicketSerializer


class SupportTicketViewSet(viewsets.ModelViewSet):
    """
    Support tickets for the current tenant. Admins/managers see every ticket
    raised in the workspace; everyone else only sees their own submissions.
    """
    serializer_class = SupportTicketSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

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

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = serializer.save(tenant=tenant, user=request.user)

        from users.audit_utils import audit_log
        audit_log(
            request, 'create', 'settings',
            f'Submitted support ticket: {ticket.subject}',
            tenant=tenant, user=request.user,
        )

        return Response(self.get_serializer(ticket).data, status=status.HTTP_201_CREATED)
