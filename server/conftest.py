import pytest
from rest_framework.test import APIClient

PASSWORD = "correct-horse"
PIN = "123456"


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def make_user(db):
    from apps.accounts.models import User

    def make(username="ahmed.ali", role="reception", full_name="أحمد علي", **extra):
        return User.objects.create_user(username, full_name, role=role, password=PASSWORD, pin=PIN, **extra)

    return make


@pytest.fixture
def manager(make_user):
    return make_user("manager", role="manager", full_name="المدير")


@pytest.fixture
def reception(make_user):
    return make_user("ahmed.ali", role="reception", full_name="أحمد علي")


def _login(user):
    from apps.accounts import services

    client = APIClient()
    result = services.login_with_password(user.username, PASSWORD)
    client.credentials(HTTP_AUTHORIZATION=f"Token {result.token}")
    return client


@pytest.fixture
def manager_api(manager):
    return _login(manager)


@pytest.fixture
def reception_api(reception):
    return _login(reception)


@pytest.fixture
def confirm():
    """Attach a fresh X-Confirm-Token to an authenticated client."""

    def attach(client):
        res = client.post("/api/v1/auth/confirm", {"password": PASSWORD}, format="json")
        assert res.status_code == 200, res.json()
        client.credentials(
            HTTP_AUTHORIZATION=client._credentials["HTTP_AUTHORIZATION"],
            HTTP_X_CONFIRM_TOKEN=res.json()["confirm_token"],
        )
        return client

    return attach


@pytest.fixture
def seeded(db):
    """The demo hotel (room board artboards): 18/30 occupied, debts on 203 and 305."""
    from django.core.management import call_command

    call_command("seed_demo", "--allow-non-debug")


@pytest.fixture
def api_as_manager(seeded):
    from apps.accounts.services import login_with_password
    from apps.core.seed import demo_data

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {login_with_password('manager', demo_data.DEMO_PASSWORD).token}")
    return client
