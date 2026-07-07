from django.urls import path

from setting.views import site_settings_public

urlpatterns = [
    path('site/', site_settings_public, name='site_settings_public'),
]
