"""Helpers for custom pages that use the Unfold admin shell."""

from django.contrib import admin
from django.template.response import TemplateResponse


def admin_render(request, template_name: str, context: dict | None = None):
    """Render inside the Django admin / Unfold layout (sidebar, apps, permissions)."""
    ctx = {
        **admin.site.each_context(request),
        'is_popup': False,
        **(context or {}),
    }
    return TemplateResponse(request, template_name, ctx)
