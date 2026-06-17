from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import User


class CustomJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that ensures the user's tenant is loaded
    """
    
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
