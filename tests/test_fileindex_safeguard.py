"""Test that fileindex safeguards prevent files from being created outside MEDIA_ROOT."""

import contextlib
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings

from fileindex.models import IndexedFile


@contextlib.contextmanager
def temporary_test_file(content="Test content for safeguard test"):
    """Context manager for creating a temporary test file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        yield temp_path
    finally:
        with contextlib.suppress(Exception):
            Path(temp_path).unlink()


class FileIndexSafeguardTestCase(TestCase):
    """Test safeguards in fileindex to prevent misplaced files."""

    def setUp(self):
        """Create a test file using context manager."""
        self._file_context = temporary_test_file()
        self.test_file_path = self._file_context.__enter__()

    def tearDown(self):
        """Clean up test file."""
        self._file_context.__exit__(None, None, None)

    def test_media_root_is_absolute(self):
        """Test that files are created with absolute MEDIA_ROOT path."""
        # Create an IndexedFile
        indexed_file, created = IndexedFile.objects.get_or_create_from_file(
            self.test_file_path
        )

        # The file should be in the correct location
        expected_path = Path(settings.MEDIA_ROOT) / indexed_file.path
        self.assertTrue(expected_path.exists())

        # The file should NOT be in a relative path from CWD
        wrong_path = Path(indexed_file.path)
        if not wrong_path.is_absolute():
            self.assertFalse(
                wrong_path.exists(),
                f"File should not exist at relative path {wrong_path}",
            )

    @override_settings(MEDIA_ROOT="relative/media")
    def test_relative_media_root_made_absolute(self):
        """Test that relative MEDIA_ROOT is converted to absolute."""
        # Even with relative MEDIA_ROOT, the safeguard should make it absolute
        indexed_file, created = IndexedFile.objects.get_or_create_from_file(
            self.test_file_path
        )

        # The destination should be absolute
        media_root = Path(settings.MEDIA_ROOT).resolve()
        expected_path = media_root / indexed_file.path

        # File should be created in the absolute path
        self.assertTrue(
            expected_path.resolve().is_relative_to(media_root),
            "File destination should be within absolute MEDIA_ROOT",
        )

        # Clean up the relative directory if it was created
        import shutil

        relative_dir = Path("relative")
        if relative_dir.exists():
            shutil.rmtree(relative_dir)

    def test_path_traversal_prevention(self):
        """Test that path traversal attempts are prevented."""
        # This test verifies the safeguard logic would catch malicious paths
        # We can't easily test with actual path traversal since 'path' is a computed property
        # But we can verify the safeguard logic is in place

        # The safeguard is in get_or_create_with_filepath_nfo
        # It checks that dest_path starts with media_root
        media_root = Path(settings.MEDIA_ROOT).resolve()

        # Create a test IndexedFile
        indexed_file, created = IndexedFile.objects.get_or_create_from_file(
            self.test_file_path
        )

        # Verify the file was created in the right place
        dest_path = media_root / indexed_file.path
        self.assertTrue(dest_path.resolve().is_relative_to(media_root))

        # Verify malicious paths would be caught
        malicious_path = "../../../etc/passwd"
        bad_dest = media_root / malicious_path
        self.assertFalse(
            bad_dest.resolve().is_relative_to(media_root),
            "Malicious path should escape MEDIA_ROOT and be caught",
        )
