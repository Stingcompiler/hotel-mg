from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def current_hotel_id():
    """Default for ``BaseModel.hotel_id``: the hotel this PC belongs to (config.json)."""
    hotel_id = settings.RUNTIME.hotel_id
    if hotel_id is None:
        # Owner PC before its first import: it has no hotel of its own and never creates hotel rows — unless the
        # database already holds a hotel (a reception database under an owner config.json): then that hotel is
        # the only sensible answer, and login events, audit rows etc. keep working instead of failing with a 500.
        hotel_id = _hotel_in_database()
        if hotel_id is None:
            raise ImproperlyConfigured("hotel_id is not set in config.json; this PC cannot create hotel data.")
    return hotel_id


def _hotel_in_database():
    from apps.accounts.models import User

    return User.objects.order_by("created_at").values_list("hotel_id", flat=True).first()
