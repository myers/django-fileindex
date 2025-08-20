"""Test that the factory-boy factories work correctly."""

from django.test import TestCase
from PIL import Image

from fileindex.factories import (
    AudioFileFactory,
    FilePathFactory,
    ImageFileFactory,
    IndexedFileFactory,
    VideoFileFactory,
    create_test_image_file,
    temporary_test_file,
)
from fileindex.models import FilePath, IndexedFile


class FactoryTestCase(TestCase):
    """Test that factories create valid objects."""

    def test_indexed_file_factory(self):
        """Test basic IndexedFile factory."""
        indexed_file = IndexedFileFactory()

        self.assertIsInstance(indexed_file, IndexedFile)
        self.assertIsNotNone(indexed_file.size)
        self.assertIsNotNone(indexed_file.sha1)
        self.assertIsNotNone(indexed_file.sha512)
        self.assertEqual(indexed_file.mime_type, "text/plain")
        self.assertIsInstance(indexed_file.metadata, dict)

    def test_image_file_factory(self):
        """Test ImageFileFactory creates proper image metadata."""
        image_file = ImageFileFactory()

        self.assertEqual(image_file.mime_type, "image/png")
        self.assertEqual(image_file.metadata["width"], 200)
        self.assertEqual(image_file.metadata["height"], 150)
        self.assertIn("thumbhash", image_file.metadata)

    def test_video_file_factory(self):
        """Test VideoFileFactory creates proper video metadata."""
        video_file = VideoFileFactory()

        self.assertEqual(video_file.mime_type, "video/mp4")
        self.assertEqual(video_file.metadata["width"], 320)
        self.assertEqual(video_file.metadata["height"], 240)
        self.assertEqual(video_file.metadata["duration"], 5000)
        self.assertEqual(video_file.metadata["frame_rate"], 30.0)

    def test_audio_file_factory(self):
        """Test AudioFileFactory creates proper audio metadata."""
        audio_file = AudioFileFactory()

        self.assertEqual(audio_file.mime_type, "audio/mp3")
        self.assertEqual(audio_file.metadata["duration"], 10000)

    def test_file_path_factory(self):
        """Test FilePathFactory."""
        file_path = FilePathFactory()

        self.assertIsInstance(file_path, FilePath)
        self.assertIsInstance(file_path.indexedfile, IndexedFile)
        self.assertIsNotNone(file_path.path)
        self.assertIsNotNone(file_path.mtime)
        self.assertIsNotNone(file_path.ctime)


class FactoryHelpersTestCase(TestCase):
    """Test helper functions for creating actual files."""

    def test_temporary_test_file(self):
        """Test temporary test file context manager."""
        with temporary_test_file("test content", suffix=".txt") as temp_path:
            # File should exist during context
            from pathlib import Path

            self.assertTrue(Path(temp_path).exists())

            # Should contain our content
            with open(temp_path) as f:
                content = f.read()
            self.assertEqual(content, "test content")

        # File should be cleaned up after context
        self.assertFalse(Path(temp_path).exists())

    def test_create_test_image_file(self):
        """Test image file creation helper."""
        with temporary_test_file("", suffix=".png") as temp_path:
            create_test_image_file(temp_path, width=100, height=50, color="red")

            # Verify image was created correctly
            with Image.open(temp_path) as img:
                self.assertEqual(img.size, (100, 50))
                self.assertEqual(img.mode, "RGB")

    def test_create_from_actual_file(self):
        """Test creating IndexedFile from actual file."""
        with temporary_test_file("test content for indexing") as temp_path:
            indexed_file = IndexedFileFactory.create_from_actual_file(temp_path)

            # Should be created properly with real file analysis
            self.assertIsInstance(indexed_file, IndexedFile)
            self.assertEqual(indexed_file.mime_type, "text/plain")
            self.assertGreater(indexed_file.size, 0)
            # Should have FilePath created
            self.assertEqual(indexed_file.filepath_set.count(), 1)

    def test_image_create_with_actual_file(self):
        """Test creating ImageFile with actual file."""
        image_file = ImageFileFactory.create_with_actual_file(width=300, height=200, color="green")

        # Should have proper image metadata extracted
        self.assertEqual(image_file.mime_type, "image/png")
        self.assertEqual(image_file.metadata["width"], 300)
        self.assertEqual(image_file.metadata["height"], 200)
        self.assertIn("thumbhash", image_file.metadata)
        # Should have FilePath
        self.assertEqual(image_file.filepath_set.count(), 1)
