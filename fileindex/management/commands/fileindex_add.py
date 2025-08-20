import logging
import os

from django.core.management.base import BaseCommand

from fileindex.exceptions import ImportErrorType
from fileindex.services.file_import import import_directory, import_file


class Command(BaseCommand):
    help = "Index files into the fileindex system"

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", help="Paths to files or directories to index")

        parser.add_argument(
            "--only-hard-links",
            action="store_true",
            default=False,
            help="Only create hard links (no copying)",
        )

    def setup_logger(self, options):
        verbosity = int(options["verbosity"])
        root_logger = logging.getLogger("")
        if verbosity > 1:
            root_logger.setLevel(logging.DEBUG)

    def handle(self, *args, **options):
        self.setup_logger(options)
        only_hard_link = options["only_hard_links"]
        total_stats = {
            "imported": 0,
            "created": 0,
            "skipped": 0,
            "errors": {},
        }

        for path in options["paths"]:
            if os.path.isfile(path):
                # Import single file
                self.stdout.write(f"Importing file: {path}")
                indexed_file, created, error = import_file(
                    path,
                    only_hard_link=only_hard_link,
                    validate=True,
                )

                if error:
                    if error == ImportErrorType.VALIDATION_FAILED:
                        total_stats["skipped"] += 1
                        self.stdout.write(self.style.WARNING(f"Skipped: {path}"))
                    else:
                        total_stats["errors"][path] = str(error)
                        self.stdout.write(self.style.ERROR(f"Error: {error}"))
                else:
                    total_stats["imported"] += 1
                    if created:
                        total_stats["created"] += 1
                    self.stdout.write(self.style.SUCCESS(f"Imported: {path}"))
            else:
                # Import directory
                self.stdout.write(f"Importing directory: {path}")

                def progress_callback(filepath, success, error_msg):
                    if options["verbosity"] > 1:
                        if success:
                            self.stdout.write(f"  ✓ {filepath}")
                        else:
                            self.stdout.write(f"  ✗ {filepath}: {error_msg if error_msg else 'Failed'}")

                stats = import_directory(
                    path,
                    recursive=True,
                    only_hard_link=only_hard_link,
                    validate=True,
                    progress_callback=progress_callback,
                )

                # Merge stats
                total_stats["imported"] += stats["imported"]
                total_stats["created"] += stats["created"]
                total_stats["skipped"] += stats["skipped"]
                total_stats["errors"].update(stats["errors"])

        # Print summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS(f"Imported: {total_stats['imported']} files"))
        self.stdout.write(self.style.SUCCESS(f"Created: {total_stats['created']} new entries"))
        self.stdout.write(self.style.WARNING(f"Skipped: {total_stats['skipped']} files"))

        if total_stats["errors"]:
            self.stdout.write(self.style.ERROR(f"\nErrors ({len(total_stats['errors'])} files):"))
            for filepath, error in list(total_stats["errors"].items())[:10]:
                self.stdout.write(self.style.ERROR(f"  {filepath}: {error}"))
            if len(total_stats["errors"]) > 10:
                self.stdout.write(self.style.ERROR(f"  ... and {len(total_stats['errors']) - 10} more"))
