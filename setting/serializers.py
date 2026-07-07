from rest_framework import serializers

from setting.models import SiteSettings


class SiteSettingsPublicSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    favicon_url = serializers.SerializerMethodField()
    og_image_url = serializers.SerializerMethodField()
    effective_seo_title = serializers.SerializerMethodField()

    class Meta:
        model = SiteSettings
        fields = [
            'site_name',
            'tagline',
            'logo_url',
            'favicon_url',
            'seo_title',
            'effective_seo_title',
            'meta_description',
            'meta_keywords',
            'og_image_url',
            'allow_search_indexing',
            'updated_at',
        ]

    def _absolute_media_url(self, file_field) -> str | None:
        if not file_field:
            return None
        request = self.context.get('request')
        url = file_field.url
        if request and url.startswith('/'):
            return request.build_absolute_uri(url)
        return url

    def get_logo_url(self, obj):
        return self._absolute_media_url(obj.logo)

    def get_favicon_url(self, obj):
        return self._absolute_media_url(obj.favicon)

    def get_og_image_url(self, obj):
        return self._absolute_media_url(obj.og_image)

    def get_effective_seo_title(self, obj):
        return obj.seo_title or obj.site_name
