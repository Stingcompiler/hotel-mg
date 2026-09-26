from django.db import transaction

from .errors import VersionConflict


def get_for_update(queryset, pk, expected_version: int | None):
    """Load a row for modification inside a service transaction.

    Raises ``VersionConflict`` (HTTP 409) when the client edited a stale copy.
    ``select_for_update`` is a no-op on SQLite (IMMEDIATE transactions already
    serialize writers) and row-locks on PostgreSQL.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("get_for_update() must be called inside transaction.atomic()")
    obj = queryset.select_for_update().get(pk=pk)
    if expected_version is not None and obj.version != expected_version:
        raise VersionConflict()
    return obj
