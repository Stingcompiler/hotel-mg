"""API freeze gate (spec §12): every screen's data hook from §10.4 exists in the OpenAPI schema.

Where the implemented path differs from the spec's shorthand the mapping says so; each such
difference is recorded in docs/decisions.md.
"""

import pytest
from drf_spectacular.generators import SchemaGenerator

P = "/api/v1/"

# Screen (design) → [(method, path in the schema)]
SCREENS = {
    "Login": [("post", "auth/pin"), ("post", "auth/password"), ("get", "auth/users"), ("get", "followups/tasks")],
    "Room board": [("get", "rooms/"), ("post", "rooms/{id}/set-status"), ("get", "followups/toasts")],
    "Reservations": [("get", "reservations/"), ("get", "rooms/")],
    "New reservation": [
        ("get", "guests/"),
        ("post", "guests/"),
        ("get", "reservations/availability"),
        ("post", "reservations/quote"),
        ("post", "reservations/"),
        ("post", "stays/check-in"),
    ],
    "Stay detail": [
        ("get", "stays/{id}"),
        ("post", "stays/{id}/extend"),
        ("post", "stays/{id}/extend/quote"),
        ("post", "stays/{id}/change-room"),
        ("post", "stays/{id}/checkout"),
        ("post", "stays/{id}/cancel"),
        ("get", "folios/{id}"),
        ("post", "folios/{id}/lines"),  # spec: stays/:id/add-line (decision 88)
        ("post", "folios/{id}/lines/{line_pk}/reverse"),
        ("post", "folios/{id}/payments"),  # spec: POST payments (decision 88)
        ("post", "payments/{id}/reverse"),
    ],
    "Follow-ups": [
        ("get", "followups/tasks"),
        ("get", "followups/board"),
        ("post", "followups/tasks/{id}/actions"),
    ],
    "Cash & shift": [
        ("get", "shifts/current"),
        ("post", "shifts/open"),
        ("post", "shifts/close"),
        ("get", "shifts/"),
        ("get", "shifts/{id}"),
    ],
    "Expenses": [
        ("get", "expenses/"),
        ("post", "expenses/"),
        ("post", "expenses/{id}/reverse"),
        ("post", "expenses/{id}/attachments"),
        ("get", "expenses/summary"),
    ],
    "Guests": [
        ("get", "guests/"),
        ("get", "guests/{id}"),
        ("patch", "guests/{id}"),
        ("get", "guests/{id}/history"),
        ("post", "guests/{id}/documents"),
        ("get", "guests/{id}/documents/{doc_pk}"),
    ],
    "Reports": [("get", "reports/"), ("get", "reports/{name}"), ("get", "reports/{name}/export")],
    "Settings": [
        ("get", "users/"),
        ("post", "users/"),
        ("patch", "users/{id}"),
        ("post", "users/{id}/reset-pin"),
        ("get", "room-types/"),
        ("patch", "room-types/{id}"),
        ("get", "rooms/"),
        ("patch", "rooms/{id}"),
        ("get", "followups/rules"),
        ("post", "followups/rules/preview"),
        ("get", "backup/settings"),
        ("patch", "backup/settings"),
        ("get", "system/status"),
        ("patch", "system/settings"),
        ("get", "audit/"),
        ("get", "audit/verify"),
    ],
    "Owner dashboard": [("get", "reports/owner-dashboard"), ("get", "system/status"), ("get", "owner/import/runs")],
    "Backup card": [
        ("post", "backup/run"),
        ("post", "backup/drive/sync"),
        ("get", "backup/drive/status"),
        ("get", "owner/import/candidates"),
        ("post", "owner/import/run"),
        ("post", "owner/import/drive"),
    ],
    "Print templates": [
        ("get", "folios/{id}/invoice"),
        ("get", "payments/{id}/receipt"),
        ("get", "expenses/{id}/receipt"),
        ("get", "shifts/{id}/statement"),
    ],
}


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


@pytest.mark.parametrize("screen", SCREENS)
def test_every_screen_hook_exists_in_the_schema(schema, screen):
    missing = [
        f"{method.upper()} {path}"
        for method, path in SCREENS[screen]
        if method not in schema["paths"].get(P + path, {})
    ]
    assert not missing, f"{screen}: {missing}"


def test_operation_ids_are_unique(schema):
    """Every operation has an operationId (the generated client names functions by it)."""
    ids = [op["operationId"] for item in schema["paths"].values() for op in item.values() if isinstance(op, dict)]
    assert len(ids) == len(set(ids))
