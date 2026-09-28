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
    "apps.core.middleware.OwnerReadOnlyMiddleware",
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
# Built SPA (web/dist copied by build/build_spa.py; bundled next to the service at release time).
SPA_ROOT = BASE_DIR / "static_spa"

# --- API --------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.ExpiringTokenAuthentication",
        # Session auth (Swagger, the Django admin) is added in config/settings/dev.py only (SEC-2).
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.Pagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "apps.core.errors.api_exception_handler",
    # `?format=` is ours (report exports: xlsx|csv), not DRF's renderer switch.
    "URL_FORMAT_OVERRIDE": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Sky Towers API",
    "DESCRIPTION": "Local API of the Sky Towers hotel management system.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "apps.core.schema.response_fields_required",
    ],
    "ENUM_NAME_OVERRIDES": {
        "UserRoleEnum": "apps.accounts.models.Role",
        "DeviceRoleEnum": ["reception", "owner"],
        "RoomStatusEnum": "apps.rooms.models.RoomStatus",
        "RoomDisplayStatusEnum": "apps.stays.serializers.DISPLAY_STATUS",
        "DurationKindEnum": "apps.stays.models.DurationKind",
        "BookingDurationKindEnum": "apps.stays.serializers.BOOKING_KINDS",
        "AfterRoomStatusEnum": "apps.stays.serializers.AFTER_ROOM_STATUS",
        "PaymentMethodEnum": "apps.cash.models.PaymentMethod",
        "AuditCategoryEnum": "apps.audit.rules.CATEGORY_KEYS",
        "ExpenseCategoryEnum": "apps.cash.models.ExpenseCategory",
    },
}

APP_VERSION = "1.1.3"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
