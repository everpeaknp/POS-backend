from django.urls import path

from setting.views import default_appearance_public, site_settings_public

urlpatterns = [
    path('site/', site_settings_public, name='site_settings_public'),
    path('default-appearance/', default_appearance_public, name='default_appearance_public'),
]
