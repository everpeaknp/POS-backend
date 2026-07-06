from rest_framework_simplejwt.authentication import JWTAuthentication
from tenants.middleware import set_current_tenant
from tenants.utils import get_request_tenant
from .models import User


class CustomJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that ensures the user's tenant is loaded
    and thread-local tenant context is set for TenantManager queries.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            user, validated_token = result
            set_current_tenant(get_request_tenant(user))
        return result

    def get_user(self, validated_token):
        """
        Override to ensure tenant relationship is loaded
        """
        try:
            user_id = validated_token.get('user_id')
            user = User.objects.select_related('tenant').get(id=user_id)
            return user
        except User.DoesNotExist:
            return None
