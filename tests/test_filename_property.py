"""Test IndexedFile.filename property error handling."""

import contextlib
import tempfile
from pathlib import Path

from django.test import TestCase

from fileindex.models import IndexedFile


class IndexedFileFilenameTestCase(TestCase):
    """Test that IndexedFile.filename property handles missing FilePath correctly."""

    def test_filename_property_with_no_filepath(self):
        """Test that accessing filename without FilePath raises proper exception."""
        # Create an IndexedFile without using get_or_create_from_file
        # This simulates a corrupt state where IndexedFile exists but has no FilePath
        indexed_file = IndexedFile.objects.create(
            size=100,
            sha1="test_sha1",
            sha512="test_sha512_unique_" + str(id(self)),  # Ensure unique
            mime_type="text/plain",
            first_seen="2024-01-01T00:00:00Z",
        )

        # Accessing filename should raise ValueError, not AssertionError
        with self.assertRaises(ValueError) as context:
            _ = indexed_file.filename

        self.assertIn("IndexedFile has no associated FilePath", str(context.exception))

    def test_filename_property_with_filepath(self):
        """Test that filename property works correctly with FilePath."""
        # Create a temporary test file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test content")
            temp_path = f.name

        try:
            # Create IndexedFile properly with FilePath
            indexed_file, _ = IndexedFile.objects.get_or_create_from_file(temp_path)

            # Filename should work without error
            filename = indexed_file.filename
            self.assertTrue(filename.endswith(".txt"))
            self.assertIsInstance(filename, str)

        finally:
            # Clean up
            with contextlib.suppress(Exception):
                Path(temp_path).unlink()
