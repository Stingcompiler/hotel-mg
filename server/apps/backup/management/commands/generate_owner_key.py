from django.core.management.base import BaseCommand

from apps.backup import keys


class Command(BaseCommand):
    # Runs on a new owner PC before its first import: no hotel id yet, and the model checks would need one.
    requires_system_checks = []
    help = "Owner PC: create the age key pair once and print the public key for the reception's backup settings."

    def handle(self, *args, **options):
        self.stdout.write(keys.generate())
