"""Tests for the migrate_fileindex_structure management command."""

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from fileindex.models import IndexedFile

# Test constants for required metadata
TEST_IMAGE_METADATA = {"width": 100, "height": 100}


class MigrateFileindexStructureTestCase(TestCase):
    """Test the migration command for fileindex structure."""

    def setUp(self):
        """Set up test environment with temporary media root."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_media_root = Path(self.temp_dir.name)

        # Create old structure directories
        self.old_fileindex_root = self.temp_media_root / "fileindex"
        self.old_fileindex_root.mkdir(parents=True)

    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def create_test_file_old_structure(self, sha512, extension=".jpg"):
        """Create a test file in the old 2-level structure with padding and
        extension."""
        # Old structure: fileindex/XX/HASH=.ext
        first_two = sha512[:2]
        old_dir = self.old_fileindex_root / first_two
        old_dir.mkdir(parents=True, exist_ok=True)

        # Add padding if not present
        if not sha512.endswith("="):
            sha512_with_padding = sha512 + "="
        else:
            sha512_with_padding = sha512

        old_filename = sha512_with_padding + extension
        old_path = old_dir / old_filename
        old_path.write_text("test content")

        # Create IndexedFile record
        relative_path = f"fileindex/{first_two}/{old_filename}"
        indexed_file = IndexedFile.objects.create(
            sha512=sha512_with_padding.rstrip("="),  # Store without padding in DB
            sha1="test_sha1_" + sha512[:10],
            mime_type="image/jpeg" if extension == ".jpg" else "image/png",
            size=100,
            first_seen="2024-01-01T00:00:00Z",
            metadata=TEST_IMAGE_METADATA,  # Required for image files
        )
        indexed_file.file.name = relative_path
        indexed_file.save()

        return indexed_file, old_path

    def create_test_file_new_structure(self, sha512):
        """Create a test file in the new 3-level structure without padding or
        extension."""
        # New structure: fileindex/XX/YY/HASH (no padding, no extension)
        sha512_no_padding = sha512.rstrip("=")
        first_two = sha512_no_padding[:2]
        second_two = sha512_no_padding[2:4]

        new_dir = self.old_fileindex_root / first_two / second_two
        new_dir.mkdir(parents=True, exist_ok=True)

        new_path = new_dir / sha512_no_padding
        new_path.write_text("test content")

        # Create IndexedFile record
        relative_path = f"fileindex/{first_two}/{second_two}/{sha512_no_padding}"
        indexed_file = IndexedFile.objects.create(
            sha512=sha512_no_padding,
            sha1="test_sha1_" + sha512[:10],
            mime_type="image/jpeg",
            size=100,
            first_seen="2024-01-01T00:00:00Z",
            metadata=TEST_IMAGE_METADATA,  # Required for image files
        )
        indexed_file.file.name = relative_path
        indexed_file.save()

        return indexed_file, new_path

    def test_is_migrated_detection(self):
        """Test that the command correctly detects migrated vs unmigrated files."""
        # Create files in both structures
        old_file, _ = self.create_test_file_old_structure("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" * 3 + "ABCD")
        new_file, _ = self.create_test_file_new_structure("ZYXWVUTSRQPONMLKJIHGFEDCBA765432" * 3 + "ZYXW")

        # Import and instantiate the command
        from fileindex.management.commands.migrate_fileindex_structure import Command

        cmd = Command()
        cmd.media_root = self.temp_media_root

        # Test detection
        self.assertFalse(cmd.is_migrated(old_file), "Old structure file detected as migrated")
        self.assertTrue(cmd.is_migrated(new_file), "New structure file not detected as migrated")

    def test_calculate_new_path(self):
        """Test that new paths are calculated correctly."""
        indexed_file, _ = self.create_test_file_old_structure("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" * 3 + "ABCD")

        from fileindex.management.commands.migrate_fileindex_structure import Command

        cmd = Command()
        new_path = cmd.calculate_new_path(indexed_file)

        # Expected: fileindex/AB/CD/ABCDEFGH...ABCD (no padding, no extension)
        expected = Path("fileindex") / "AB" / "CD" / indexed_file.sha512.rstrip("=")
        self.assertEqual(new_path, expected)

    def test_dry_run_mode(self):
        """Test that dry-run mode doesn't make changes."""
        indexed_file, old_path = self.create_test_file_old_structure("TESTDRYRUNHASH" + "A" * 90)

        out = StringIO()
        with patch("django.conf.settings.MEDIA_ROOT", str(self.temp_media_root)):
            call_command(
                "migrate_fileindex_structure",
                dry_run=True,
                stdout=out,
            )

        # Check file hasn't moved
        self.assertTrue(old_path.exists(), "File was moved in dry-run mode")

        # Check database hasn't changed
        indexed_file.refresh_from_db()
        self.assertIn("=", indexed_file.file.name, "Database updated in dry-run mode")

        # Check output mentions dry run
        output = out.getvalue()
        self.assertIn("DRY RUN", output)
        self.assertIn("Would migrate", output)

    def test_actual_migration(self):
        """Test that files are actually migrated to new structure."""
        # Create multiple test files
        test_hashes = [
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" + "A" * 73,
            "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB" + "B" * 73,
            "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC" + "C" * 73,
        ]

        old_files = []
        for hash_val in test_hashes:
            indexed_file, old_path = self.create_test_file_old_structure(hash_val)
            old_files.append((indexed_file, old_path))

        # Run migration (with automatic yes to prompt)
        out = StringIO()
        with (
            patch("django.conf.settings.MEDIA_ROOT", str(self.temp_media_root)),
            patch("builtins.input", return_value="yes"),
        ):
            call_command(
                "migrate_fileindex_structure",
                stdout=out,
            )

        # Verify each file was migrated
        for indexed_file, old_path in old_files:
            # Old file should be gone
            self.assertFalse(old_path.exists(), f"Old file still exists: {old_path}")

            # Check database was updated
            indexed_file.refresh_from_db()
            new_rel_path = indexed_file.file.name

            # Should have 3-level structure
            self.assertEqual(new_rel_path.count("/"), 3)

            # Should have no padding
            self.assertNotIn("=", new_rel_path)

            # Should have no extension
            self.assertFalse(Path(new_rel_path).suffix)

            # New file should exist
            new_abs_path = self.temp_media_root / new_rel_path
            self.assertTrue(new_abs_path.exists(), f"New file doesn't exist: {new_abs_path}")

            # Content should be preserved
            self.assertEqual(new_abs_path.read_text(), "test content")

    def test_resume_capability(self):
        """Test that migration can resume from where it left off."""
        # Create some files in old structure and some already migrated
        old_hashes = [
            "OLDFILE1" + "A" * 96,
            "OLDFILE2" + "B" * 96,
        ]
        new_hashes = [
            "NEWFILE1" + "C" * 96,
            "NEWFILE2" + "D" * 96,
        ]

        for hash_val in old_hashes:
            self.create_test_file_old_structure(hash_val)

        for hash_val in new_hashes:
            self.create_test_file_new_structure(hash_val)

        out = StringIO()
        with (
            patch("django.conf.settings.MEDIA_ROOT", str(self.temp_media_root)),
            patch("builtins.input", return_value="yes"),
        ):
            call_command(
                "migrate_fileindex_structure",
                stdout=out,
            )

        output = out.getvalue()
        # Should report already migrated files
        self.assertIn("Skipped (already migrated): 2 files", output)
        # Should only migrate the old files
        self.assertIn("Migrated: 2 files", output)

    def test_verify_mode(self):
        """Test that verify mode correctly checks migration status."""
        # Create a properly migrated file
        good_file, _ = self.create_test_file_new_structure("GOODFILE" + "A" * 96)

        # Create a bad file (old structure)
        bad_file, _ = self.create_test_file_old_structure("BADFILE" + "B" * 97)

        out = StringIO()
        with patch("django.conf.settings.MEDIA_ROOT", str(self.temp_media_root)):
            call_command(
                "migrate_fileindex_structure",
                verify=True,
                stdout=out,
            )

        output = out.getvalue()
        self.assertIn("Verifying migration", output)
        # Should find issues with the unmigrated file
        self.assertIn("Found 3 issues", output)  # Padding, extension, and depth issues
        self.assertIn("padding", output.lower())

    def test_migration_directory_structure(self):
        """Test that migration creates correct directory structure."""
        # Create a file and migrate it
        indexed_file, old_path = self.create_test_file_old_structure("DIRTEST" + "A" * 97)

        out = StringIO()
        with (
            patch("django.conf.settings.MEDIA_ROOT", str(self.temp_media_root)),
            patch("builtins.input", return_value="yes"),
        ):
            call_command(
                "migrate_fileindex_structure",
                stdout=out,
            )

        # Verify the migration created the correct structure
        indexed_file.refresh_from_db()
        new_path = self.temp_media_root / indexed_file.file.name

        # Should be in 3-level structure
        parts = Path(indexed_file.file.name).parts
        self.assertEqual(len(parts), 4)  # fileindex/DI/RT/DIRTEST...
        self.assertEqual(parts[0], "fileindex")
        self.assertEqual(parts[1], "DI")  # First 2 chars
        self.assertEqual(parts[2], "RT")  # Next 2 chars

        # File should exist at new location
        self.assertTrue(new_path.exists(), "File wasn't migrated")
        self.assertFalse(old_path.exists(), "Old file still exists")

    def test_batch_processing(self):
        """Test that batch processing works correctly."""
        # Create more files than batch size
        num_files = 5
        for i in range(num_files):
            hash_val = f"BATCH{i:04d}" + "X" * 95
            self.create_test_file_old_structure(hash_val)

        out = StringIO()
        with (
            patch("django.conf.settings.MEDIA_ROOT", str(self.temp_media_root)),
            patch("builtins.input", return_value="yes"),
        ):
            call_command(
                "migrate_fileindex_structure",
                batch_size=2,  # Small batch size for testing
                stdout=out,
            )

        # All files should be migrated
        for indexed_file in IndexedFile.objects.all():
            self.assertEqual(indexed_file.file.name.count("/"), 3)
            self.assertNotIn("=", indexed_file.file.name)
            self.assertFalse(Path(indexed_file.file.name).suffix)

    def test_missing_file_handling(self):
        """Test handling of files that exist in DB but not on disk."""
        # Create IndexedFile without actual file
        indexed_file = IndexedFile.objects.create(
            sha512="MISSINGFILE" + "A" * 93,
            sha1="test_sha1",
            mime_type="image/jpeg",
            size=100,
            first_seen="2024-01-01T00:00:00Z",
            metadata=TEST_IMAGE_METADATA,  # Required for image files
        )
        indexed_file.file.name = "fileindex/MI/MISSINGFILE" + "A" * 93 + "=.jpg"
        indexed_file.save()

        out = StringIO()
        with patch("django.conf.settings.MEDIA_ROOT", str(self.temp_media_root)):
            call_command(
                "migrate_fileindex_structure",
                stdout=out,
            )

        output = out.getvalue()
        self.assertIn("File not found", output)
        # With the new approach, we don't say "No files to migrate" if there
        # are files in DB
        self.assertIn("Migrated: 0 files", output)
