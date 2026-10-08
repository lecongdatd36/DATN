"""Cấu hình nền tảng QLNH; các app nghiệp vụ được thêm theo từng giai đoạn."""

import os
from pathlib import Path
import dj_database_url # deploy
from django.contrib.messages import constants as message_constants
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# File .env của dự án được ưu tiên, tránh trùng biến DEBUG của công cụ terminal.
load_dotenv(BASE_DIR / ".env", override=True, encoding="utf-8")


def required_env(name):
    value = os.environ.get(name)
    if not value or not value.strip():
        raise ImproperlyConfigured(f"Thiếu {name}. Hãy cấu hình trong file .env.")
    return value


def positive_int_env(name, default):
    raw_value = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} phải là số nguyên dương.") from exc
    if value <= 0:
        raise ImproperlyConfigured(f"{name} phải là số nguyên dương.")
    return value


SECRET_KEY = required_env("SECRET_KEY")
debug_value = os.environ.get("DEBUG", "False").strip().lower()
if debug_value not in {"true", "false", "1", "0"}:
    raise ImproperlyConfigured("DEBUG phải là True, False, 1 hoặc 0.")
DEBUG = debug_value in {"true", "1"}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
    if host.strip()
]
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
# Gunicorn/Render terminate HTTPS before forwarding the request to Django.  Without
# this header Django sees an HTTP request and rejects same-origin QR POSTs coming
# from an HTTPS phone browser during CSRF origin validation.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
if RENDER_EXTERNAL_URL and RENDER_EXTERNAL_URL not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(RENDER_EXTERNAL_URL)
# Optional canonical address embedded in printed table QR codes.  It is useful
# in local/LAN operation where the staff browser itself may use localhost.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/") or RENDER_EXTERNAL_URL

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts.apps.AccountsConfig",
    "apps.employees.apps.EmployeesConfig",
    "apps.customers.apps.CustomersConfig",
    "apps.seating.apps.SeatingConfig",
    "apps.bookings.apps.BookingsConfig",
    "apps.menu.apps.MenuConfig",
    "apps.orders.apps.OrdersConfig",
    "apps.inventory.apps.InventoryConfig",
    "apps.reports.apps.ReportsConfig",
    "cloudinary",
    "cloudinary_storage",
    "apps.customer_portal.apps.CustomerPortalConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware", # deploy
    "django.middleware.gzip.GZipMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "core.middleware.RequestTimingMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "qlnh-runtime-cache",
    }
}
# Giữ bản bền vững trong DB nhưng đọc phiên lặp lại từ RAM để thao tác webapp nhanh hơn.
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
MESSAGE_STORAGE = "django.contrib.messages.storage.fallback.FallbackStorage"
MESSAGE_TAGS = {message_constants.ERROR: "danger"}

# Ngưỡng vận hành có thể chỉnh trực tiếp bằng biến môi trường trên Render.
SLOW_REQUEST_THRESHOLD_MS = positive_int_env("SLOW_REQUEST_THRESHOLD_MS", 750)
KITCHEN_PENDING_SLA_MINUTES = positive_int_env("KITCHEN_PENDING_SLA_MINUTES", 8)
KITCHEN_COOKING_SLA_MINUTES = positive_int_env("KITCHEN_COOKING_SLA_MINUTES", 15)
KITCHEN_READY_SLA_MINUTES = positive_int_env("KITCHEN_READY_SLA_MINUTES", 5)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "qlnh.performance": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        }
    },
}

ROOT_URLCONF = "QLNH.urls"
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
                "core.context_processors.access_policy",
            ],
        },
    },
]
WSGI_APPLICATION = "QLNH.wsgi.application"
ASGI_APPLICATION = "QLNH.asgi.application"

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": required_env("DB_NAME"),
            "USER": required_env("DB_USER"),
            "PASSWORD": required_env("DB_PASSWORD"),
            "HOST": required_env("DB_HOST"),
            "PORT": required_env("DB_PORT"),
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {"connect_timeout": 5},
        }
    }

# Custom User được khai báo trước migration đầu tiên của dự án.
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:workspace"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "vi"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# ẢNH TRÊN CLOUDINARY
STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        # Development must serve the current source file instead of a possibly
        # stale collectstatic manifest. Production keeps immutable hashed assets.
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

# Cổng thanh toán VNPAY. Để trống hai mã định danh khi chỉ dùng tiền mặt/chuyển khoản tại quầy.
VNPAY_PAYMENT_URL = os.environ.get(
    "VNPAY_PAYMENT_URL", "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
).strip()
VNPAY_TMN_CODE = os.environ.get("VNPAY_TMN_CODE", "").strip()
VNPAY_HASH_SECRET = os.environ.get("VNPAY_HASH_SECRET", "").strip()
VNPAY_RETURN_URL = os.environ.get("VNPAY_RETURN_URL", "").strip()

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
