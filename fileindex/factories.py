"""Factory definitions for fileindex models."""

import contextlib
import datetime
import tempfile
from pathlib import Path

import factory
from factory.django import DjangoModelFactory
from PIL import Image

from fileindex.models import FilePath, IndexedFile


@contextlib.contextmanager
def temporary_test_file(content="Test content", suffix=".txt"):
    """Context manager for creating temporary test files."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        yield temp_path
    finally:
        with contextlib.suppress(Exception):
            Path(temp_path).unlink()


def create_test_image_file(filepath, width=200, height=150, color="blue"):
    """Create a test image file at the given path."""
    img = Image.new("RGB", (width, height), color=color)
    img.save(filepath, "PNG")
    return filepath


class IndexedFileFactory(DjangoModelFactory):
    """Factory for IndexedFile model.

    Note: This creates the database record but doesn't create actual files.
    For tests that need actual files, use create_from_actual_file().

    Usage examples:
        # Create a basic IndexedFile record
        indexed_file = IndexedFileFactory()

        # Create from an actual file on disk
        indexed_file = IndexedFileFactory.create_from_actual_file("/path/to/file.txt")

        # Create with custom attributes
        indexed_file = IndexedFileFactory(mime_type="text/plain", size=500)
    """

    class Meta:
        model = IndexedFile

    size = factory.Faker("random_int", min=100, max=10000)
    sha1 = factory.Sequence(lambda n: f"TESTSTHA1HASH{n:020d}")
    sha512 = factory.Sequence(lambda n: f"TESTSHA512HASH{n:050d}")
    mime_type = "text/plain"
    first_seen = factory.Faker("date_time_this_year", tzinfo=datetime.UTC)
    corrupt = None
    metadata = factory.Dict({})

    @classmethod
    def create_from_actual_file(cls, file_path, **kwargs):
        """Create IndexedFile from an actual file using the normal creation process."""
        indexed_file, created = IndexedFile.objects.get_or_create_from_file(file_path)

        # Update any provided attributes
        for key, value in kwargs.items():
            if hasattr(indexed_file, key):
                setattr(indexed_file, key, value)

        if kwargs:
            indexed_file.save()

        return indexed_file


class ImageFileFactory(IndexedFileFactory):
    """Factory for image IndexedFile with proper metadata."""

    mime_type = "image/png"
    metadata = factory.Dict(
        {
            "image": factory.Dict(
                {
                    "width": 200,
                    "height": 150,
                    "thumbhash": factory.Faker("hexify", text="a" * 32),
                    "animated": False,
                }
            ),
        }
    )

    @classmethod
    def create_with_actual_file(cls, width=200, height=150, color="blue", **kwargs):
        """Create ImageFile with actual file on disk.

        Args:
            width: Image width in pixels (default: 200)
            height: Image height in pixels (default: 150)
            color: Image background color (default: "blue")
            **kwargs: Additional attributes to set on the IndexedFile

        Returns:
            IndexedFile instance with proper image metadata extracted

        Usage:
            # Create a test image with default settings
            image = ImageFileFactory.create_with_actual_file()

            # Create a custom sized image
            image = ImageFileFactory.create_with_actual_file(
                width=800, height=600, color="red"
            )
        """
        with temporary_test_file("", suffix=".png") as temp_path:
            create_test_image_file(temp_path, width, height, color)
            return cls.create_from_actual_file(temp_path, **kwargs)


class VideoFileFactory(IndexedFileFactory):
    """Factory for video IndexedFile."""

    mime_type = "video/mp4"
    metadata = factory.Dict(
        {
            "video": factory.Dict(
                {
                    "width": 320,
                    "height": 240,
                    "frame_rate": 30.0,
                }
            ),
            "duration": 5000,  # 5 seconds in milliseconds
        }
    )


class AudioFileFactory(IndexedFileFactory):
    """Factory for audio IndexedFile."""

    mime_type = "audio/mp3"
    metadata = factory.Dict(
        {
            "duration": 10000,  # 10 seconds in milliseconds
        }
    )


class FilePathFactory(DjangoModelFactory):
    """Factory for FilePath model."""

    class Meta:
        model = FilePath

    indexedfile = factory.SubFactory(IndexedFileFactory)
    mtime = factory.Faker("date_time_this_year", tzinfo=datetime.UTC)
    ctime = factory.Faker("date_time_this_year", tzinfo=datetime.UTC)
    hostname = factory.Faker("domain_name")
    path = factory.Faker("file_path", depth=3)
    created_at = factory.Faker("date_time_this_year", tzinfo=datetime.UTC)
