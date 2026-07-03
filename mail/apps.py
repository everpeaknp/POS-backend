from django.apps import AppConfig


class MailConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mail'
    verbose_name = 'Mail'

    def ready(self):
        import mail.signals  # noqa: F401
