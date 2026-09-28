"""Local development on Linux/macOS: reception role, debug on, data in server/.devdata."""

from .reception import *  # noqa: F403

DEBUG = True

# Swagger and the Django admin use a Django session; never in the installed app (review 2026-09-28, SEC-2).
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_AUTHENTICATION_CLASSES": [
        *REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"],  # noqa: F405
        "rest_framework.authentication.SessionAuthentication",
    ],
}
