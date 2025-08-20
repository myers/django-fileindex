"""
Django management command to migrate fileindex structure:
- From 2-level to 3-level directory structure
- Remove base32 padding (=)
- Remove file extensions
"""

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from tqdm import tqdm

from fileindex.models import IndexedFile


class Command(BaseCommand):
    help = "Migrate fileindex from 2-level to 3-level structure, remove padding and extensions"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without making modifications",
        )
        parser.add_argument(
            "--verify",
            action="store_true",
            help="Verify migration completed successfully",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of files to process in each transaction batch",
        )

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]
        self.verify_only = options["verify"]
        self.batch_size = options["batch_size"]
        self.media_root = Path(settings.MEDIA_ROOT)

        if self.verify_only:
            return self.verify_migration()

        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        # Get total count of files (fast query)
        total_files = IndexedFile.objects.count()

        if total_files == 0:
            self.stdout.write(self.style.SUCCESS("No files to migrate"))
            return

        self.stdout.write(f"Total files in database: {total_files}")
        self.stdout.write("Will check each file and migrate if needed...")

        # Perform migration (checking each file as we go)
        self.migrate_all_files()

        self.stdout.write(self.style.SUCCESS("Migration completed successfully"))

    def is_migrated(self, indexed_file):
        """Check if a file has already been migrated by examining its path structure"""
        path = indexed_file.file.name

        # Migrated files have:
        # - 3 slashes (fileindex/XX/YY/HASH)
        # - No equals sign (padding removed)
        # - No file extension

        slash_count = path.count("/")
        has_padding = "=" in path
        has_extension = Path(path).suffix != ""

        # Migrated files should have exactly 3 slashes and no padding/extension
        return slash_count == 3 and not has_padding and not has_extension

    def calculate_new_path(self, indexed_file):
        """Calculate the new path for a file"""
        # Remove padding from hash
        hash_no_padding = indexed_file.sha512.rstrip("=")

        # Create 3-level directory structure
        level1 = hash_no_padding[0:2]
        level2 = hash_no_padding[2:4]

        # New relative path (no extension)
        new_relative_path = Path("fileindex") / level1 / level2 / hash_no_padding

        return new_relative_path

    def migrate_all_files(self):
        """Migrate all files, checking each one as we go"""
        total_files = IndexedFile.objects.count()
        errors = []
        skipped = 0
        migrated = 0

        # Use iterator to avoid loading all objects into memory
        queryset = IndexedFile.objects.all().iterator(chunk_size=self.batch_size)

        # Create progress bar
        with tqdm(total=total_files, desc="Processing files", unit="file") as pbar:
            batch = []

            for indexed_file in queryset:
                # Check if already migrated
                if self.is_migrated(indexed_file):
                    skipped += 1
                    pbar.update(1)
                    pbar.set_postfix(migrated=migrated, skipped=skipped)
                    continue

                # Check if file exists
                current_path = self.media_root / indexed_file.file.name
                if not current_path.exists():
                    error_msg = f"File not found: {indexed_file.file.name}"
                    pbar.write(self.style.WARNING(error_msg))
                    errors.append(error_msg)
                    pbar.update(1)
                    continue

                # Add to batch for migration
                batch.append(indexed_file)

                # Process batch when it reaches batch_size
                if len(batch) >= self.batch_size:
                    if not self.dry_run:
                        with transaction.atomic():
                            for file_to_migrate in batch:
                                try:
                                    self.migrate_single_file(file_to_migrate)
                                    migrated += 1
                                except Exception as e:
                                    error_msg = f"Failed to migrate file {file_to_migrate.id}: {e}"
                                    pbar.write(self.style.ERROR(error_msg))
                                    errors.append(error_msg)
                    else:
                        for file_to_migrate in batch:
                            self.migrate_single_file(file_to_migrate)
                            migrated += 1

                    pbar.update(len(batch))
                    pbar.set_postfix(migrated=migrated, skipped=skipped)
                    batch = []

            # Process remaining files in batch
            if batch:
                if not self.dry_run:
                    with transaction.atomic():
                        for file_to_migrate in batch:
                            try:
                                self.migrate_single_file(file_to_migrate)
                                migrated += 1
                            except Exception as e:
                                error_msg = f"Failed to migrate file {file_to_migrate.id}: {e}"
                                pbar.write(self.style.ERROR(error_msg))
                                errors.append(error_msg)
                else:
                    for file_to_migrate in batch:
                        self.migrate_single_file(file_to_migrate)
                        migrated += 1

                pbar.update(len(batch))
                pbar.set_postfix(migrated=migrated, skipped=skipped)

        # Report results
        self.stdout.write(f"\nMigrated: {migrated} files")
        self.stdout.write(f"Skipped (already migrated): {skipped} files")

        if errors:
            self.stdout.write(self.style.ERROR(f"{len(errors)} errors occurred during migration"))
            for error in errors[:10]:  # Show first 10 errors
                self.stdout.write(self.style.ERROR(error))
            if len(errors) > 10:
                self.stdout.write(self.style.ERROR(f"... and {len(errors) - 10} more errors"))

    def migrate_single_file(self, indexed_file):
        """Migrate a single file"""
        current_path = self.media_root / indexed_file.file.name
        new_relative_path = self.calculate_new_path(indexed_file)
        new_absolute_path = self.media_root / new_relative_path

        if self.dry_run:
            # In dry run, use stdout.write instead of tqdm.write
            self.stdout.write(f"Would migrate: {indexed_file.file.name} -> {new_relative_path}")
            return

        # Create new directory structure if needed
        new_absolute_path.parent.mkdir(parents=True, exist_ok=True)

        # Move the file
        if current_path.exists():
            shutil.move(str(current_path), str(new_absolute_path))
        else:
            raise FileNotFoundError(f"Source file not found: {current_path}")

        # Update database
        indexed_file.file.name = str(new_relative_path)
        indexed_file.save()

        # Verify move was successful
        if not new_absolute_path.exists():
            raise FileNotFoundError(f"File not found after move: {new_absolute_path}")

    def verify_migration(self):
        """Verify that migration completed successfully"""
        self.stdout.write("Verifying migration...")

        issues = []
        total_files = IndexedFile.objects.count()

        for indexed_file in tqdm(IndexedFile.objects.all(), total=total_files, desc="Verifying"):
            expected_path = self.media_root / indexed_file.file.name

            # Check file exists
            if not expected_path.exists():
                issues.append(f"Missing file: {indexed_file.file.name}")
                continue

            # Check no padding in filename
            if "=" in indexed_file.file.name:
                issues.append(f"File still has padding: {indexed_file.file.name}")

            # Check no extension
            if expected_path.suffix:
                issues.append(f"File still has extension: {indexed_file.file.name}")

            # Check 3-level structure
            parts = Path(indexed_file.file.name).parts
            if len(parts) != 4:  # fileindex/XX/YY/HASH
                issues.append(f"Incorrect directory depth ({len(parts)}): {indexed_file.file.name}")

        if issues:
            self.stdout.write(self.style.ERROR(f"Found {len(issues)} issues:"))
            for issue in issues[:10]:  # Show first 10 issues
                self.stdout.write(self.style.ERROR(f"  - {issue}"))
            if len(issues) > 10:
                self.stdout.write(self.style.ERROR(f"  ... and {len(issues) - 10} more"))
            return False
        else:
            self.stdout.write(self.style.SUCCESS("All files migrated successfully"))
            return True
