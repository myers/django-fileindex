import os
import logging

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from fileindex.watch_service import watch_and_import


class Command(BaseCommand):
    help = "Watch directories for new files and import them automatically"

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", help="Paths to watch for new files")
        parser.add_argument(
            "--remove-after-import",
            action="store_true",
            default=False,
            help="Remove files after successful import",
        )
        parser.add_argument(
            "--no-import-existing",
            action="store_true",
            default=False,
            help="Don't import existing files, only watch for new ones",
        )

    def setup_logger(self, options):
        verbosity = int(options["verbosity"])
        root_logger = logging.getLogger("")
        if verbosity > 1:
            root_logger.setLevel(logging.DEBUG)
        elif verbosity > 0:
            root_logger.setLevel(logging.INFO)

    def handle(self, *args, **options):
        # Verify media root exists
        if not os.path.exists(settings.MEDIA_ROOT):
            raise CommandError(f"MEDIA_ROOT does not exist: {settings.MEDIA_ROOT}")
            
        self.setup_logger(options)
        
        self.stdout.write(self.style.SUCCESS("Starting file watcher..."))
        
        # Watch and import files
        watch_and_import(
            paths=options["paths"],
            remove_after_import=options["remove_after_import"],
            import_existing=not options["no_import_existing"],
            callback=lambda: self.stdout.write(self.style.SUCCESS("File watcher stopped"))
        )