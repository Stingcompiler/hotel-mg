import json
import uuid

import pytest
from django.core.exceptions import ImproperlyConfigured

from config import runtime
from config.settings._role import check_role


def test_defaults_without_config_file(tmp_path):
    cfg = runtime.load(home=tmp_path)
    assert cfg.role == "reception"
    assert cfg.hotel_id == runtime.DEV_HOTEL_ID
    assert cfg.db_path == tmp_path / "data" / "hotel.db"
    assert cfg.backups_dir == tmp_path / "backups"


def test_secret_key_is_generated_once(tmp_path):
    first = runtime.load(home=tmp_path).secret_key
    assert len(first) >= 50
    assert runtime.load(home=tmp_path).secret_key == first


def test_owner_config_with_empty_hotel_id(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"role": "owner", "hotel_id": ""}), encoding="utf-8")
    cfg = runtime.load(home=tmp_path)
    assert cfg.role == "owner"
    assert cfg.hotel_id is None


def test_reception_config(tmp_path):
    hotel = uuid.uuid4()
    (tmp_path / "config.json").write_text(
        json.dumps({"role": "reception", "hotel_id": str(hotel), "secret_key": "k", "second_backup_dir": "E:/bk"}),
        encoding="utf-8",
    )
    cfg = runtime.load(home=tmp_path)
    assert cfg.hotel_id == hotel
    assert cfg.secret_key == "k"
    assert cfg.second_backup_dir is not None


def test_invalid_role_is_rejected(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"role": "admin"}), encoding="utf-8")
    with pytest.raises(ValueError):
        runtime.load(home=tmp_path)


def test_settings_module_must_match_config_role(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"role": "owner", "hotel_id": ""}), encoding="utf-8")
    with pytest.raises(ImproperlyConfigured):
        check_role(runtime.load(home=tmp_path), "reception")
