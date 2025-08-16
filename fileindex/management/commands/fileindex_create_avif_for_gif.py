import logging

from django.core.management.base import BaseCommand

from fileindex.models import IndexedFile
from fileindex.services.avif_generation import enqueue_creating_avif_from_gif


class Command(BaseCommand):
    help = "Queue AVIF creation jobs for GIF files that don't have AVIF versions"

    def setup_logger(self, options):
        verbosity = int(options["verbosity"])
        root_logger = logging.getLogger("")
        if verbosity > 1:
            root_logger.setLevel(logging.DEBUG)

    def handle(self, *args, **options):
        self.setup_logger(options)

        # Find all GIFs without AVIF versions
        gifs_to_process = IndexedFile.objects.filter(mime_type="image/gif").exclude(
            derived_files__mime_type="image/avif"
        )

        count = 0
        for indexed_file in gifs_to_process:
            enqueue_creating_avif_from_gif(indexed_file.indexedimage)
            count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Queued {count} GIF files for AVIF conversion")
        )
