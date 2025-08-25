from django.apps import AppConfig


class FileindexAppConfig(AppConfig):
    name = "fileindex"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Signal indexedfile_added is available for apps to use
        # Import checks to register them
        from . import checks  # noqa: F401
