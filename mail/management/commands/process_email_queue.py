from django.core.management.base import BaseCommand

from mail.services import process_email_queue


class Command(BaseCommand):
    help = 'Process queued outbound emails'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50)

    def handle(self, *args, **options):
        result = process_email_queue(limit=options['limit'])
        self.stdout.write(self.style.SUCCESS(str(result)))
