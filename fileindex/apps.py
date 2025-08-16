from django.apps import AppConfig


class FileindexAppConfig(AppConfig):
    name = "fileindex"

    def ready(self):
        # Tasks registered with @task are defined in this import
        from . import tasks  # noqa
