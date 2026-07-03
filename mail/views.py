from django.http import HttpResponse, HttpResponseRedirect
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from mail import services
from mail.models import EmailLog


class MailDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_superuser:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        return Response(services.mail_dashboard_stats())


class TrackOpenView(APIView):
    permission_classes = []

    def get(self, request, tracking_id):
        try:
            log = EmailLog.objects.get(tracking_id=tracking_id)
            log.open_count += 1
            if not log.opened_at:
                log.opened_at = timezone.now()
                if log.status in ('sent', 'delivered'):
                    log.status = 'opened'
            log.save(update_fields=['open_count', 'opened_at', 'status'])
        except EmailLog.DoesNotExist:
            pass
        pixel = (
            b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff'
            b'\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00'
            b'\x01\x00\x00\x02\x02D\x01\x00;'
        )
        return HttpResponse(pixel, content_type='image/gif')
