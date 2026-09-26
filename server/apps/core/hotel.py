from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def current_hotel_id():
    """Default for ``BaseModel.hotel_id``: the hotel this PC belongs to (config.json)."""
    hotel_id = settings.RUNTIME.hotel_id
    if hotel_id is None:
        # Owner PC before its first import: it has no hotel of its own and never creates hotel rows.
        raise ImproperlyConfigured("hotel_id is not set in config.json; this PC cannot create hotel data.")
    return hotel_id
