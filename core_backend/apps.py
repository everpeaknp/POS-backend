from django.apps import AppConfig


class CoreBackendConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core_backend'

    def ready(self):
        from core_backend.platform_admin import setup_platform_admin
        setup_platform_admin()
