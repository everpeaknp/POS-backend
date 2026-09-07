"""Send the weekly security digest to users who opted in (Settings > Notifications)."""

from django.core.management.base import BaseCommand

from users.security_digest import send_weekly_security_digest


class Command(BaseCommand):
    help = 'Email + in-app notify users who enabled weekly security log exports.'

    def handle(self, *args, **options):
        sent = send_weekly_security_digest()
        self.stdout.write(self.style.SUCCESS(f'Sent {sent} weekly security digest(s).'))
