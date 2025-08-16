from django.apps import AppConfig


class FileindexAppConfig(AppConfig):
    name = "fileindex"

    def ready(self):
        # Import tasks to register them with the @task decorator
        from fileindex import tasks  # noqa: F401
