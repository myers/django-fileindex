import logging
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from watchdog.events import LoggingEventHandler

from fileindex.services.watch import DirectoryWatcher


class Command(BaseCommand):
    help = "Watch directories and import new files as they are added"

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", help="Directories to watch for new files")

        parser.add_argument(
            "--delete-after",
            action="store_true",
            default=False,
            help="Delete original files after successful import",
        )

    def handle(self, *args, **options):
        assert os.path.exists(settings.MEDIA_ROOT), f"MEDIA_ROOT does not exist: {settings.MEDIA_ROOT!r}"

        # Setup logging
        verbosity = int(options["verbosity"])
        root_logger = logging.getLogger("")
        if verbosity > 1:
            root_logger.setLevel(logging.DEBUG)

        # Create callbacks for progress reporting
        def file_event_callback(filepath, success, message):
            if success:
                self.stdout.write(self.style.SUCCESS(f"{message}: {filepath}"))
            elif "Skipped" in message:
                self.stdout.write(self.style.WARNING(f"{message}"))
            else:
                self.stdout.write(self.style.ERROR(f"{message}"))

        def import_progress_callback(filepath, success, error_msg):
            if verbosity > 1:
                if success:
                    self.stdout.write(f"  ✓ {filepath}")
                else:
                    self.stdout.write(f"  ✗ {filepath}: {error_msg if error_msg else 'Failed'}")

        # Create the watcher service
        watcher = DirectoryWatcher(
            paths=options["paths"],
            delete_after=options.get("delete_after", False),
            recursive=True,
            validate=True,
            file_event_callback=file_event_callback,
            import_progress_callback=import_progress_callback if verbosity > 1 else None,
        )

        # Import existing files first
        self.stdout.write("Importing existing files...")
        results = watcher.import_existing_files()

        # Print summary for each directory
        self.stdout.write("\n" + "=" * 60)
        for dirpath, stats in results.items():
            self.stdout.write(f"\nDirectory: {dirpath}")
            self.stdout.write(self.style.SUCCESS(f"  Imported: {stats['imported']} files"))
            self.stdout.write(self.style.SUCCESS(f"  Created: {stats['created']} new entries"))
            self.stdout.write(self.style.WARNING(f"  Skipped: {stats['skipped']} files"))
            if stats["errors"]:
                self.stdout.write(self.style.ERROR(f"  Errors: {len(stats['errors'])} files"))

        # Start watching for new files
        self.stdout.write("=" * 60)
        self.stdout.write("\nWatching for new files...")
        for path in options["paths"]:
            self.stdout.write(f"  • {path}")

        # Add verbose logging if requested
        if verbosity > 1:
            observer = watcher.start_watching()
            # Add logging event handler for verbose output
            event_handler = LoggingEventHandler()
            for path in options["paths"]:
                observer.schedule(event_handler, path, recursive=True)

        # Start watching and wait
        try:
            watcher.watch_and_wait()
        except KeyboardInterrupt:
            self.stdout.write("\nStopping watcher...")

        self.stdout.write(self.style.SUCCESS("\nWatch stopped."))
