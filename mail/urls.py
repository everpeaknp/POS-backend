from django.urls import path

from mail.views import MailDashboardAPIView, TrackOpenView

urlpatterns = [
    path('dashboard/', MailDashboardAPIView.as_view(), name='mail-dashboard-api'),
    path('track/<uuid:tracking_id>/open/', TrackOpenView.as_view(), name='mail-track-open'),
]
