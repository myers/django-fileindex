"""
Tests for custom Django form fields.
"""

from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from fileindex.factories import IndexedFileFactory
from fileindex.fields import IndexedFileField


@pytest.fixture
def simple_uploaded_file():
    """Create a simple uploaded file for testing."""
    return SimpleUploadedFile("test.txt", b"test content", content_type="text/plain")


@pytest.fixture
def image_uploaded_file():
    """Create a simple image file for testing."""
    # 1x1 red pixel PNG
    png_data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf"
        b"\xc0\x00\x00\x00\x03\x00\x01\x9e\xf6\xf0\x8c\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return SimpleUploadedFile("test.png", png_data, content_type="image/png")


@pytest.mark.django_db
def test_indexed_file_field_creates_indexed_file(simple_uploaded_file):
    """Test that IndexedFileField creates an IndexedFile from upload."""
    field = IndexedFileField()

    with patch("fileindex.fields.default_storage") as mock_storage:
        # Mock storage operations
        mock_storage.save.return_value = "uploads/temp/test.txt"
        mock_storage.path.return_value = "/tmp/uploads/temp/test.txt"
        mock_storage.exists.return_value = True

        # Mock IndexedFile creation
        mock_indexed_file = IndexedFileFactory.build()
        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_create.return_value = (mock_indexed_file, True)

            result = field.clean(simple_uploaded_file)

            assert result == mock_indexed_file
            mock_storage.save.assert_called_once()
            mock_create.assert_called_once_with("/tmp/uploads/temp/test.txt")
            mock_storage.delete.assert_called_once_with("uploads/temp/test.txt")


@pytest.mark.django_db
def test_indexed_file_field_validates_extensions(simple_uploaded_file):
    """Test file extension validation."""
    field = IndexedFileField(allowed_extensions=[".pdf", ".doc"])

    with pytest.raises(ValidationError) as excinfo:
        field.clean(simple_uploaded_file)

    assert "File type not allowed" in str(excinfo.value)
    assert ".pdf" in str(excinfo.value)


@pytest.mark.django_db
def test_indexed_file_field_validates_file_size():
    """Test file size limit validation."""
    field = IndexedFileField(max_file_size=5)  # 5 bytes max

    large_file = SimpleUploadedFile(
        "large.txt", b"This is much more than 5 bytes of content", content_type="text/plain"
    )

    with pytest.raises(ValidationError) as excinfo:
        field.clean(large_file)

    assert "exceeds maximum allowed size" in str(excinfo.value)


@pytest.mark.django_db
def test_indexed_file_field_cleans_up_on_error(simple_uploaded_file):
    """Test temporary file cleanup on errors."""
    field = IndexedFileField()

    with patch("fileindex.fields.default_storage") as mock_storage:
        mock_storage.save.return_value = "uploads/temp/test.txt"
        mock_storage.path.return_value = "/tmp/uploads/temp/test.txt"
        mock_storage.exists.return_value = True

        # Mock IndexedFile creation to fail
        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_create.side_effect = Exception("Database error")

            with pytest.raises(ValidationError) as excinfo:
                field.clean(simple_uploaded_file)

            # Verify cleanup was called
            mock_storage.delete.assert_called_once_with("uploads/temp/test.txt")
            assert "Failed to process file" in str(excinfo.value)


@pytest.mark.django_db
def test_indexed_file_field_returns_none_for_no_file():
    """Test that field returns None when no file is provided."""
    field = IndexedFileField(required=False)

    result = field.clean(None)
    assert result is None


@pytest.mark.django_db
def test_indexed_file_field_with_custom_path_prefix(simple_uploaded_file):
    """Test custom path prefix for temporary files."""
    field = IndexedFileField(path_prefix="custom/path")

    with patch("fileindex.fields.default_storage") as mock_storage:
        mock_storage.save.return_value = "custom/path/test.txt"
        mock_storage.path.return_value = "/tmp/custom/path/test.txt"
        mock_storage.exists.return_value = True

        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_indexed_file = IndexedFileFactory.build()
            mock_create.return_value = (mock_indexed_file, True)

            field.clean(simple_uploaded_file)

            # Verify the custom path was used
            mock_storage.save.assert_called_once()
            call_args = mock_storage.save.call_args[0][0]
            assert call_args.startswith("custom/path/")
