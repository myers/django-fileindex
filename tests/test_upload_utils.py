"""
Tests for upload utility functions.
"""

import io
import tempfile
from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import (
    SimpleUploadedFile,
    TemporaryUploadedFile,
)
from PIL import Image

from fileindex.factories import IndexedFileFactory
from fileindex.upload_utils import (
    cleanup_failed_upload,
    create_indexed_file_from_upload,
    create_indexed_files_batch,
    get_upload_path_for_model,
    validate_image_upload,
)


@pytest.fixture
def simple_uploaded_file():
    """Create a simple uploaded file for testing."""
    return SimpleUploadedFile("test.txt", b"test content", content_type="text/plain")


@pytest.fixture
def temp_uploaded_file():
    """Create a temporary uploaded file for testing."""

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    temp.write(b"temporary file content")
    temp.flush()

    file = TemporaryUploadedFile(name="temp_test.txt", content_type="text/plain", size=22, charset="utf-8")
    file.temporary_file_path = Mock(return_value=temp.name)
    return file


@pytest.fixture
def valid_image_file():
    """Create a valid image file for testing."""
    # Create a simple 10x10 red image
    img = Image.new("RGB", (10, 10), color="red")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    return SimpleUploadedFile("test.png", img_bytes.read(), content_type="image/png")


@pytest.mark.django_db
def test_create_indexed_file_from_memory_upload(simple_uploaded_file):
    """Test creating IndexedFile from InMemoryUploadedFile."""

    with patch("fileindex.upload_utils.default_storage") as mock_storage:
        mock_storage.save.return_value = "uploads/temp/test.txt"
        mock_storage.path.return_value = "/tmp/uploads/temp/test.txt"
        mock_storage.exists.return_value = True

        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_indexed_file = IndexedFileFactory.build()
            mock_create.return_value = (mock_indexed_file, True)

            result, created = create_indexed_file_from_upload(simple_uploaded_file)

            assert result == mock_indexed_file
            assert created is True
            mock_storage.save.assert_called_once()
            mock_create.assert_called_once_with("/tmp/uploads/temp/test.txt", derived_from=None, derived_for=None)
            # Verify temp file was cleaned up
            mock_storage.delete.assert_called_once_with("uploads/temp/test.txt")


@pytest.mark.django_db
def test_create_indexed_file_from_temporary_upload(temp_uploaded_file):
    """Test creating IndexedFile from TemporaryUploadedFile."""

    with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
        mock_indexed_file = IndexedFileFactory.build()
        mock_create.return_value = (mock_indexed_file, False)

        result, created = create_indexed_file_from_upload(temp_uploaded_file)

        assert result == mock_indexed_file
        assert created is False
        # Should use the temporary file path directly
        mock_create.assert_called_once_with(
            temp_uploaded_file.temporary_file_path(), derived_from=None, derived_for=None
        )


@pytest.mark.django_db
def test_create_indexed_file_with_derived_from(simple_uploaded_file):
    """Test creating derived IndexedFile."""
    parent_file = IndexedFileFactory.build()

    with patch("fileindex.upload_utils.default_storage") as mock_storage:
        mock_storage.save.return_value = "uploads/temp/test.txt"
        mock_storage.path.return_value = "/tmp/uploads/temp/test.txt"
        mock_storage.exists.return_value = True

        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_indexed_file = IndexedFileFactory.build()
            mock_create.return_value = (mock_indexed_file, True)

            result, created = create_indexed_file_from_upload(
                simple_uploaded_file, derived_from=parent_file, derived_for="thumbnail"
            )

            assert result == mock_indexed_file
            mock_create.assert_called_once_with(
                "/tmp/uploads/temp/test.txt", derived_from=parent_file, derived_for="thumbnail"
            )


@pytest.mark.django_db
def test_create_indexed_file_custom_path_prefix(simple_uploaded_file):
    """Test custom path prefix for uploads."""

    with patch("fileindex.upload_utils.default_storage") as mock_storage:
        mock_storage.save.return_value = "custom/path/test.txt"
        mock_storage.path.return_value = "/tmp/custom/path/test.txt"
        mock_storage.exists.return_value = True

        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_indexed_file = IndexedFileFactory.build()
            mock_create.return_value = (mock_indexed_file, True)

            create_indexed_file_from_upload(simple_uploaded_file, path_prefix="custom/path")

            # Verify custom path was used
            call_args = mock_storage.save.call_args[0][0]
            assert call_args.startswith("custom/path/")


@pytest.mark.django_db
def test_create_indexed_file_cleanup_on_error(simple_uploaded_file):
    """Test cleanup on error with cleanup_on_error=True."""

    with patch("fileindex.upload_utils.default_storage") as mock_storage:
        mock_storage.save.return_value = "uploads/temp/test.txt"
        mock_storage.path.return_value = "/tmp/uploads/temp/test.txt"
        mock_storage.exists.return_value = True

        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_create.side_effect = ValueError("Database error")

            with pytest.raises(ValueError):
                create_indexed_file_from_upload(simple_uploaded_file, cleanup_on_error=True)

            # Verify cleanup was called
            mock_storage.delete.assert_called_once_with("uploads/temp/test.txt")


@pytest.mark.django_db
def test_create_indexed_file_no_cleanup_on_error(simple_uploaded_file):
    """Test no cleanup on error with cleanup_on_error=False."""

    with patch("fileindex.upload_utils.default_storage") as mock_storage:
        mock_storage.save.return_value = "uploads/temp/test.txt"
        mock_storage.path.return_value = "/tmp/uploads/temp/test.txt"
        mock_storage.exists.return_value = True

        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_create.side_effect = ValueError("Database error")

            with pytest.raises(ValueError):
                create_indexed_file_from_upload(simple_uploaded_file, cleanup_on_error=False)

            # Verify cleanup was NOT called
            mock_storage.delete.assert_not_called()


@pytest.mark.django_db
def test_create_indexed_file_raises_on_no_file():
    """Test that ValueError is raised when no file provided."""
    with pytest.raises(ValueError) as excinfo:
        create_indexed_file_from_upload(None)

    assert "No file provided" in str(excinfo.value)


def test_validate_image_upload_accepts_valid(valid_image_file):
    """Test image validation for valid images."""
    # Should not raise any exception
    validate_image_upload(valid_image_file)


def test_validate_image_upload_rejects_invalid():
    """Test image validation rejects invalid formats."""
    invalid_file = SimpleUploadedFile("test.txt", b"not an image", content_type="text/plain")

    with pytest.raises(ValidationError) as excinfo:
        validate_image_upload(invalid_file)

    assert "Invalid image file" in str(excinfo.value)


def test_validate_image_upload_checks_format():
    """Test image format validation."""
    # Create a valid image but say it's the wrong format
    img = Image.new("RGB", (10, 10), color="red")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    png_file = SimpleUploadedFile("test.png", img_bytes.read(), content_type="image/png")

    # Should accept PNG by default
    validate_image_upload(png_file, allowed_formats=["PNG", "JPEG"])

    # Should reject if PNG not in allowed formats
    with pytest.raises(ValidationError) as excinfo:
        validate_image_upload(png_file, allowed_formats=["JPEG", "GIF"])

    assert "Invalid image format" in str(excinfo.value)


def test_validate_image_upload_checks_dimensions():
    """Test image dimension validation."""
    # Create a 100x100 image
    img = Image.new("RGB", (100, 100), color="blue")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    large_image = SimpleUploadedFile("large.png", img_bytes.read(), content_type="image/png")

    # Should accept if within limits
    validate_image_upload(large_image, max_dimensions=(200, 200))

    # Should reject if too large
    with pytest.raises(ValidationError) as excinfo:
        validate_image_upload(large_image, max_dimensions=(50, 50))

    assert "Image dimensions" in str(excinfo.value)


def test_validate_image_upload_checks_min_dimensions():
    """Test minimum image dimension validation."""
    # Create a 10x10 image
    img = Image.new("RGB", (10, 10), color="green")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    small_image = SimpleUploadedFile("small.png", img_bytes.read(), content_type="image/png")

    # Should accept if above minimum
    validate_image_upload(small_image, min_dimensions=(5, 5))

    # Should reject if too small
    with pytest.raises(ValidationError) as excinfo:
        validate_image_upload(small_image, min_dimensions=(50, 50))

    assert "Image dimensions" in str(excinfo.value)


@pytest.mark.django_db
def test_create_indexed_files_batch_atomic():
    """Test atomic batch creation."""
    files = [SimpleUploadedFile(f"test{i}.txt", f"content{i}".encode(), content_type="text/plain") for i in range(3)]

    with patch("fileindex.upload_utils.default_storage") as mock_storage:
        mock_storage.save.side_effect = [f"uploads/temp/test{i}.txt" for i in range(3)]
        mock_storage.path.side_effect = [f"/tmp/uploads/temp/test{i}.txt" for i in range(3)]

        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_files = [IndexedFileFactory.build() for _ in range(3)]
            mock_create.side_effect = [(f, True) for f in mock_files]

            with patch("fileindex.upload_utils.transaction.atomic") as mock_atomic:
                mock_atomic.return_value.__enter__ = Mock()
                mock_atomic.return_value.__exit__ = Mock()

                result = create_indexed_files_batch(files, atomic=True)

                assert len(result) == 3
                assert all(f in mock_files for f in result)
                mock_atomic.assert_called_once()


@pytest.mark.django_db
def test_create_indexed_files_batch_non_atomic():
    """Test non-atomic batch creation."""
    files = [SimpleUploadedFile(f"test{i}.txt", f"content{i}".encode(), content_type="text/plain") for i in range(2)]

    with patch("fileindex.upload_utils.default_storage") as mock_storage:
        mock_storage.save.side_effect = [f"uploads/temp/test{i}.txt" for i in range(2)]
        mock_storage.path.side_effect = [f"/tmp/uploads/temp/test{i}.txt" for i in range(2)]

        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_files = [IndexedFileFactory.build() for _ in range(2)]
            mock_create.side_effect = [(f, True) for f in mock_files]

            with patch("fileindex.upload_utils.transaction.atomic") as mock_atomic:
                result = create_indexed_files_batch(files, atomic=False)

                assert len(result) == 2
                mock_atomic.assert_not_called()


@pytest.mark.django_db
def test_create_indexed_files_batch_empty_list():
    """Test batch creation with empty list."""
    result = create_indexed_files_batch([])
    assert result == []


def test_cleanup_failed_upload_removes_files():
    """Test cleanup of failed uploads."""
    file_path = "uploads/temp/file1.txt"

    with patch("fileindex.upload_utils.default_storage") as mock_storage:
        mock_storage.location = "/media"

        # Test with a non-storage path (regular file)
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.unlink") as mock_unlink:
                result = cleanup_failed_upload(file_path)
                assert result is True
                mock_unlink.assert_called_once()


def test_cleanup_failed_upload_handles_missing_files():
    """Test cleanup handles already missing files gracefully."""
    file_path = "uploads/temp/missing.txt"

    with patch("fileindex.upload_utils.default_storage") as mock_storage:
        mock_storage.location = "/media"

        with patch("pathlib.Path.exists", return_value=False):
            result = cleanup_failed_upload(file_path)
            assert result is False


def test_cleanup_failed_upload_handles_single_path():
    """Test cleanup with single file path."""
    file_path = "/media/uploads/temp/single.txt"

    with patch("fileindex.upload_utils.default_storage") as mock_storage:
        mock_storage.location = "/media"
        mock_storage.exists.return_value = True

        result = cleanup_failed_upload(file_path)

        # Should detect it's a storage path and use storage to delete
        assert result is True
        mock_storage.delete.assert_called_once_with("uploads/temp/single.txt")


def test_get_upload_path_for_model_generates_path():
    """Test path generation for different models."""
    # Mock a model instance
    mock_instance = Mock()
    mock_instance._meta = Mock()
    mock_instance._meta.app_label = "myapp"
    mock_instance._meta.model_name = "testmodel"
    mock_instance.pk = 123

    path = get_upload_path_for_model(mock_instance, "file.txt")

    assert path == "uploads/myapp/testmodel/123/file.txt"


def test_get_upload_path_for_model_with_custom_prefix():
    """Test path generation with custom base path."""
    mock_instance = Mock()
    mock_instance._meta = Mock()
    mock_instance._meta.app_label = "myapp"
    mock_instance._meta.model_name = "mymodel"
    mock_instance.pk = 456

    path = get_upload_path_for_model(mock_instance, "document.pdf", base_path="custom/docs")

    assert path == "custom/docs/myapp/mymodel/456/document.pdf"


def test_get_upload_path_for_model_without_pk():
    """Test path generation for unsaved model (no pk)."""
    mock_instance = Mock()
    mock_instance._meta = Mock()
    mock_instance._meta.app_label = "myapp"
    mock_instance._meta.model_name = "newmodel"
    mock_instance.pk = None

    path = get_upload_path_for_model(mock_instance, "new.txt")

    assert path == "uploads/myapp/newmodel/new/new.txt"
