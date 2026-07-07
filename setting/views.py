from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from setting.models import SiteSettings
from setting.serializers import SiteSettingsPublicSerializer


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
