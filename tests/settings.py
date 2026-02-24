"""
Django settings for running tests
"""

import os
import tempfile

SECRET_KEY = "test-secret-key-for-django-fileindex"

DEBUG = True

ALLOWED_HOSTS = []

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "fileindex.apps.FileindexAppConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "tests.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "fileindex_test",
        "USER": "fileindex",
        "PASSWORD": "fileindex",
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "8732"),
        "TEST": {
            "NAME": "test_fileindex",
        },
    }
}

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"

# Media files
MEDIA_ROOT = tempfile.mkdtemp()
MEDIA_URL = "/media/"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Time zone
USE_TZ = True
TIME_ZONE = "UTC"

# Testing
TEST_RUNNER = "django.test.runner.DiscoverRunner"

# Sendfile settings
SENDFILE_ROOT = MEDIA_ROOT
SENDFILE_URL = MEDIA_URL
SENDFILE = False  # Use Django's FileResponse in tests
SENDFILE_BACKEND = "django_sendfile.backends.development"
