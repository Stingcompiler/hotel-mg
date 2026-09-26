"""pytest settings: reception role with a throwaway SKYTOWERS_HOME."""

import tempfile
from pathlib import Path

from config import runtime

from .reception import *  # noqa: F403
from .reception import DATABASES

RUNTIME = runtime.load(home=Path(tempfile.mkdtemp(prefix="skytowers-test-")), role_override="reception")
RUNTIME.data_dir.mkdir(parents=True, exist_ok=True)
DATABASES["default"]["NAME"] = RUNTIME.db_path

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests only

INSTALLED_APPS = [*INSTALLED_APPS, "tests.testapp"]  # noqa: F405
