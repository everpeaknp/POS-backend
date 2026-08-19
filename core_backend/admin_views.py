from django.shortcuts import redirect

from setting.models import EsewaSettings, GoogleOAuthSettings


def platform_dashboard(request):
    # The dashboard now lives at /admin/ itself (see
    # core_backend.platform_admin._install_dashboard_index). This URL is
    # kept only so old links/bookmarks to /admin/platform/ still resolve.
    return redirect('admin:index')


def legacy_esewa_settings_change(request, object_id=None):
    """Redirect old /admin/billing/esewasettings/... URLs to setting app."""
    settings_obj = EsewaSettings.get_solo()
    return redirect('admin:setting_esewasettings_change', settings_obj.pk)


def legacy_google_oauth_settings_change(request, object_id=None):
    """Redirect old /admin/billing/googleoauthsettings/... URLs to setting app."""
    settings_obj = GoogleOAuthSettings.get_solo()
    return redirect('admin:setting_googleoauthsettings_change', settings_obj.pk)
