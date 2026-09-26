from django.core.exceptions import ImproperlyConfigured


def check_role(runtime, role: str) -> None:
    """Refuse to start when config.json names a different role than the settings module."""
    if runtime.role != role:
        raise ImproperlyConfigured(
            f"config.json role is {runtime.role!r} but settings module is for {role!r}. "
            "Start the server with the settings module matching config.json."
        )
