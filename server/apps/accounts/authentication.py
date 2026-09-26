from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication

from . import rules


class ExpiringTokenAuthentication(TokenAuthentication):
    """DRF token that expires 12 hours after login (spec §6.8). Header: ``Authorization: Token <key>``."""

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if rules.token_expired(token.created, timezone.now()):
            token.delete()
            raise exceptions.AuthenticationFailed(code="token_expired")
        return user, token
