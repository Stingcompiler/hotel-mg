from django.core.management.base import BaseCommand

from apps.backup import keys


class Command(BaseCommand):
    help = "Owner PC: create the age key pair once and print the public key for the reception's backup settings."

    def handle(self, *args, **options):
        self.stdout.write(keys.generate())
