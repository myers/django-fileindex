import mimetypes
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from tqdm import tqdm

from fileindex.models import IndexedFile


class Command(BaseCommand):
    help = "Validate and optionally correct file extensions and MIME types"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Actually fix the issues (rename files and update database)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Limit number of files to check",
        )
        parser.add_argument(
            "--include-derived",
            action="store_true",
            help="Also check derived files (normally skipped)",
        )

    def get_actual_mime_type(self, file_path):
        """Get the actual MIME type of a file using file command or python-magic."""
        try:
            import magic

            mime = magic.Magic(mime=True)
            return mime.from_file(file_path)
        except ImportError:
            # Fallback to file command
            import subprocess

            try:
                result = subprocess.run(
                    ["file", "--mime-type", "-b", file_path],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                mime_type = result.stdout.strip()

                # Handle special cases where file command detects differently
                if "image/avif" in result.stdout.lower() or "avif" in result.stdout.lower():
                    return "image/avif"

                return mime_type
            except subprocess.CalledProcessError:
                # Final fallback to mimetypes
                mime_type, _ = mimetypes.guess_type(file_path)
                return mime_type
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error detecting MIME type: {e}"))
            return None

    def get_correct_extension(self, mime_type):
        """Get the correct file extension for a MIME type."""
        extension_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/avif": ".avif",
            "image/heic": ".heic",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/quicktime": ".mov",
            "video/x-msvideo": ".avi",
            "video/x-matroska": ".mkv",
            "application/pdf": ".pdf",
            "text/plain": ".txt",
        }
        return extension_map.get(mime_type, "")

    def handle(self, *args, **options):
        fix_mode = options["fix"]
        limit = options["limit"]
        include_derived = options["include_derived"]

        self.stdout.write(self.style.WARNING(f"Running in {'FIX' if fix_mode else 'CHECK'} mode"))

        # Get all indexed files
        queryset = IndexedFile.objects.all()
        if limit:
            queryset = queryset[:limit]

        total = queryset.count()
        issues_found = []
        files_fixed = 0

        self.stdout.write(f"Checking {total} files...")
        if include_derived:
            self.stdout.write("Including derived files")

        for indexed_file in tqdm(queryset, total=total):
            # Skip derived files unless explicitly included
            if indexed_file.derived_from_id and not include_derived:
                continue

            # Get the actual file path
            file_path = os.path.join(settings.MEDIA_ROOT, indexed_file.file.name)

            # Check if file exists
            if not os.path.exists(file_path):
                issues_found.append(
                    {
                        "id": indexed_file.id,
                        "issue": "missing_file",
                        "path": file_path,
                    }
                )
                continue

            # Get actual MIME type
            actual_mime = self.get_actual_mime_type(file_path)
            if not actual_mime:
                continue

            # Get current extension from filename
            current_ext = os.path.splitext(indexed_file.file.name)[1].lower()

            # Get expected extension based on actual MIME type
            expected_ext = self.get_correct_extension(actual_mime)

            # Check for mismatches
            db_mime_mismatch = indexed_file.mime_type != actual_mime
            ext_mismatch = expected_ext and current_ext != expected_ext

            if db_mime_mismatch or ext_mismatch:
                issue = {
                    "id": indexed_file.id,
                    "sha512": indexed_file.sha512,
                    "current_path": indexed_file.file.name,
                    "current_ext": current_ext,
                    "expected_ext": expected_ext,
                    "db_mime": indexed_file.mime_type,
                    "actual_mime": actual_mime,
                    "db_mime_mismatch": db_mime_mismatch,
                    "ext_mismatch": ext_mismatch,
                }
                issues_found.append(issue)

                if fix_mode:
                    self.fix_file(indexed_file, actual_mime, expected_ext, file_path)
                    files_fixed += 1

        # Report findings
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS(f"Checked {total} files"))
        self.stdout.write(self.style.WARNING(f"Found {len(issues_found)} issues"))

        if fix_mode:
            self.stdout.write(self.style.SUCCESS(f"Fixed {files_fixed} files"))

        # Show details of issues
        if issues_found and not fix_mode:
            self.stdout.write("\nIssues found (use --fix to correct):\n")
            for issue in issues_found[:10]:  # Show first 10
                if isinstance(issue, dict) and "issue" in issue:
                    if issue["issue"] == "missing_file":
                        self.stdout.write(self.style.ERROR(f"  Missing: {issue['path']}"))
                else:
                    self.stdout.write(f"\n  File ID: {issue['id']}")
                    self.stdout.write(f"    SHA512: {issue['sha512'][:20]}...")
                    if issue["db_mime_mismatch"]:
                        self.stdout.write(f"    MIME: {issue['db_mime']} -> {issue['actual_mime']}")
                    if issue["ext_mismatch"]:
                        self.stdout.write(f"    Extension: {issue['current_ext']} -> {issue['expected_ext']}")

            if len(issues_found) > 10:
                self.stdout.write(f"\n  ... and {len(issues_found) - 10} more")

    @transaction.atomic
    def fix_file(self, indexed_file, actual_mime, expected_ext, current_path):
        """Fix a file's extension and MIME type."""
        try:
            # Update MIME type in database if needed
            if indexed_file.mime_type != actual_mime:
                indexed_file.mime_type = actual_mime

            # Rename file if extension is wrong
            if expected_ext:
                current_name = indexed_file.file.name
                base_name = os.path.splitext(current_name)[0]
                new_name = base_name + expected_ext

                if current_name != new_name:
                    # Get new full path
                    new_path = os.path.join(settings.MEDIA_ROOT, new_name)

                    # Rename the actual file
                    if os.path.exists(current_path):
                        os.rename(current_path, new_path)

                    # Update database
                    indexed_file.file.name = new_name

            indexed_file.save()

            self.stdout.write(
                self.style.SUCCESS(f"  Fixed: {indexed_file.sha512[:20]}... (MIME: {actual_mime}, ext: {expected_ext})")
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  Error fixing {indexed_file.sha512[:20]}...: {e}"))
