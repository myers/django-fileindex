from django.core.management.base import BaseCommand
from django.db.models import Q
from tqdm import tqdm

from fileindex.models import IndexedFile
from fileindex.services import metadata


class Command(BaseCommand):
    help = "Populate JSON metadata only for IndexedFiles without existing metadata"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )
        parser.add_argument(
            "--force-update",
            action="store_true",
            help="Update all files, not just those with missing metadata",
        )
        parser.add_argument(
            "--migrate-structure",
            action="store_true",
            help="Migrate flat metadata to new structured format (video/audio/image keys)",
        )
        parser.add_argument(
            "--mime-type",
            type=str,
            help="Only process files with this MIME type (e.g., video/quicktime)",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        force_update = options.get("force_update", False)
        migrate_structure = options.get("migrate_structure", False)
        mime_type = options.get("mime_type")

        if dry_run:
            self.stdout.write("DRY RUN MODE - No changes will be made\n")

        # Handle structure migration
        if migrate_structure:
            self._migrate_metadata_structure(dry_run)
            return

        # Find IndexedFiles to update
        if force_update:
            # Update all audio/video/image files
            indexed_files = IndexedFile.objects.filter(
                Q(mime_type__startswith="audio/")
                | Q(mime_type__startswith="video/")
                | Q(mime_type__startswith="image/")
            )
        else:
            # Find IndexedFiles without metadata or missing mediainfo
            indexed_files = IndexedFile.objects.filter(
                Q(metadata={}) | Q(metadata__isnull=True) | Q(metadata__mediainfo__isnull=True)
            )

        # Apply MIME type filter if specified
        if mime_type:
            indexed_files = indexed_files.filter(mime_type=mime_type)
            self.stdout.write(f"Filtering by MIME type: {mime_type}")

        total_count = indexed_files.count()
        self.stdout.write(f"Found {total_count} IndexedFiles without metadata\n")

        if total_count == 0:
            self.stdout.write("No files need metadata population.")
            return

        updated_count = 0

        for indexed_file in tqdm(indexed_files, desc="Processing IndexedFiles"):
            try:
                # Extract metadata using the unified metadata service
                new_metadata, is_corrupt = metadata.extract_metadata(indexed_file.file.path, indexed_file.mime_type)

                # Handle corrupt files with more specific context
                if is_corrupt:
                    file_type = indexed_file.mime_type or "unknown"
                    error_msg = f"Marking corrupt file: {indexed_file.sha512[:10]} ({file_type})"
                    if indexed_file.mime_type and indexed_file.mime_type.startswith("image/"):
                        error_msg += " - Failed to extract image dimensions or generate thumbhash"
                    elif indexed_file.mime_type and indexed_file.mime_type.startswith("video/"):
                        error_msg += " - Failed to extract video metadata (missing dimensions/duration/frame rate)"
                    elif indexed_file.mime_type and indexed_file.mime_type.startswith("audio/"):
                        error_msg += " - Failed to extract audio metadata (missing duration)"

                    self.stdout.write(error_msg)
                    if not dry_run:
                        indexed_file.corrupt = True
                        indexed_file.save(update_fields=["corrupt"])
                    continue

                # Check if we have new metadata to save
                if new_metadata and (force_update or indexed_file.metadata != new_metadata):
                    if not dry_run:
                        indexed_file.metadata = new_metadata
                        indexed_file.save(update_fields=["metadata"])
                    updated_count += 1

                    if dry_run:
                        self.stdout.write(f"Would update {indexed_file.sha512[:10]} with new metadata")

            except Exception as e:
                file_type = indexed_file.mime_type or "unknown"
                error_type = type(e).__name__
                self.stdout.write(f"Error processing {indexed_file.sha512[:10]} ({file_type}): {error_type}: {e}")
                continue

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"\nDRY RUN: Would populate metadata for {updated_count} IndexedFiles")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\n✓ Successfully populated metadata for {updated_count} IndexedFiles")
            )

    def _migrate_metadata_structure(self, dry_run: bool) -> None:
        """Migrate old flat metadata structure to new nested structure."""
        self.stdout.write("Migrating metadata to new structure...\n")

        # Find files with old structure (has width/height/bitrate at root level)
        old_structure_files = IndexedFile.objects.filter(
            Q(metadata__has_key="width")
            | Q(metadata__has_key="height")
            | Q(metadata__has_key="bitrate")
            | Q(metadata__has_key="frame_rate")
            | Q(metadata__has_key="thumbhash")
        ).exclude(Q(metadata__has_key="video") | Q(metadata__has_key="audio") | Q(metadata__has_key="image"))

        total_count = old_structure_files.count()
        self.stdout.write(f"Found {total_count} IndexedFiles with old metadata structure\n")

        if total_count == 0:
            self.stdout.write("No files need structure migration.")
            return

        migrated_count = 0

        for indexed_file in tqdm(old_structure_files, desc="Migrating metadata"):
            old_metadata = indexed_file.metadata or {}
            new_metadata = {}

            # Migrate based on mime type
            if indexed_file.mime_type and indexed_file.mime_type.startswith("video/"):
                # Migrate video metadata
                video_info = {}
                if "width" in old_metadata:
                    video_info["width"] = old_metadata["width"]
                if "height" in old_metadata:
                    video_info["height"] = old_metadata["height"]
                if "frame_rate" in old_metadata:
                    video_info["frame_rate"] = old_metadata["frame_rate"]

                if video_info:
                    new_metadata["video"] = video_info

                if "duration" in old_metadata:
                    new_metadata["duration"] = old_metadata["duration"]

            elif indexed_file.mime_type and indexed_file.mime_type.startswith("audio/"):
                # Migrate audio metadata
                audio_info = {}
                if "bitrate" in old_metadata:  # Rename bitrate to audio.bitrate
                    audio_info["bitrate"] = old_metadata["bitrate"]
                if "sample_rate" in old_metadata:
                    audio_info["sample_rate"] = old_metadata["sample_rate"]
                if "channels" in old_metadata:
                    audio_info["channels"] = old_metadata["channels"]

                # Tags
                audio_tags = {}
                if "title" in old_metadata:
                    audio_tags["title"] = old_metadata["title"]
                if "artist" in old_metadata:
                    audio_tags["artist"] = old_metadata["artist"]
                if "album" in old_metadata:
                    audio_tags["album"] = old_metadata["album"]

                if audio_tags:
                    audio_info["tags"] = audio_tags

                if audio_info:
                    new_metadata["audio"] = audio_info

                if "duration" in old_metadata:
                    new_metadata["duration"] = old_metadata["duration"]

            elif indexed_file.mime_type and indexed_file.mime_type.startswith("image/"):
                # Migrate image metadata
                image_info = {}
                if "width" in old_metadata:
                    image_info["width"] = old_metadata["width"]
                if "height" in old_metadata:
                    image_info["height"] = old_metadata["height"]
                if "thumbhash" in old_metadata:
                    image_info["thumbhash"] = old_metadata["thumbhash"]
                if "animated" in old_metadata:
                    image_info["animated"] = old_metadata["animated"]
                else:
                    image_info["animated"] = False

                if image_info:
                    new_metadata["image"] = image_info

                if "duration" in old_metadata:
                    new_metadata["duration"] = old_metadata["duration"]

            # Save the migrated metadata
            if new_metadata:
                if dry_run:
                    self.stdout.write(
                        f"Would migrate {indexed_file.sha512[:10]} from:\n  {old_metadata}\nto:\n  {new_metadata}\n"
                    )
                else:
                    indexed_file.metadata = new_metadata
                    indexed_file.save(update_fields=["metadata"])
                migrated_count += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"\nDRY RUN: Would migrate {migrated_count} IndexedFiles"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\n✓ Successfully migrated {migrated_count} IndexedFiles"))
