import dataclasses

import pytest
from django.conf import settings

from apps.accounts.models import User
from apps.backup import export, keys
from apps.cash import services as cash
from apps.rooms.models import Room, RoomType


@pytest.fixture
def owner_identity(tmp_path):
    path = tmp_path / "owner.key"
    public = keys.generate(path)
    return keys.load(path), public


@pytest.fixture
def hotel(owner_identity, tmp_path, monkeypatch):
    """Reception with rooms, a manager, an open shift and backups encrypted to the owner key."""
    monkeypatch.setattr(settings, "RUNTIME", dataclasses.replace(settings.RUNTIME, home=tmp_path / "reception"))
    settings.RUNTIME.data_dir.mkdir(parents=True, exist_ok=True)
    manager = User.objects.create_user("manager", "المدير", role="manager", password="pw-123456", pin="1234")
    double = RoomType.objects.create(
        name="مزدوجة", nightly_price=1_500_000, weekly_price=9_500_000, monthly_price=30_000_000
    )
    for n in ("201", "202", "203", "204"):
        Room.objects.create(number=n, floor=2, room_type=double)
    cfg = export.backup_settings()
    cfg.owner_recipient = owner_identity[1]
    cfg.save()
    cash.open_shift(manager, opening=5_000_000)
    return manager
