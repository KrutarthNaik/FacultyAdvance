from pathlib import Path
import os
import re
from decouple import config, Csv
from django.core.exceptions import ImproperlyConfigured
from .database import build_database_config
from .deployment import build_deployment_security, validate_vercel_runtime
from .email import build_email_config
from .security import DEVELOPMENT_SECRET_KEY, validate_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent
IS_VERCEL = os.environ.get("VERCEL") == "1"
DEBUG = config("DEBUG", default=not IS_VERCEL, cast=bool)
if IS_VERCEL and DEBUG:
    raise ImproperlyConfigured("DEBUG=True is not supported on Vercel; deploy with DEBUG=False.")
SECRET_KEY = validate_secret_key(
    config("SECRET_KEY", default=DEVELOPMENT_SECRET_KEY).strip(),
    debug=DEBUG,
)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="", cast=Csv())
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
if IS_VERCEL and os.environ.get("VERCEL_URL"):
    vercel_host = os.environ["VERCEL_URL"].strip()
    if vercel_host and vercel_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(vercel_host)

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "corsheaders", "rest_framework", "rest_framework_simplejwt", "core",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug", "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

DATABASE_URL = config("DATABASE_URL", default="").strip()
DATABASE_CONN_MAX_AGE = config("DATABASE_CONN_MAX_AGE", default=0, cast=int)
DATABASES = {
    "default": build_database_config(
        DATABASE_URL,
        BASE_DIR / "db.sqlite3",
        debug=DEBUG,
        conn_max_age=DATABASE_CONN_MAX_AGE,
    )
}
REDIS_URL = config("REDIS_URL", default="").strip()
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }
else:
    if IS_VERCEL and not DEBUG:
        raise ImproperlyConfigured(
            "REDIS_URL is required on Vercel to share API rate-limit state across function instances."
        )
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "facultyadvance-local",
        }
    }
TRUST_PROXY_SSL_HEADER = config("TRUST_PROXY_SSL_HEADER", default=False, cast=bool)
if IS_VERCEL:
    validate_vercel_runtime(
        debug=DEBUG,
        trust_proxy=TRUST_PROXY_SSL_HEADER,
        redis_url=REDIS_URL,
    )
EMAIL_SETTINGS = build_email_config(
    debug=DEBUG,
    backend=config("EMAIL_BACKEND", default="").strip(),
    host=config("EMAIL_HOST", default=""),
    port=config("EMAIL_PORT", default=25, cast=int),
    username=config("EMAIL_HOST_USER", default=""),
    password=config("EMAIL_HOST_PASSWORD", default=""),
    use_tls=config("EMAIL_USE_TLS", default=False, cast=bool),
    use_ssl=config("EMAIL_USE_SSL", default=False, cast=bool),
    default_from_email=config("DEFAULT_FROM_EMAIL", default="").strip(),
)
globals().update(EMAIL_SETTINGS)
EMAIL_ALERTS_ENABLED = config("EMAIL_ALERTS_ENABLED", default=True, cast=bool)
SQLITE_MIGRATION_SOURCE = config("SQLITE_MIGRATION_SOURCE", default="").strip()
if SQLITE_MIGRATION_SOURCE:
    source_path = Path(SQLITE_MIGRATION_SOURCE).expanduser()
    if not source_path.is_file():
        raise ImproperlyConfigured(
            "SQLITE_MIGRATION_SOURCE must refer to an existing SQLite database file."
        )
    DATABASES["migration_source"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": source_path.resolve(),
    }
AUTH_USER_MODEL = "core.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "core.validators.StrongPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = config(
    "FRONTEND_ORIGINS",
    default=config("FRONTEND_ORIGIN", default="http://localhost:5173"),
    cast=Csv(),
)
if DEBUG:
    local_frontend_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    CORS_ALLOWED_ORIGINS = list(dict.fromkeys(
        [*CORS_ALLOWED_ORIGINS, *local_frontend_origins]
    ))
globals().update(build_deployment_security(
    debug=DEBUG,
    allowed_hosts=ALLOWED_HOSTS,
    cors_origins=CORS_ALLOWED_ORIGINS,
    trust_proxy=TRUST_PROXY_SSL_HEADER,
))
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="",
    cast=Csv(),
)
if not DEBUG and not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured(
        "Set CSRF_TRUSTED_ORIGINS to the trusted HTTPS application origins in production."
    )
if DEBUG and not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
if not DEBUG and any(not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("Production CSRF_TRUSTED_ORIGINS must use HTTPS.")

PUBLIC_REGISTRATION_ENABLED = config(
    "PUBLIC_REGISTRATION_ENABLED", default=DEBUG, cast=bool
)
PASSWORD_RESET_FRONTEND_URL = config(
    "PASSWORD_RESET_FRONTEND_URL", default="http://localhost:5173/reset-password"
)
EMAIL_VERIFICATION_FRONTEND_URL = config(
    "EMAIL_VERIFICATION_FRONTEND_URL", default="http://localhost:5173/verify-email"
)
if not DEBUG and (
    not PASSWORD_RESET_FRONTEND_URL.startswith("https://")
    or not EMAIL_VERIFICATION_FRONTEND_URL.startswith("https://")
):
    raise ImproperlyConfigured("Production password reset and email verification URLs must use HTTPS.")
ACCOUNT_TOKEN_MAX_AGE = config("ACCOUNT_TOKEN_MAX_AGE", default=60 * 60 * 24, cast=int)
if ACCOUNT_TOKEN_MAX_AGE < 60:
    raise ImproperlyConfigured("ACCOUNT_TOKEN_MAX_AGE must be at least 60 seconds.")
GOOGLE_SSO_CLIENT_ID = config("GOOGLE_SSO_CLIENT_ID", default="").strip()
GOOGLE_SSO_CLIENT_SECRET = config("GOOGLE_SSO_CLIENT_SECRET", default="").strip()
GOOGLE_SSO_WORKSPACE_DOMAIN = config("GOOGLE_SSO_WORKSPACE_DOMAIN", default="").strip().lower()
GOOGLE_SSO_REDIRECT_URI = config("GOOGLE_SSO_REDIRECT_URI", default="").strip()
GOOGLE_SSO_FRONTEND_CALLBACK = config(
    "GOOGLE_SSO_FRONTEND_CALLBACK", default="http://localhost:5173/sso/callback"
).strip()
if GOOGLE_SSO_WORKSPACE_DOMAIN and not re.fullmatch(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
    GOOGLE_SSO_WORKSPACE_DOMAIN,
):
    raise ImproperlyConfigured("GOOGLE_SSO_WORKSPACE_DOMAIN must be a bare DNS domain name.")
if not DEBUG and GOOGLE_SSO_CLIENT_ID and (
    not GOOGLE_SSO_CLIENT_SECRET
    or not GOOGLE_SSO_WORKSPACE_DOMAIN
    or not GOOGLE_SSO_REDIRECT_URI.startswith("https://")
    or not GOOGLE_SSO_FRONTEND_CALLBACK.startswith("https://")
):
    raise ImproperlyConfigured(
        "Configured Google SSO requires its client secret, Workspace domain, and HTTPS callback URLs."
    )
NOTIFICATION_RETENTION_DAYS = config(
    "NOTIFICATION_RETENTION_DAYS", default=0, cast=int
)
if NOTIFICATION_RETENTION_DAYS < 0:
    raise ImproperlyConfigured("NOTIFICATION_RETENTION_DAYS cannot be negative.")

USE_S3_STORAGE = config("USE_S3_STORAGE", default=False, cast=bool)
if IS_VERCEL and not DEBUG and not USE_S3_STORAGE:
    raise ImproperlyConfigured(
        "USE_S3_STORAGE=True is required on Vercel because function filesystems are ephemeral."
    )
if USE_S3_STORAGE:
    INSTALLED_APPS.append("storages")
    AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")
    AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="")
    AWS_S3_ENDPOINT_URL = config("AWS_S3_ENDPOINT_URL", default="") or None
    AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_OBJECT_PARAMETERS = {"ServerSideEncryption": "AES256"}
    if not AWS_STORAGE_BUCKET_NAME or not AWS_S3_REGION_NAME:
        raise ImproperlyConfigured(
            "AWS_STORAGE_BUCKET_NAME and AWS_S3_REGION_NAME are required when S3 storage is enabled."
        )
    if bool(AWS_ACCESS_KEY_ID) != bool(AWS_SECRET_ACCESS_KEY):
        raise ImproperlyConfigured(
            "Set both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or leave both empty to use workload identity."
        )
    if not DEBUG and AWS_S3_ENDPOINT_URL and not AWS_S3_ENDPOINT_URL.startswith("https://"):
        raise ImproperlyConfigured("Production S3-compatible storage endpoints must use HTTPS.")
    AWS_QUERYSTRING_AUTH = True
    AWS_S3_CUSTOM_DOMAIN = None
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

MALWARE_SCANNER = config("MALWARE_SCANNER", default="disabled").strip().lower()
if MALWARE_SCANNER and MALWARE_SCANNER not in {"disabled", "clamd", "clamscan", "clamav"}:
    raise ImproperlyConfigured("MALWARE_SCANNER must be one of: disabled, clamd, clamscan, clamav.")
CLAMD_HOST = config("CLAMD_HOST", default="127.0.0.1").strip()
CLAMD_PORT = config("CLAMD_PORT", default=3310, cast=int)
CLAMD_TIMEOUT = config("CLAMD_TIMEOUT", default=5, cast=int)
if MALWARE_SCANNER in {"clamd", "clamscan", "clamav"} and (not CLAMD_HOST or CLAMD_PORT < 1 or CLAMD_TIMEOUT < 1):
    raise ImproperlyConfigured("CLAMD_HOST, CLAMD_PORT and CLAMD_TIMEOUT must be valid when a malware scanner is enabled.")

EVIDENCE_UPLOAD_MAX_BYTES = config(
    "EVIDENCE_UPLOAD_MAX_BYTES",
    default=(
        4 * 1024 * 1024
        if IS_VERCEL
        else 10 * 1024 * 1024
    ),
    cast=int,
)
if EVIDENCE_UPLOAD_MAX_BYTES < 1:
    raise ImproperlyConfigured("EVIDENCE_UPLOAD_MAX_BYTES must be positive.")
if IS_VERCEL and EVIDENCE_UPLOAD_MAX_BYTES > 4 * 1024 * 1024:
    raise ImproperlyConfigured(
        "EVIDENCE_UPLOAD_MAX_BYTES cannot exceed 4 MiB on Vercel Functions."
    )

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("API_ANON_RATE", default="60/hour"),
        "user": config("API_USER_RATE", default="1000/hour"),
        "auth": config("AUTH_RATE", default="5/minute"),
        "registration": config("REGISTRATION_RATE", default="3/hour"),
        "email": config("EMAIL_ACTION_RATE", default="3/hour"),
    },
}
from datetime import timedelta
SIMPLE_JWT = {"ACCESS_TOKEN_LIFETIME": timedelta(hours=8), "AUTH_HEADER_TYPES": ("Bearer",)}
if not DEBUG:
    SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"] = timedelta(minutes=15)
    SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"] = timedelta(days=1)
    SIMPLE_JWT["ROTATE_REFRESH_TOKENS"] = True
    SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"] = True
    INSTALLED_APPS.append("rest_framework_simplejwt.token_blacklist")
    MIDDLEWARE.insert(1, "django.middleware.security.SecurityMiddleware")
    MIDDLEWARE = list(dict.fromkeys(MIDDLEWARE))

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
