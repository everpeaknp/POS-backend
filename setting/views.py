from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from setting.models import DefaultAppearanceSettings, SiteSettings
from setting.serializers import DefaultAppearanceSettingsPublicSerializer, SiteSettingsPublicSerializer


@extend_schema(
    tags=['Settings'],
    summary='Public site settings',
    description='Site name, logo, favicon, and SEO defaults for the customer app.',
)
@api_view(['GET'])
@permission_classes([AllowAny])
def site_settings_public(request):
    site = SiteSettings.get_solo()
    serializer = SiteSettingsPublicSerializer(site, context={'request': request})
    return Response(serializer.data)


@extend_schema(
    tags=['Settings'],
    summary='Public default appearance settings',
    description=(
        'The platform-wide default theme/accent/sidebar/navbar/radius set by admins '
        '(see /admin/setting/defaultappearancesettings/). Used to brand pages an '
        'anonymous visitor sees before they have any account-level preferences of '
        'their own, such as the login/signup/forgot-password screens.'
    ),
)
@api_view(['GET'])
@permission_classes([AllowAny])
def default_appearance_public(request):
    defaults = DefaultAppearanceSettings.get_solo()
    serializer = DefaultAppearanceSettingsPublicSerializer(defaults)
    return Response(serializer.data)
