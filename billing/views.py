from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from django.http import HttpResponse

from billing.models import BillingPayment
from billing.invoice import render_invoice_html, user_can_view_payment
from billing.serializers import CheckoutSerializer, VerifyPaymentSerializer
from billing import services
from billing.account_limits import get_user_account_limits
from tenants.utils import get_request_tenant


class BillingOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Billing'], summary='Get billing overview')
    def get(self, request):
        tenant = get_request_tenant(request.user)
        return Response(services.billing_overview(tenant, request.user))


class BillingAccountLimitsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Billing'],
        summary='Get account org-creation and module limits',
        description='Used when creating a new organization before a tenant context exists.',
    )
    def get(self, request):
        return Response(get_user_account_limits(request.user))


class BillingCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Billing'], summary='Start eSewa checkout for a plan')
    def post(self, request):
        context_tenant = get_request_tenant(request.user)
        tenant = services.resolve_checkout_tenant(request.user, context_tenant)

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            form = services.initiate_checkout(
                tenant,
                request.user,
                serializer.validated_data['plan_code'],
            )
            return Response(form, status=status.HTTP_201_CREATED)
        except PermissionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class BillingVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Billing'], summary='Verify eSewa payment and activate subscription')
    def post(self, request):
        tenant = get_request_tenant(request.user)
        if not tenant:
            return Response({'detail': 'No organization in context'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = VerifyPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        transaction_uuid = serializer.validated_data['transaction_uuid']
        encoded_data = serializer.validated_data.get('data') or None

        if not transaction_uuid and encoded_data:
            from billing.esewa import decode_callback_data
            transaction_uuid = decode_callback_data(encoded_data).get('transaction_uuid')

        if not transaction_uuid:
            return Response({'detail': 'transaction_uuid is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = services.verify_and_activate(
                tenant,
                request.user,
                transaction_uuid,
                encoded_data,
            )
            return Response(result)
        except PermissionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {'detail': f'Payment verification failed: {exc}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class BillingPaymentInvoiceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Billing'], summary='Download subscription payment invoice (HTML/PDF)')
    def get(self, request, payment_id: int):
        try:
            payment = BillingPayment.objects.select_related('tenant', 'initiated_by').get(pk=payment_id)
        except BillingPayment.DoesNotExist:
            return Response({'detail': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)

        if not user_can_view_payment(request.user, payment):
            return Response({'detail': 'You do not have access to this invoice'}, status=status.HTTP_403_FORBIDDEN)

        if payment.status != 'completed':
            return Response({'detail': 'Invoice is only available for completed payments'}, status=status.HTTP_400_BAD_REQUEST)

        html = render_invoice_html(payment, request.user)
        filename = f'invoice-{payment.transaction_uuid}.html'
        response = HttpResponse(html, content_type='text/html; charset=utf-8')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
