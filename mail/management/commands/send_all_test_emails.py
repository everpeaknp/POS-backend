from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from mail.models import SmtpSettings
from mail.services import send_all_test_emails


class Command(BaseCommand):
    help = 'Send all active email templates with sample data to a test inbox'

    def add_arguments(self, parser):
        parser.add_argument(
            '--to',
            dest='to_email',
            help='Recipient email (defaults to SMTP sender email, then superuser email)',
        )

    def handle(self, *args, **options):
        to_email = options.get('to_email')
        if not to_email:
            smtp = SmtpSettings.get_solo()
            to_email = smtp.sender_email
        if not to_email:
            user = get_user_model().objects.filter(is_superuser=True).first()
            to_email = user.email if user else None
        if not to_email:
            self.stderr.write(self.style.ERROR('No recipient email. Pass --to or configure SMTP sender email.'))
            return

        self.stdout.write(f'Sending all test emails to {to_email}...')
        sent, failed = send_all_test_emails(to_email)

        for slug in sent:
            self.stdout.write(self.style.SUCCESS(f'  sent: {slug}'))
        for err in failed:
            self.stdout.write(self.style.ERROR(f'  failed: {err}'))

        if failed:
            self.stderr.write(self.style.WARNING(f'Done: {len(sent)} sent, {len(failed)} failed'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Done: {len(sent)} test emails sent to {to_email}'))
