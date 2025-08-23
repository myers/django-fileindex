import logging
import os

from django.core.management.base import BaseCommand
from tqdm import tqdm

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

        parser.add_argument(
            "--show-hash-progress",
            action="store_true",
            default=False,
            help="Show progress bar for file hashing",
        )

    def setup_logger(self, options):
        verbosity = int(options["verbosity"])
        root_logger = logging.getLogger("")
        if verbosity > 1:
            root_logger.setLevel(logging.DEBUG)

    def handle(self, *args, **options):
        self.setup_logger(options)
        only_hard_link = options["only_hard_links"]
        show_hash_progress = options["show_hash_progress"]
        total_stats = {
            "imported": 0,
            "created": 0,
            "skipped": 0,
            "errors": {},
        }

        # Create hash progress callback if requested
        hash_progress_callback = None
        hash_pbar = None

        if show_hash_progress:

            def hash_progress_callback(bytes_processed, total_bytes):
                nonlocal hash_pbar
                if hash_pbar is None or hash_pbar.total != total_bytes:
                    if hash_pbar:
                        hash_pbar.close()
                    hash_pbar = tqdm(
                        total=total_bytes,
                        unit="B",
                        unit_scale=True,
                        desc="Hashing",
                        leave=False,
                    )
                hash_pbar.n = bytes_processed
                hash_pbar.refresh()

        for path in options["paths"]:
            if os.path.isfile(path):
                # Import single file
                self.stdout.write(f"Importing file: {path}")
                indexed_file, created, error = import_file(
                    path,
                    only_hard_link=only_hard_link,
                    validate=True,
                    hash_progress_callback=hash_progress_callback,
                )

                # Close progress bar after file is done
                if hash_pbar:
                    hash_pbar.close()
                    hash_pbar = None

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
                    hash_progress_callback=hash_progress_callback,
                )

                # Merge stats
                total_stats["imported"] += stats["imported"]
                total_stats["created"] += stats["created"]
                total_stats["skipped"] += stats["skipped"]
                total_stats["errors"].update(stats["errors"])

        # Clean up any remaining progress bar
        if hash_pbar:
            hash_pbar.close()

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
