import os
import re
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "core.middleware.SplitSessionMiddleware",  # T6.6: admin/frontend sessions isolated
    "core.middleware.InstanceLocaleMiddleware",  # T7.1: instance language unless the user toggled
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "onboard.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.topbar_progress",
            ],
        },
    },
]

WSGI_APPLICATION = "onboard.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=os.environ["DATABASE_URL"], conn_max_age=600,
        conn_health_checks=True,  # RUN-004: drop stale persistent connections after a Postgres restart
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# T7.1: one instance per country (D18) — language and display tz come from that country's env file.
# Defaults are Malaysia's, so an env without them renders exactly as before.
LANGUAGE_CODE = os.environ.get("DJANGO_LANGUAGE_CODE", "en-us")
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Asia/Kuala_Lumpur")  # display only; storage stays UTC via USE_TZ
# The instance's own language plus English (the toggle). The toggle shows each language's own name
# (get_language_info name_local), so these labels are only Django's internal list.
_SUPPORTED = {"en": "English", "vi": "Vietnamese", "th": "Thai", "id": "Indonesian"}
_LANG = LANGUAGE_CODE.split("-")[0]
if _LANG not in _SUPPORTED:  # fail at startup, not as a half-English site
    raise ImproperlyConfigured(f"DJANGO_LANGUAGE_CODE={LANGUAGE_CODE!r}: supported are {sorted(_SUPPORTED)}")
LANGUAGES = [(c, _SUPPORTED[c]) for c in dict.fromkeys([_LANG, "en"])]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"  # relative: Django puts FORCE_SCRIPT_NAME (/vn) in front (T7.3)
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {"BACKEND": "core.storage.MinioMediaStorage"},  # MinIO/S3, private + presigned (P1/P2)
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --- MinIO / S3 media storage. P1/P2. ---
AWS_STORAGE_BUCKET_NAME = os.environ.get("MINIO_BUCKET", "onboard-media")
AWS_S3_ENDPOINT_URL = os.environ["MINIO_ENDPOINT"]  # http://minio:9000 — uploads (container-to-container)
# T7.3: per-country instances get a service account scoped to their own bucket (MINIO_ACCESS_KEY/
# MINIO_SECRET_KEY); Malaysia falls back to the root pair it has always used (SEC-004/D2).
AWS_ACCESS_KEY_ID = os.environ.get("MINIO_ACCESS_KEY") or os.environ["MINIO_ROOT_USER"]
AWS_SECRET_ACCESS_KEY = os.environ.get("MINIO_SECRET_KEY") or os.environ["MINIO_ROOT_PASSWORD"]
AWS_S3_ADDRESSING_STYLE = "path"  # MinIO is path-style
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_DEFAULT_ACL = None  # objects stay private; served only via presigned URLs
AWS_QUERYSTRING_EXPIRE = 900
AWS_S3_FILE_OVERWRITE = False

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Security wiring (behind nginx/Cloudflare TLS). P12. ---
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# SEC-035: https hardening has its own switch, so a plain-http LAN pilot can run with DEBUG off
# (DEBUG=True leaked URL patterns and tracebacks). Anything but "false" keeps it on: fail secure.
HTTPS = os.environ.get("DJANGO_HTTPS", "True").lower() != "false"
SESSION_COOKIE_SECURE = HTTPS
CSRF_COOKIE_SECURE = HTTPS
LANGUAGE_COOKIE_SECURE = HTTPS

# T7.3 (D18): every country shares one domain and is told apart by path — Malaysia at /, the
# others at /vn/, /th/, /id/ (nginx strips the prefix). Malaysia's cookies are Path=/ and so also
# reach /vn/; per-instance names keep each instance reading only its own session, CSRF and
# language cookies, and per-instance paths keep its cookies away from Malaysia. Unset = Malaysia,
# whose names and paths stay Django's defaults (existing sessions survive the upgrade).
URL_PREFIX = os.environ.get("DJANGO_URL_PREFIX", "").strip("/")
if URL_PREFIX:
    if not re.fullmatch(r"[a-z]{2}", URL_PREFIX):
        raise ImproperlyConfigured(f"DJANGO_URL_PREFIX={URL_PREFIX!r}: expected a 2-letter country code")
    FORCE_SCRIPT_NAME = f"/{URL_PREFIX}"
    SESSION_COOKIE_NAME = f"sessionid_{URL_PREFIX}"
    CSRF_COOKIE_NAME = f"csrftoken_{URL_PREFIX}"
    LANGUAGE_COOKIE_NAME = f"django_language_{URL_PREFIX}"
    SESSION_COOKIE_PATH = CSRF_COOKIE_PATH = LANGUAGE_COOKIE_PATH = f"/{URL_PREFIX}/"
LANGUAGE_COOKIE_HTTPONLY = True  # only the server reads it (set_language POST); no JS needs it
LANGUAGE_COOKIE_SAMESITE = "Lax"

# TLS terminates at nginx/Cloudflare; the proxy header above lets Django see it. SEC-003.
if HTTPS:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# COM-004: without this, core's INFO records (the PII-export audit line in admin.py)
# propagate to an unconfigured root logger and are dropped. Container stdout is the trail.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"core": {"handlers": ["console"], "level": "INFO"}},
}

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"  # T7.3: a URL name, so /vn/ lands on /vn/, not on Malaysia's /
LOGOUT_REDIRECT_URL = "login"
