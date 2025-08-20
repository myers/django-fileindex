"""
Django settings for running tests with PostgreSQL
"""

from .settings import *  # noqa: F403

# Override database settings for PostgreSQL
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "fileindex_test",
        "USER": "fileindex",
        "PASSWORD": "fileindex",
        "HOST": "localhost",
        "PORT": "8732",
        "TEST": {
            "NAME": "test_fileindex",
        },
    }
}

# Use standard apps for PostgreSQL tests
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "fileindex.apps.FileindexAppConfig",
]
