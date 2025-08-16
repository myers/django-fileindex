import pprint
import logging

from django.core.management.base import BaseCommand

from fileindex.file_import_service import import_paths


class Command(BaseCommand):
    help = "Index files and directories"

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", help="Paths to files or directories to index")
        parser.add_argument(
            "--only-hard-links",
            action="store_true",
            default=False,
            help="Only allow hard links (no copying)",
        )

    def setup_logger(self, options):
        verbosity = int(options["verbosity"])
        root_logger = logging.getLogger("")
        if verbosity > 1:
            root_logger.setLevel(logging.DEBUG)
        elif verbosity > 0:
            root_logger.setLevel(logging.INFO)

    def handle(self, *args, **options):
        self.setup_logger(options)
        
        # Import all paths
        errors = import_paths(
            paths=options["paths"],
            only_hard_link=options["only_hard_links"],
            remove_after_import=False
        )
        
        # Report results
        if errors:
            self.stdout.write(self.style.ERROR(f"\nEncountered {len(errors)} errors:"))
            pprint.pprint(errors)
            return
            
        self.stdout.write(self.style.SUCCESS("\nAll files imported successfully!"))