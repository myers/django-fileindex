"""
Management command to fix AVIF files with incorrect MIME type and missing derived_for field.

This command:
1. Finds IndexedFiles derived from GIFs with application/octet-stream MIME type
2. Verifies they are actually AVIF files using ffprobe
3. Updates their MIME type to image/avif
4. Sets derived_for to 'compression'
"""

import json
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models, transaction

from fileindex.models import IndexedFile


class Command(BaseCommand):
    help = "Fix AVIF files with incorrect MIME type and missing derived_for field"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be fixed without making changes",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Limit the number of files to process",
        )
        parser.add_argument(
            "--verify-with-ffprobe",
            action="store_true",
            default=True,
            help="Verify files are AVIF using ffprobe (default: True)",
        )
        parser.add_argument(
            "--fix-existing-avif",
            action="store_true",
            help="Also fix existing AVIF files that have correct MIME type but missing derived_for",
        )

    def verify_is_avif(self, file_path):
        """Use ffprobe to verify if a file is AVIF format"""
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                str(file_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode != 0:
                return False

            data = json.loads(result.stdout)
            format_name = data.get("format", {}).get("format_name", "")

            # AVIF files are typically detected as 'mov,mp4,m4a,3gp,3g2,mj2' by ffprobe
            # but we need to check the codec
            if "mp4" in format_name or "mov" in format_name:
                # Check codec with a stream probe
                cmd_codec = [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "json",
                    str(file_path),
                ]
                result_codec = subprocess.run(
                    cmd_codec, capture_output=True, text=True, timeout=5
                )

                if result_codec.returncode == 0:
                    codec_data = json.loads(result_codec.stdout)
                    streams = codec_data.get("streams", [])
                    if streams:
                        codec_name = streams[0].get("codec_name", "")
                        # AV1 codec indicates AVIF
                        return codec_name == "av1"

            return False

        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            self.stdout.write(
                self.style.WARNING(f"  Could not verify {file_path}: {e}")
            )
            return False

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        limit = options.get("limit")
        verify_with_ffprobe = options.get("verify_with_ffprobe", True)
        fix_existing_avif = options.get("fix_existing_avif", False)

        self.stdout.write("Finding AVIF files with incorrect metadata...")

        # Find files that need fixing
        if fix_existing_avif:
            # Include files with correct MIME type but missing derived_for
            candidates = (
                IndexedFile.objects.filter(
                    derived_from__mime_type="image/gif", derived_for__isnull=True
                )
                .filter(
                    models.Q(mime_type="application/octet-stream")
                    | models.Q(mime_type="image/avif")
                )
                .select_related("derived_from")
            )
        else:
            # Only files with wrong MIME type
            candidates = IndexedFile.objects.filter(
                derived_from__mime_type="image/gif",
                mime_type="application/octet-stream",
                derived_for__isnull=True,
            ).select_related("derived_from")

        if limit:
            candidates = candidates[:limit]

        total_candidates = candidates.count()
        self.stdout.write(f"Found {total_candidates} candidate files to check")

        if dry_run:
            self.stdout.write("DRY RUN MODE - No changes will be made")

        fixed_count = 0
        skipped_count = 0
        error_count = 0

        for indexed_file in candidates:
            file_path = Path(settings.MEDIA_ROOT) / indexed_file.file.name

            # Verify it's actually an AVIF file (only for octet-stream files)
            if (
                verify_with_ffprobe
                and indexed_file.mime_type == "application/octet-stream"
            ):
                if not file_path.exists():
                    self.stdout.write(
                        self.style.ERROR(f"  File not found: {file_path}")
                    )
                    error_count += 1
                    continue

                if not self.verify_is_avif(file_path):
                    if dry_run:
                        self.stdout.write(
                            f"  Would skip {indexed_file.sha512[:10]}... - not verified as AVIF"
                        )
                    skipped_count += 1
                    continue

            if dry_run:
                changes = []
                if indexed_file.mime_type != "image/avif":
                    changes.append(f"MIME: {indexed_file.mime_type} → image/avif")
                if indexed_file.derived_for != "compression":
                    changes.append("derived_for: None → compression")

                self.stdout.write(
                    f"  Would fix: {indexed_file.sha512[:10]}... "
                    f"(from GIF {indexed_file.derived_from.sha512[:10]}...) "
                    f"[{', '.join(changes)}]"
                )
                fixed_count += 1
            else:
                try:
                    with transaction.atomic():
                        # Only update fields that need changing
                        update_fields = []
                        if indexed_file.mime_type != "image/avif":
                            indexed_file.mime_type = "image/avif"
                            update_fields.append("mime_type")
                        if indexed_file.derived_for != "compression":
                            indexed_file.derived_for = "compression"
                            update_fields.append("derived_for")

                        if update_fields:
                            indexed_file.save(update_fields=update_fields)
                            fixed_count += 1

                        if fixed_count % 100 == 0:
                            self.stdout.write(f"  Fixed {fixed_count} files...")

                except Exception as e:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"  Error fixing {indexed_file.sha512[:10]}...: {e}"
                        )
                    )

        # Summary
        self.stdout.write("\n" + "=" * 50)
        if dry_run:
            self.stdout.write(self.style.SUCCESS("DRY RUN COMPLETE"))
            self.stdout.write(f"Would fix: {fixed_count} files")
            self.stdout.write(f"Would skip: {skipped_count} files")
        else:
            self.stdout.write(self.style.SUCCESS("FIX COMPLETE"))
            self.stdout.write(f"Fixed: {fixed_count} files")
            self.stdout.write(f"Skipped: {skipped_count} files")

        if error_count:
            self.stdout.write(self.style.ERROR(f"Errors: {error_count}"))

        # Show current state
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("Current AVIF file statistics:")

        correct_avif = IndexedFile.objects.filter(
            mime_type="image/avif", derived_for="compression"
        ).count()

        remaining_wrong = IndexedFile.objects.filter(
            derived_from__mime_type="image/gif",
            mime_type="application/octet-stream",
            derived_for__isnull=True,
        ).count()

        self.stdout.write(f"  Correct AVIF files: {correct_avif}")
        self.stdout.write(f"  Remaining to fix: {remaining_wrong}")
