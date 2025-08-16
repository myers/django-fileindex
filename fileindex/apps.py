from django.apps import AppConfig


class FileindexAppConfig(AppConfig):
    name = "fileindex"

    def ready(self):
        # Signal indexedfile_added is available for apps to use
        pass
