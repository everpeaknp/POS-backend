from core_backend.admin_utils import admin_render
from setting.models import EsewaSettings, GoogleOAuthSettings, SiteSettings


def setting_hub(request):
    """Platform settings hub at /admin/setting/."""
    esewa = EsewaSettings.get_solo()
    google = GoogleOAuthSettings.get_solo()
    site = SiteSettings.get_solo()
    return admin_render(request, 'admin/setting/hub.html', {
        'title': 'Platform settings',
        'esewa': esewa,
        'google': google,
        'site': site,
    })
