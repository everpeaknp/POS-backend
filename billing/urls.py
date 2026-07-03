from django.urls import path

from billing.views import BillingCheckoutView, BillingOverviewView, BillingVerifyView

urlpatterns = [
    path('overview/', BillingOverviewView.as_view(), name='billing-overview'),
    path('checkout/', BillingCheckoutView.as_view(), name='billing-checkout'),
    path('verify/', BillingVerifyView.as_view(), name='billing-verify'),
]
