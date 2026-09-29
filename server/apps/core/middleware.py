from django.conf import settings

from .clock import observe_clock
from .errors import error_json_response

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Still reachable while the clock is blocked, so a manager can sign in and approve.
CLOCK_EXEMPT_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/system/clock/approve",
    "/admin/login/",  # development only (config/urls.py)
)


class ClockGuardMiddleware:
    """Refuse every write with HTTP 423 ``clock_rollback`` while the device clock is blocked."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in WRITE_METHODS and not request.path.startswith(CLOCK_EXEMPT_PREFIXES):
            if observe_clock():
                return error_json_response("clock_rollback", 423)
        return self.get_response(request)


# The only writes an owner PC accepts (spec §2): signing in, and its own import / Drive / backup endpoints.
# … and approving its clock after a rollback, or imports stay refused forever (review 2026-09-29, C-14).
OWNER_ALLOWED_PREFIXES = ("/api/v1/auth/", "/api/v1/owner/", "/api/v1/system/clock/approve")


class OwnerReadOnlyMiddleware:
    """On the owner PC every mutating API request is refused with 403 ``owner_read_only`` (spec §2)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            settings.SKYTOWERS_ROLE == "owner"
            and request.method in WRITE_METHODS
            and not request.path.startswith(OWNER_ALLOWED_PREFIXES)
        ):
            return error_json_response("owner_read_only", 403)
        return self.get_response(request)
