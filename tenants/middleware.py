import threading
from django.utils.deprecation import MiddlewareMixin

# Thread-local storage for current tenant
_thread_locals = threading.local()


def get_current_tenant():
    """Get the current tenant from thread-local storage."""
    return getattr(_thread_locals, 'tenant', None)


def set_current_tenant(tenant):
    """Set the current tenant in thread-local storage."""
    _thread_locals.tenant = tenant


from tenants.utils import get_request_tenant


class TenantMiddleware(MiddlewareMixin):
    """
    Middleware to identify and set the current tenant based on authenticated user.
    This enables automatic tenant filtering across all queries.
    """
    
    def process_request(self, request):
        """
        Extract tenant from authenticated user and store in thread-local.
        """
        tenant = None
        
        if request.user and request.user.is_authenticated:
            tenant = get_request_tenant(request.user)
        
        set_current_tenant(tenant)
        request.tenant = tenant
    
    def process_response(self, request, response):
        """
        Clear tenant from thread-local after request processing.
        """
        set_current_tenant(None)
        return response
    
    def process_exception(self, request, exception):
        """
        Clear tenant from thread-local on exception.
        """
        set_current_tenant(None)
