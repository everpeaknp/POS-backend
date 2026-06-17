"""
Django Python 3.14 Compatibility Patch

This patch fixes the AttributeError: 'super' object has no attribute 'dicts'
that occurs when using Django 5.0.x with Python 3.14.

The issue is in Django's template context __copy__ method which tries to
access super().dicts, but Python 3.14 changed how super() works.

This should be removed once Django officially supports Python 3.14.
"""

import django.template.context
from copy import copy


# Store the original __copy__ methods
_original_context_copy = django.template.context.Context.__copy__
_original_request_context_copy = django.template.context.RequestContext.__copy__


def patched_context_copy(self):
    """
    Patched __copy__ method for Django's Context class.
    
    This fixes the Python 3.14 compatibility issue where super().dicts
    raises AttributeError.
    """
    try:
        # Try the original method first (works on Python < 3.14)
        return _original_context_copy(self)
    except (AttributeError, TypeError) as e:
        error_msg = str(e)
        if "'super' object has no attribute 'dicts'" in error_msg or "missing 1 required positional argument" in error_msg:
            # Python 3.14 fix: manually copy the context
            duplicate = self.__class__.__new__(self.__class__)
            # Copy all the dicts from the stack
            duplicate.dicts = [d.copy() for d in self.dicts]
            # Copy other attributes
            if hasattr(self, '_processors'):
                duplicate._processors = self._processors
            if hasattr(self, '_processors_index'):
                duplicate._processors_index = self._processors_index
            return duplicate
        else:
            # Re-raise if it's a different error
            raise


def patched_request_context_copy(self):
    """
    Patched __copy__ method for Django's RequestContext class.
    
    This fixes the Python 3.14 compatibility issue.
    """
    try:
        # Try the original method first (works on Python < 3.14)
        return _original_request_context_copy(self)
    except (AttributeError, TypeError) as e:
        error_msg = str(e)
        if "'super' object has no attribute 'dicts'" in error_msg or "missing 1 required positional argument" in error_msg or "'RequestContext' object has no attribute '_request'" in error_msg:
            # Python 3.14 fix: manually copy the request context
            # First, use the base Context copy to get the dicts
            duplicate = patched_context_copy(self)
            
            # Now convert it to a RequestContext by setting the request
            # Try different attribute names that Django might use
            request_obj = None
            for attr_name in ['_request', 'request']:
                if hasattr(self, attr_name):
                    request_obj = getattr(self, attr_name)
                    break
            
            # If we found a request, initialize the RequestContext properly
            if request_obj is not None:
                # Re-create as RequestContext with the request
                duplicate.__class__ = self.__class__
                duplicate.__dict__.update(self.__dict__)
                # Ensure dicts are copied
                duplicate.dicts = [d.copy() for d in self.dicts]
            
            return duplicate
        else:
            # Re-raise if it's a different error
            raise


# Apply the patches
django.template.context.Context.__copy__ = patched_context_copy
django.template.context.RequestContext.__copy__ = patched_request_context_copy


print("[OK] Django Python 3.14 compatibility patch applied (Context + RequestContext)")

