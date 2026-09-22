"""
Fallback module for unfold admin classes when unfold is not installed.
This prevents ImportError for all admin.py files that import from unfold.
"""

from django.contrib import admin

# Provide fallback classes
class ModelAdmin(admin.ModelAdmin):
    pass

class StackedInline(admin.StackedInline):
    pass

class TabularInline(admin.TabularInline):
    pass

# Provide fallback forms
class AdminPasswordChangeForm:
    pass

class UserChangeForm:
    pass

class UserCreationForm:
    pass

# Provide fallback widgets
class UnfoldAdminCheckboxSelectMultipleWidget:
    pass

class UnfoldAdminTextareaWidget:
    pass

class UnfoldAdminPasswordWidget:
    pass

class UnfoldAdminSelectWidget:
    pass

# Provide fallback decorators
def display(*args, **kwargs):
    def decorator(func):
        return func
    if callable(args[0] if args else None):
        return decorator(args[0])
    return decorator
