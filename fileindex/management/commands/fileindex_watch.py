import logging
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from watchdog.events import FileSystemEventHandler, LoggingEventHandler
from watchdog.observers.polling import PollingObserver

from fileindex.models import IndexedFile
from fileindex.services.file_validation import should_import


class WatchEventHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.callback = callback

    def on_close(self, event):
        if event.is_directory:
            return
        self.callback(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            return
        self.callback(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        self.callback(event.src_path)


class Command(BaseCommand):
    help = "Move and import all supported files from a set of paths. Watches for new files that are added."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+")

    def setup_logger(self, options):
        verbosity = int(options["verbosity"])
        root_logger = logging.getLogger("")
        if verbosity > 1:
            root_logger.setLevel(logging.DEBUG)

    def handle(self, *args, **options):
        assert os.path.exists(settings.MEDIA_ROOT), f"MEDIA_ROOT does not exists: {settings.MEDIA_ROOT!r}"

        self.setup_logger(options)
        observer = self.setup_watcher(*args, **options)
        for path in options["paths"]:
            self.import_dir(path)
        self.wait_for_observer(observer)

    def setup_watcher(self, *args, **options):
        event_handler = WatchEventHandler(self.import_file)
        event_handler2 = LoggingEventHandler()
        observer = PollingObserver()
        for path in options["paths"]:
            print(path)
            observer.schedule(event_handler, path, recursive=True)
            observer.schedule(event_handler2, path, recursive=True)
        observer.start()
        return observer

    def wait_for_observer(self, observer):
        try:
            while observer.is_alive():
                observer.join(1)
        finally:
            observer.stop()
            observer.join()

    def import_file(self, filepath):
        if not should_import(filepath):
            print(f"not importing {filepath!r}")
            return False
        print(f"importing {filepath!r}...", end="", flush=True)
        try:
            indexed_file, created = IndexedFile.objects.get_or_create_from_file(filepath)
        except Exception as ee:
            print(f"Error while importing: {ee!r}")
            return False
        print("done", flush=True)
        assert os.path.exists(indexed_file.file.path)
        os.unlink(filepath)
        return True

    def import_dir(self, dirpath):
        for root, dirs, files in os.walk(dirpath):
            dirs.sort()
            files.sort()
            for fn in files:
                filepath = os.path.join(root, fn)
                self.import_file(filepath)
