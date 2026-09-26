"""Settings shared by both roles. Role modules only set ``SKYTOWERS_ROLE``-specific values."""

from pathlib import Path

from config import runtime

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SKYTOWERS_ROLE: str = "reception"  # overridden by config.settings.<role>
RUNTIME = runtime.load(role_override=None)

SECRET_KEY = RUNTIME.secret_key
DEBUG = False
# The service binds to 127.0.0.1:8471 only (spec §2).
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.rooms",
    "apps.guests",
    "apps.stays",
    "apps.billing",
    "apps.cash",
    "apps.followups",
    "apps.backup",
    "apps.reports",
    "apps.audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.ClockGuardMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database (spec §3) -----------------------------------------------------
# Only standard ORM features: switching ENGINE/NAME to PostgreSQL must be the
# only change needed. The PRAGMAs below are SQLite connection settings, not SQL
# used by the application.
SQLITE_PRAGMAS = "PRAGMA journal_mode=WAL;PRAGMA synchronous=FULL;PRAGMA foreign_keys=ON;PRAGMA busy_timeout=20000;"

RUNTIME.data_dir.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": RUNTIME.db_path,
        "OPTIONS": {
            "init_command": SQLITE_PRAGMAS,
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

# --- Locale -----------------------------------------------------------------
LANGUAGE_CODE = "ar"
TIME_ZONE = "Africa/Khartoum"  # hotel timezone: stay dates are local dates
USE_I18N = True
USE_TZ = True  # timestamps stored in UTC

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "static_collected"

# --- API --------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.ExpiringTokenAuthentication",
        # Session auth serves the browsable API / Swagger for staff during the backend phases.
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "apps.core.errors.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Sky Towers API",
    "DESCRIPTION": "Local API of the Sky Towers hotel management system.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "UserRoleEnum": "apps.accounts.models.Role",
        "DeviceRoleEnum": ["reception", "owner"],
        "RoomStatusEnum": "apps.rooms.models.RoomStatus",
        "DurationKindEnum": "apps.stays.models.DurationKind",
        "BookingDurationKindEnum": "apps.stays.serializers.BOOKING_KINDS",
        "AfterRoomStatusEnum": "apps.stays.serializers.AFTER_ROOM_STATUS",
        "PaymentMethodEnum": "apps.cash.models.PaymentMethod",
    },
}

APP_VERSION = "0.1.0"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
