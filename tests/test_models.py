"""Tests for fileindex models."""

import tempfile
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from fileindex.factories import IndexedFileFactory
from fileindex.models import FilePath, IndexedFile


def test_indexed_file_str():
    """Test IndexedFile string representation."""
    indexed_file = IndexedFileFactory.build(sha512="abcdef1234567890" * 8)
    assert str(indexed_file) == "abcdef1234..."


def test_indexed_file_protected_url():
    """Test IndexedFile protected_url property."""
    indexed_file = IndexedFileFactory.build()
    indexed_file.file.name = "test/path/file.jpg"
    assert indexed_file.protected_url == "/media/test/path/file.jpg"


def test_indexed_file_url():
    """Test IndexedFile url property."""
    indexed_file = IndexedFileFactory.build()
    indexed_file.file.name = "test/path/file.jpg"
    assert indexed_file.url == "/media/test/path/file.jpg"


def test_indexed_file_save_sets_first_seen():
    """Test that saving IndexedFile sets first_seen if not set."""
    indexed_file = IndexedFileFactory.build(first_seen=None)
    indexed_file.first_seen = None

    with patch("fileindex.models.datetime.datetime") as mock_datetime:
        mock_now = Mock()
        mock_datetime.now.return_value = mock_now

        # Mock the parent save method
        with patch("django.db.models.Model.save") as mock_super_save:
            # Call save on the instance
            indexed_file.save()

            # Verify first_seen was set
            assert indexed_file.first_seen == mock_now
            # Verify super save was called
            mock_super_save.assert_called_once()


def test_indexed_file_save_preserves_existing_first_seen():
    """Test that saving IndexedFile preserves existing first_seen."""
    existing_time = timezone.now()
    indexed_file = IndexedFileFactory.build(first_seen=existing_time)

    # Mock the parent save method
    with patch("django.db.models.Model.save"):
        # Call save on the instance
        indexed_file.save()

        # Verify first_seen was not changed
        assert indexed_file.first_seen == existing_time


@pytest.mark.django_db
def test_indexed_file_thumbnail_for_video():
    """Test thumbnail property for video files."""
    # Create an indexed file with video mime type and required metadata
    indexed_file = IndexedFileFactory(
        mime_type="video/mp4",
        metadata={
            "width": 1920,
            "height": 1080,
            "duration": 120000,  # 2 minutes in milliseconds
            "frame_rate": 30.0,
        },
    )

    # Create a thumbnail derived file
    thumbnail = IndexedFileFactory(derived_for="thumbnail", derived_from=indexed_file)

    # Should return the thumbnail
    assert indexed_file.thumbnail == thumbnail


@pytest.mark.django_db
def test_indexed_file_thumbnail_for_non_video():
    """Test thumbnail property for non-video files."""
    # Create an indexed file with image mime type and required metadata
    indexed_file = IndexedFileFactory(
        mime_type="image/jpeg", metadata={"width": 1920, "height": 1080, "thumbhash": "test_thumbhash"}
    )

    # Should return None for non-video files
    assert indexed_file.thumbnail is None


@pytest.mark.django_db
def test_indexed_file_thumbnail_no_thumbnail_exists():
    """Test thumbnail property when no thumbnail exists."""
    # Create a video file without thumbnail
    indexed_file = IndexedFileFactory(
        mime_type="video/mp4", metadata={"width": 1920, "height": 1080, "duration": 120000, "frame_rate": 30.0}
    )

    # Should return None when no thumbnail exists
    assert indexed_file.thumbnail is None


@pytest.mark.django_db
def test_indexed_file_get_or_create_derived_for():
    """Test get_or_create_from_file with derived_for parameter."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(b"test image content")
        tmp.flush()

        # Create a parent file
        IndexedFileFactory()

        # Create derived file with derived_for as string type
        indexed_file, created = IndexedFile.objects.get_or_create_from_file(tmp.name, derived_for="thumbnail")

        assert created is True
        assert indexed_file.derived_for == "thumbnail"


@pytest.mark.django_db
@patch("fileindex.services.metadata_extraction.extract_required_metadata")
def test_indexed_file_get_or_create_with_corrupt_metadata(mock_extract):
    """Test get_or_create_from_file when metadata extraction indicates corruption."""
    # Mock metadata extraction to return corrupt flag
    mock_extract.return_value = ({"test": "metadata"}, True)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(b"test corrupt content")
        tmp.flush()

        indexed_file, created = IndexedFile.objects.get_or_create_from_file(tmp.name)

        assert created is True
        assert indexed_file.corrupt is True


def test_filepath_str():
    """Test FilePath string representation."""
    filepath = FilePath(pk=123, path="/test/path/file.jpg")
    assert str(filepath) == "(123) '/test/path/file.jpg'"


def test_filepath_save_sets_created_at():
    """Test that saving FilePath sets created_at if not set."""
    indexed_file = IndexedFileFactory.build()
    filepath = FilePath(
        indexedfile=indexed_file, mtime=timezone.now(), ctime=timezone.now(), path="/test/path", created_at=None
    )

    with patch("fileindex.models.datetime.datetime") as mock_datetime:
        mock_now = Mock()
        mock_datetime.now.return_value = mock_now

        # Mock the parent save method
        with patch("django.db.models.Model.save"):
            # Call save on the instance
            filepath.save()

            # Verify created_at was set
            assert filepath.created_at == mock_now


def test_filepath_save_preserves_existing_created_at():
    """Test that saving FilePath preserves existing created_at."""
    existing_time = timezone.now()
    indexed_file = IndexedFileFactory.build()
    filepath = FilePath(
        indexedfile=indexed_file,
        mtime=timezone.now(),
        ctime=timezone.now(),
        path="/test/path",
        created_at=existing_time,
    )

    # Mock the parent save method
    with patch("django.db.models.Model.save"):
        # Call save on the instance
        filepath.save()

        # Verify created_at was not changed
        assert filepath.created_at == existing_time


@pytest.mark.django_db
def test_indexed_file_filename_property():
    """Test IndexedFile filename property."""
    # Create an indexed file
    indexed_file = IndexedFileFactory()

    # Create associated FilePath
    FilePath.objects.create(
        indexedfile=indexed_file,
        path="/test/path/myfile.jpg",
        mtime=timezone.now(),
        ctime=timezone.now(),
        created_at=timezone.now(),
    )

    # Should return the filename from the first FilePath
    assert indexed_file.filename == "myfile.jpg"


@pytest.mark.django_db
def test_indexed_file_filename_property_no_filepath():
    """Test IndexedFile filename property when no FilePath exists."""
    # Create an indexed file without FilePath
    indexed_file = IndexedFileFactory()

    # Should raise ValueError when no FilePath exists
    with pytest.raises(ValueError, match="IndexedFile has no associated FilePath"):
        _ = indexed_file.filename


@pytest.mark.django_db
def test_indexed_file_model_fields():
    """Test IndexedFile model field constraints and defaults."""
    indexed_file = IndexedFileFactory()

    # Check required fields are set
    assert indexed_file.sha512 is not None
    assert indexed_file.sha1 is not None
    assert indexed_file.file is not None
    assert indexed_file.size is not None

    # Check boolean defaults
    assert indexed_file.corrupt is None or indexed_file.corrupt is False

    # Check relationship fields
    assert indexed_file.derived_from is None or isinstance(indexed_file.derived_from, IndexedFile)


@pytest.mark.django_db
def test_filepath_unique_constraint():
    """Test FilePath unique_together constraint."""
    indexed_file = IndexedFileFactory()

    # Create first FilePath
    FilePath.objects.create(
        indexedfile=indexed_file,
        path="/test/path.jpg",
        mtime=timezone.now(),
        ctime=timezone.now(),
        created_at=timezone.now(),
    )

    # Try to create duplicate - should raise IntegrityError
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        FilePath.objects.create(
            indexedfile=indexed_file,
            path="/test/path.jpg",  # Same path
            mtime=timezone.now(),
            ctime=timezone.now(),
            created_at=timezone.now(),
        )
