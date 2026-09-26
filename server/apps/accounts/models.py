"""User model (spec §5). PIN/password login, lockout and confirm tokens arrive in phase B1.

Defined in B0 because Django needs a custom user model before the first
migration and ``BaseModel.created_by`` points here.
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel

from . import rules


class Role(models.TextChoices):
    OWNER = "owner", "المالك"
    MANAGER = "manager", "مدير"
    RECEPTION = "reception", "استقبال"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, username, full_name, role=Role.RECEPTION, password=None, pin=None, **extra):
        user = self.model(username=username, full_name=full_name, role=role, **extra)
        user.set_password(password)  # None -> unusable password
        if pin is not None:
            user.set_pin(pin)
        user.full_clean(exclude=["password", "hotel_id"])
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password, full_name="المدير", **extra):
        extra.setdefault("role", Role.MANAGER)
        return self.create_user(username, full_name, password=password, is_staff=True, is_superuser=True, **extra)


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    # AbstractBaseUser.password holds the password hash (spec: password_hash).
    username = models.CharField(max_length=64, unique=True)
    full_name = models.CharField(max_length=120)
    role = models.CharField(max_length=16, choices=Role.choices)
    pin_hash = models.CharField(max_length=128, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="May open the read-only Django admin.")

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.full_name

    def set_pin(self, pin: str) -> None:
        if not rules.is_valid_pin(pin):
            raise ValidationError("رمز الدخول يجب أن يكون من 4 إلى 6 أرقام.", code="invalid_pin")
        self.pin_hash = make_password(pin)

    def check_pin(self, pin: str) -> bool:
        return bool(self.pin_hash) and rules.is_valid_pin(pin) and check_password(pin, self.pin_hash)
