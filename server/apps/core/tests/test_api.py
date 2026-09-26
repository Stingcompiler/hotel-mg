from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.clock import observe_clock
from apps.core.errors import ApiError, api_exception_handler
from apps.core.models import SCHEMA_VERSION

pytestmark = pytest.mark.django_db


def test_system_status_is_public(api):
    res = api.get("/api/v1/system/status")
    assert res.status_code == 200
    assert res.json() == {
        "role": "reception",
        "hotel_id": str(settings.RUNTIME.hotel_id),
        "last_backup": None,
        "data_as_of": None,
        "clock_blocked": False,
        "version": settings.APP_VERSION,
        "schema_version": SCHEMA_VERSION,
    }


def test_openapi_schema_is_served(api):
    res = api.get("/api/v1/schema", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert res.status_code == 200
    schema = res.json()
    assert schema["info"]["title"] == "Sky Towers API"
    assert "/api/v1/system/status" in schema["paths"]


def test_errors_use_code_and_arabic_detail(api):
    res = api.post("/api/v1/system/status")
    assert res.status_code == 405
    assert res.json() == {"code": "method_not_allowed", "detail": "هذا الإجراء غير مسموح."}


def _block_clock():
    now = timezone.now()
    observe_clock(now)
    observe_clock(now - timedelta(hours=1))


def test_clock_guard_refuses_writes_with_423(api):
    _block_clock()
    res = api.post("/api/v1/system/status")
    assert res.status_code == 423
    assert res.json()["code"] == "clock_rollback"
    # Reads keep working, and status reports the block.
    assert api.get("/api/v1/system/status").json()["clock_blocked"] is True


def test_clock_guard_lets_approval_path_through(api):
    _block_clock()
    assert api.post("/api/v1/system/clock/approve").status_code == 404  # endpoint arrives in B3


def test_handler_shapes_api_error():
    res = api_exception_handler(ApiError("no_open_shift", 409), {})
    assert res.status_code == 409
    assert res.data == {"code": "no_open_shift", "detail": "لا توجد وردية مفتوحة على هذا الجهاز."}


def test_handler_keeps_field_errors_for_validation():
    res = api_exception_handler(ValidationError({"amount": ["bad"]}), {})
    assert res.status_code == 400
    assert res.data["code"] == "validation_error"
    assert res.data["errors"] == {"amount": ["bad"]}


def test_handler_maps_drf_exceptions():
    res = api_exception_handler(NotFound(), {})
    assert res.data == {"code": "not_found", "detail": "العنصر غير موجود."}
