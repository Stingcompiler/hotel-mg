"""The owner forgot the only owner password: an administrator of the reception PC sets a new one.

    skytowers-server.exe manage reset_password admin

The password is asked twice (or given with --password for scripts). The account is unlocked and its backup key
slot is rewritten with the new password, so backups keep opening on another PC. Audited as
``user.reset_password_offline``.
"""

from getpass import getpass

from django.core.management.base import BaseCommand, CommandError

from apps.accounts import services
from apps.core.errors import ApiError


class Command(BaseCommand):
    help = "Set a new password for an account (e.g. the owner who forgot it). Run as an administrator of this PC."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--password", help="the new password (asked twice when omitted)")

    def handle(self, *args, username, password=None, **options):
        if password is None:
            password = getpass("كلمة المرور الجديدة: ")
            if password != getpass("أعد كتابتها: "):
                raise CommandError("كلمتا المرور غير متطابقتين.")
        try:
            user = services.reset_password_offline(username, password)
        except ApiError as exc:
            raise CommandError(str(exc.detail)) from None
        self.stdout.write(f"تم: كلمة مرور {user.username} الجديدة جاهزة، والحساب مفتوح.")
