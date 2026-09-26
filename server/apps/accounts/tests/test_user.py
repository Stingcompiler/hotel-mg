import pytest
from django.core.exceptions import ValidationError

from apps.accounts import rules
from apps.accounts.models import Role, User


@pytest.mark.parametrize("pin", ["1234", "12345", "123456"])
def test_valid_pins(pin):
    assert rules.is_valid_pin(pin)


@pytest.mark.parametrize("pin", ["123", "1234567", "12a4", "١٢٣٤", "", None, 1234])
def test_invalid_pins(pin):
    assert not rules.is_valid_pin(pin)


@pytest.mark.django_db
def test_create_user_hashes_pin_and_password():
    user = User.objects.create_user("ahmed.ali", "أحمد علي", role=Role.RECEPTION, password="secret-pass", pin="4321")
    assert user.pin_hash and "4321" not in user.pin_hash
    assert user.check_pin("4321")
    assert not user.check_pin("1111")
    assert user.check_password("secret-pass")
    assert user.version == 1


@pytest.mark.django_db
def test_user_without_password_or_pin_cannot_log_in():
    user = User.objects.create_user("x", "س", role=Role.RECEPTION)
    assert not user.has_usable_password()
    assert not user.check_pin("1234")


@pytest.mark.django_db
def test_invalid_pin_is_refused():
    with pytest.raises(ValidationError):
        User.objects.create_user("x", "س", pin="12")


@pytest.mark.django_db
def test_invalid_role_is_refused():
    with pytest.raises(ValidationError):
        User.objects.create_user("x", "س", role="admin")
