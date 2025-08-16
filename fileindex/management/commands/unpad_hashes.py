"""
Django management command to remove padding from SHA1 and SHA512 hashes in the database.

This command finds all IndexedFile records with padded hashes (ending with '=')
and removes the padding to match the current hash generation format.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from tqdm import tqdm

from fileindex.models import IndexedFile


class Command(BaseCommand):
    help = "Remove base32 padding from SHA1 and SHA512 hashes in the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Number of records to process in each transaction batch",
        )

    def handle(self, *args, **options):
        self.batch_size = options["batch_size"]

        # Find all files with padded hashes
        padded_files = IndexedFile.objects.filter(
            sha1__endswith="="
        ) | IndexedFile.objects.filter(sha512__endswith="=")
        total_files = padded_files.distinct().count()

        if total_files == 0:
            self.stdout.write(self.style.SUCCESS("No padded hashes found"))
            return

        self.stdout.write(f"Found {total_files} files with padded hashes")

        # Process files in batches
        updated_count = 0
        errors = []

        # Use iterator to avoid loading all objects into memory
        queryset = padded_files.distinct().iterator(chunk_size=self.batch_size)

        with tqdm(total=total_files, desc="Removing padding", unit="file") as pbar:
            batch = []

            for file_obj in queryset:
                batch.append(file_obj)

                # Process batch when it reaches batch_size
                if len(batch) >= self.batch_size:
                    batch_updated, batch_errors = self.process_batch(batch)
                    updated_count += batch_updated
                    errors.extend(batch_errors)
                    pbar.update(len(batch))
                    pbar.set_postfix(updated=updated_count, errors=len(errors))
                    batch = []

            # Process remaining files in batch
            if batch:
                batch_updated, batch_errors = self.process_batch(batch)
                updated_count += batch_updated
                errors.extend(batch_errors)
                pbar.update(len(batch))
                pbar.set_postfix(updated=updated_count, errors=len(errors))

        # Report results
        self.stdout.write(f"\nSuccessfully updated: {updated_count} files")

        if errors:
            self.stdout.write(
                self.style.ERROR(f"{len(errors)} errors occurred during update")
            )
            for error in errors[:10]:  # Show first 10 errors
                self.stdout.write(self.style.ERROR(error))
            if len(errors) > 10:
                self.stdout.write(
                    self.style.ERROR(f"... and {len(errors) - 10} more errors")
                )
        else:
            self.stdout.write(self.style.SUCCESS("All hashes successfully unpadded!"))

    def process_batch(self, batch):
        """Process a batch of files, removing padding from their hashes."""
        updated_count = 0
        errors = []

        try:
            with transaction.atomic():
                for file_obj in batch:
                    try:
                        updated = False

                        # Handle SHA1
                        if file_obj.sha1 and file_obj.sha1.endswith("="):
                            old_sha1 = file_obj.sha1
                            new_sha1 = old_sha1.rstrip("=")

                            # Check for SHA1 conflicts
                            if (
                                IndexedFile.objects.filter(sha1=new_sha1)
                                .exclude(id=file_obj.id)
                                .exists()
                            ):
                                errors.append(
                                    f"SHA1 conflict: File ID {file_obj.id} would create duplicate "
                                    f"hash {new_sha1} (from {old_sha1})"
                                )
                                continue

                            file_obj.sha1 = new_sha1
                            updated = True

                        # Handle SHA512
                        if file_obj.sha512 and file_obj.sha512.endswith("="):
                            old_sha512 = file_obj.sha512
                            new_sha512 = old_sha512.rstrip("=")

                            # Check for SHA512 conflicts
                            if (
                                IndexedFile.objects.filter(sha512=new_sha512)
                                .exclude(id=file_obj.id)
                                .exists()
                            ):
                                errors.append(
                                    f"SHA512 conflict: File ID {file_obj.id} would create duplicate "
                                    f"hash {new_sha512} (from {old_sha512})"
                                )
                                continue

                            file_obj.sha512 = new_sha512
                            updated = True

                        if updated:
                            file_obj.save(update_fields=["sha1", "sha512"])
                            updated_count += 1

                    except Exception as e:
                        errors.append(f"Failed to update file ID {file_obj.id}: {e}")

        except Exception as e:
            errors.append(f"Batch transaction failed: {e}")

        return updated_count, errors
