"""
Custom authentication backends for email-based login
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()


class EmailBackend(ModelBackend):
    """
    Custom authentication backend that allows users to log in using their email address
    instead of username.
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate user by email and password.
        
        Args:
            request: The HTTP request
            username: Can be either username or email (we treat it as email)
            password: User's password
            **kwargs: Additional keyword arguments
            
        Returns:
            User object if authentication successful, None otherwise
        """
        # Try to get the email from kwargs first (for email-based login)
        email = kwargs.get('email', username)
        
        if email is None or password is None:
            return None
        
        try:
            # Try to find user by email — use filter().first() to handle
            # edge case where duplicate emails exist in the database
            user = User.objects.filter(email=email).order_by('id').first()
            if user is None:
                User().set_password(password)
                return None
        except Exception:
            User().set_password(password)
            return None
        
        # Check password
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        
        return None
    
    def get_user(self, user_id):
        """
        Get user by ID.
        
        Args:
            user_id: User's primary key
            
        Returns:
            User object if found, None otherwise
        """
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
        
        return user if self.user_can_authenticate(user) else None
