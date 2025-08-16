import logging
import os
import pprint

from django.core.management.base import BaseCommand

from fileindex.models import IndexedFile
from fileindex.services.file_validation import should_import


class Command(BaseCommand):
    help = "Index all files"

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+")

        parser.add_argument(
            "--only-hard-links",
            action="store_true",
            default=False,
            help="Only allow hard links",
        )

    def setup_logger(self, options):
        verbosity = int(options["verbosity"])
        root_logger = logging.getLogger("")
        if verbosity > 1:
            root_logger.setLevel(logging.DEBUG)

    def handle(self, *args, **options):
        self.setup_logger(options)
        self.errors = {}
        for path in options["paths"]:
            if os.path.isfile(path):
                self.import_file(path, **options)
            else:
                self.import_dir(path, **options)
        pprint.pprint(self.errors)

    def import_file(self, filepath, **options):
        if not should_import(filepath):
            print(f"not importing {filepath!r}")
            return False
        print(f"importing {filepath!r}...")
        try:
            IndexedFile.objects.get_or_create_from_file(
                filepath, only_hard_link=options["only_hard_links"]
            )
        except Exception as ee:
            self.errors[filepath] = str(ee)
            print(f"holy cats an error {ee!r}")
            return False
        return True

    def import_dir(self, dirpath, **options):
        for root, dirs, files in os.walk(dirpath):
            dirs.sort()
            files.sort()
            for fn in files:
                filepath = os.path.join(root, fn)
                self.import_file(filepath, **options)
