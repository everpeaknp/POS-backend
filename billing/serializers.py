from rest_framework import serializers

from billing.plans import plan_available_for_checkout


class CheckoutSerializer(serializers.Serializer):
    plan_code = serializers.CharField(max_length=32)

    def validate_plan_code(self, value):
        if not plan_available_for_checkout(value):
            raise serializers.ValidationError('Invalid or inactive plan')
        return value


class VerifyPaymentSerializer(serializers.Serializer):
    transaction_uuid = serializers.CharField(max_length=64, required=False, allow_blank=True)
    data = serializers.CharField(required=False, allow_blank=True)
