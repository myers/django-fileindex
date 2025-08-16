"""
Django management command to backup orphaned files from media/fileindex to backups/fileindex.
Orphaned files are those present in the filesystem but not tracked in the database.
"""

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from tqdm import tqdm

from fileindex.models import IndexedFile


class Command(BaseCommand):
    help = "Move orphaned files from media/fileindex to backups/fileindex"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without making modifications",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Limit number of files to process",
        )

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]
        self.limit = options.get("limit")
        self.media_root = Path(settings.MEDIA_ROOT)
        self.fileindex_dir = self.media_root / "fileindex"
        self.backup_dir = Path(settings.BASE_DIR) / "backups" / "fileindex"

        if self.dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )

        # Get all tracked file paths from database
        tracked_paths = self.get_tracked_paths()
        self.stdout.write(f"Found {len(tracked_paths)} files in database")

        # Find orphaned files
        orphaned_files = self.find_orphaned_files(tracked_paths)

        if not orphaned_files:
            self.stdout.write(self.style.SUCCESS("No orphaned files found"))
            return

        self.stdout.write(f"Found {len(orphaned_files)} orphaned files")

        if not self.dry_run:
            confirm = input("Continue with backup? (yes/no): ")
            if confirm.lower() != "yes":
                self.stdout.write(self.style.ERROR("Backup cancelled"))
                return

        # Backup orphaned files
        self.backup_files(orphaned_files)

        self.stdout.write(self.style.SUCCESS("Backup completed successfully"))

    def get_tracked_paths(self):
        """Get set of all file paths tracked in the database"""
        tracked_paths = set()

        for indexed_file in IndexedFile.objects.all():
            # Store the relative path from media root
            tracked_paths.add(self.media_root / indexed_file.file.name)

        return tracked_paths

    def find_orphaned_files(self, tracked_paths):
        """Find files in fileindex directory that aren't in the database"""
        orphaned_files = []

        if not self.fileindex_dir.exists():
            self.stdout.write(
                self.style.WARNING(f"Directory does not exist: {self.fileindex_dir}")
            )
            return orphaned_files

        # Walk through all files in fileindex directory
        all_files = list(self.fileindex_dir.rglob("*"))

        for file_path in all_files:
            if file_path.is_file() and file_path not in tracked_paths:
                orphaned_files.append(file_path)

                if self.limit and len(orphaned_files) >= self.limit:
                    self.stdout.write(
                        self.style.WARNING(f"Limiting to {self.limit} files")
                    )
                    break

        return orphaned_files

    def backup_files(self, orphaned_files):
        """Move orphaned files to backup directory"""
        errors = []

        with tqdm(
            total=len(orphaned_files), desc="Backing up files", unit="file"
        ) as pbar:
            for file_path in orphaned_files:
                try:
                    self.backup_single_file(file_path)
                    pbar.update(1)
                except Exception as e:
                    error_msg = f"Failed to backup {file_path}: {e}"
                    pbar.write(self.style.ERROR(error_msg))
                    errors.append(error_msg)

        if errors:
            self.stdout.write(
                self.style.ERROR(f"\n{len(errors)} errors occurred during backup")
            )
            for error in errors[:10]:  # Show first 10 errors
                self.stdout.write(self.style.ERROR(error))
            if len(errors) > 10:
                self.stdout.write(self.style.ERROR(f"... and {len(errors) - 10} more"))

    def backup_single_file(self, file_path):
        """Backup a single orphaned file"""
        # Calculate relative path from media/fileindex
        relative_path = file_path.relative_to(self.media_root)

        # Calculate backup destination path
        backup_path = self.backup_dir / relative_path

        if self.dry_run:
            self.stdout.write(f"Would move: {relative_path} -> backups/{relative_path}")
            return

        # Create backup directory structure if needed
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        # Move the file
        shutil.move(str(file_path), str(backup_path))

        # Verify move was successful
        if not backup_path.exists():
            raise FileNotFoundError(f"File not found after move: {backup_path}")

        # Remove empty directories in source
        try:
            parent = file_path.parent
            while parent != self.fileindex_dir and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
        except Exception:
            # Ignore errors when removing empty directories
            pass
