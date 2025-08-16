"""
Management command to retry metadata extraction for images that failed previously.
Uses Pillow with robust settings and ffprobe as fallback.
"""

import logging

from django.core.management.base import BaseCommand
from django.db.models import Q
from PIL import Image, ImageFile

from fileindex.models import IndexedFile, IndexedImage

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Retry metadata extraction for images missing dimensions or with corrupt flag"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be processed without making changes",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Limit number of images to process",
        )
        parser.add_argument(
            "--only-corrupt",
            action="store_true",
            help="Only process images marked as corrupt",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            help="Only process images with missing dimensions",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options.get("limit")
        only_corrupt = options.get("only_corrupt", False)
        only_missing = options.get("only_missing", False)

        # Enable Pillow robustness settings globally
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        Image.MAX_IMAGE_PIXELS = 200000000  # Increase from default 89M

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

        # Build query for images to process
        query = Q()

        if only_corrupt:
            # Only corrupt images
            query = Q(indexedfile__corrupt=True)
        elif only_missing:
            # Only missing dimensions
            query = Q(width__isnull=True) | Q(height__isnull=True)
        else:
            # Both corrupt and missing dimensions
            query = (
                Q(indexedfile__corrupt=True)
                | Q(width__isnull=True)
                | Q(height__isnull=True)
            )

        # Get images that need processing
        images_to_process = IndexedImage.objects.filter(query).select_related(
            "indexedfile"
        )

        if limit:
            images_to_process = images_to_process[:limit]

        total_count = images_to_process.count()
        self.stdout.write(f"Found {total_count} images to process")

        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("No images need processing"))
            return

        # Show sample
        self.stdout.write("\nSample of images to process:")
        for img in images_to_process[:5]:
            status = []
            if img.indexedfile.corrupt:
                status.append("corrupt")
            if img.width is None or img.height is None:
                status.append("missing dimensions")
            self.stdout.write(
                f"  - {img.indexedfile.sha512[:10]}... "
                f"({img.indexedfile.mime_type}) - {', '.join(status)}"
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"\nDRY RUN: Would process {total_count} images")
            )
            return

        # Process images
        success_count = 0
        pillow_success = 0
        ffprobe_success = 0
        failed_count = 0

        self.stdout.write(f"\nProcessing {total_count} images...")

        for img in images_to_process:
            try:
                # Clear corrupt flag if set
                was_corrupt = img.indexedfile.corrupt
                if was_corrupt:
                    img.indexedfile.corrupt = False

                # Try to generate size
                old_dimensions = (img.width, img.height)
                IndexedImage.objects.generate_size(img)

                # Check what method succeeded
                if old_dimensions == (None, None) and img.width and img.height:
                    # Dimensions were successfully extracted
                    success_count += 1

                    # Try to determine which method worked (crude heuristic)
                    try:
                        # If Pillow can open it now, it was probably Pillow
                        with Image.open(img.indexedfile.file.path):
                            pillow_success += 1
                    except Exception:
                        # Otherwise assume ffprobe
                        ffprobe_success += 1

                    if was_corrupt:
                        self.stdout.write(
                            f"  ✓ Fixed corrupt image {img.indexedfile.sha512[:10]}... "
                            f"Dimensions: {img.width}x{img.height}"
                        )

                # Save changes
                img.save()
                if was_corrupt:
                    img.indexedfile.save(update_fields=["corrupt"])

            except Exception as e:
                failed_count += 1
                # Restore corrupt flag if we couldn't process it
                if was_corrupt:
                    img.indexedfile.corrupt = True
                    img.indexedfile.save(update_fields=["corrupt"])

                self.stdout.write(
                    self.style.ERROR(
                        f"  ✗ Failed {img.indexedfile.sha512[:10]}...: {str(e)[:50]}"
                    )
                )

        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(
            self.style.SUCCESS(f"Successfully processed: {success_count}")
        )
        if success_count > 0:
            self.stdout.write(f"  - Pillow succeeded: ~{pillow_success}")
            self.stdout.write(f"  - FFprobe succeeded: ~{ffprobe_success}")
        self.stdout.write(self.style.ERROR(f"Failed: {failed_count}"))

        # Check remaining issues
        remaining_corrupt = IndexedFile.objects.filter(
            corrupt=True, mime_type__startswith="image/"
        ).count()
        remaining_missing = IndexedImage.objects.filter(
            Q(width__isnull=True) | Q(height__isnull=True)
        ).count()

        if remaining_corrupt > 0 or remaining_missing > 0:
            self.stdout.write("\nRemaining issues:")
            if remaining_corrupt:
                self.stdout.write(f"  - Corrupt images: {remaining_corrupt}")
            if remaining_missing:
                self.stdout.write(f"  - Images missing dimensions: {remaining_missing}")
