from django.core.management.base import BaseCommand
from django.db.models import Q
from tqdm import tqdm

from fileindex.models import IndexedFile
from fileindex.services import media_analysis


class Command(BaseCommand):
    help = "Populate JSON metadata only for IndexedFiles without existing metadata"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)

        if dry_run:
            self.stdout.write("DRY RUN MODE - No changes will be made\n")

        # Find IndexedFiles without metadata
        indexed_files = IndexedFile.objects.filter(Q(metadata={}) | Q(metadata__isnull=True))

        total_count = indexed_files.count()
        self.stdout.write(f"Found {total_count} IndexedFiles without metadata\n")

        if total_count == 0:
            self.stdout.write("No files need metadata population.")
            return

        updated_count = 0

        for indexed_file in tqdm(indexed_files, desc="Processing IndexedFiles"):
            metadata = {}
            updated = False

            try:
                # Extract metadata directly from the file based on MIME type
                if indexed_file.mime_type and indexed_file.mime_type.startswith("image/"):
                    # Process images
                    try:
                        dimensions = media_analysis.extract_image_dimensions(indexed_file.file.path)
                        if dimensions:
                            width, height = dimensions
                            metadata["width"] = width
                            metadata["height"] = height
                            updated = True
                    except Exception as e:
                        self.stdout.write(f"Failed to get dimensions for {indexed_file.sha512[:10]}: {e}")
                        # Mark as corrupt if we can't read the file
                        if ("Truncated" in str(e) or "cannot identify" in str(e).lower()) and not dry_run:
                            indexed_file.corrupt = True
                            indexed_file.save(update_fields=["corrupt"])
                        continue

                    # Check for animation (GIF/AVIF)
                    if indexed_file.mime_type in ["image/gif", "image/avif"]:
                        try:
                            duration = media_analysis.get_duration(indexed_file.file.path, indexed_file.mime_type)
                            if duration and duration > 0:
                                metadata["duration"] = int(duration * 1000)  # Convert to ms
                                metadata["animated"] = True
                                updated = True
                            else:
                                metadata["animated"] = False
                                updated = True
                        except Exception as e:
                            self.stdout.write(f"Failed to get duration for {indexed_file.sha512[:10]}: {e}")

                elif indexed_file.mime_type and indexed_file.mime_type.startswith("video/"):
                    # Process videos
                    try:
                        video_metadata = media_analysis.extract_video_metadata(indexed_file.file.path)

                        if video_metadata.get("width"):
                            metadata["width"] = video_metadata["width"]
                            updated = True
                        if video_metadata.get("height"):
                            metadata["height"] = video_metadata["height"]
                            updated = True
                        if video_metadata.get("duration"):
                            metadata["duration"] = int(video_metadata["duration"] * 1000)  # Convert to ms
                            updated = True
                        if video_metadata.get("frame_rate"):
                            metadata["frame_rate"] = video_metadata["frame_rate"]
                            updated = True
                    except Exception as e:
                        self.stdout.write(f"Failed to extract video metadata for {indexed_file.sha512[:10]}: {e}")

                elif indexed_file.mime_type and indexed_file.mime_type.startswith("audio/"):
                    # Process audio
                    try:
                        audio_metadata = media_analysis.extract_audio_metadata(indexed_file.file.path)

                        if audio_metadata.get("duration"):
                            metadata["duration"] = int(audio_metadata["duration"] * 1000)  # Convert to ms
                            updated = True
                    except Exception as e:
                        self.stdout.write(f"Failed to extract audio metadata for {indexed_file.sha512[:10]}: {e}")

            except Exception as e:
                self.stdout.write(f"Error processing {indexed_file.sha512[:10]}: {e}")
                continue

            # Save if we updated metadata
            if updated:
                if not dry_run:
                    indexed_file.metadata = metadata
                    indexed_file.save(update_fields=["metadata"])
                updated_count += 1

                if dry_run:
                    self.stdout.write(f"Would update {indexed_file.sha512[:10]} with: {metadata}")

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"\nDRY RUN: Would populate metadata for {updated_count} IndexedFiles")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\n✓ Successfully populated metadata for {updated_count} IndexedFiles")
            )
