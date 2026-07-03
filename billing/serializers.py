from rest_framework import serializers

from billing.plans import SUBSCRIPTION_PLANS


class CheckoutSerializer(serializers.Serializer):
    plan_code = serializers.ChoiceField(choices=list(SUBSCRIPTION_PLANS.keys()))


class VerifyPaymentSerializer(serializers.Serializer):
    transaction_uuid = serializers.CharField(max_length=64, required=False, allow_blank=True)
    data = serializers.CharField(required=False, allow_blank=True)
