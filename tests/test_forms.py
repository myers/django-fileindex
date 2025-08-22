"""
Tests for form mixins and utilities.
"""

from unittest.mock import Mock, patch

import pytest
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models

from fileindex.factories import IndexedFileFactory
from fileindex.forms import (
    IndexedFileModelForm,
    IndexedFileUploadMixin,
)


# Test model for form testing (not a test class)
class FileTestModel(models.Model):
    """Model for file upload testing (not a test class)."""

    name = models.CharField(max_length=100)
    indexed_file = models.ForeignKey("fileindex.IndexedFile", on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        app_label = "tests"


@pytest.fixture
def simple_uploaded_file():
    """Create a simple uploaded file for testing."""
    return SimpleUploadedFile("test.txt", b"test content", content_type="text/plain")


@pytest.fixture
def mock_model_instance():
    """Create a test model instance for testing."""
    instance = FileTestModel(name="test")
    instance.indexed_file = None
    instance.save = Mock()
    return instance


@pytest.mark.django_db
def test_indexed_file_upload_mixin_saves_file(simple_uploaded_file, mock_model_instance):
    """Test that mixin properly saves uploaded file as IndexedFile."""

    class TestForm(IndexedFileUploadMixin, forms.ModelForm):
        upload_file = forms.FileField()

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"

    form = TestForm()
    form.instance = mock_model_instance
    form.cleaned_data = {"upload_file": simple_uploaded_file}
    form.save_m2m = Mock()

    # Mock the parent save to return our instance
    with patch.object(forms.ModelForm, "save", return_value=mock_model_instance):
        with patch("fileindex.forms.default_storage") as mock_storage:
            mock_storage.save.return_value = "uploads/temp/test.txt"
            mock_storage.path.return_value = "/tmp/uploads/temp/test.txt"
            mock_storage.exists.return_value = True

            with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
                mock_indexed_file = IndexedFileFactory.build()
                mock_create.return_value = (mock_indexed_file, True)

                result = form.save(commit=True)

                assert result == mock_model_instance
                assert mock_model_instance.indexed_file == mock_indexed_file
                mock_model_instance.save.assert_called_once()
                form.save_m2m.assert_called_once()


@pytest.mark.django_db
def test_indexed_file_upload_mixin_handles_no_file(mock_model_instance):
    """Test form save without file upload."""

    class TestForm(IndexedFileUploadMixin, forms.ModelForm):
        upload_file = forms.FileField(required=False)

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"

    form = TestForm()
    form.instance = mock_model_instance
    form.cleaned_data = {"upload_file": None}
    form.save_m2m = Mock()

    with patch.object(forms.ModelForm, "save", return_value=mock_model_instance):
        result = form.save(commit=True)

        assert result == mock_model_instance
        assert mock_model_instance.indexed_file is None
        mock_model_instance.save.assert_called_once()


@pytest.mark.django_db
def test_indexed_file_upload_mixin_no_commit(simple_uploaded_file, mock_model_instance):
    """Test form save with commit=False."""

    class TestForm(IndexedFileUploadMixin, forms.ModelForm):
        upload_file = forms.FileField()

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"

    form = TestForm()
    form.instance = mock_model_instance
    form.cleaned_data = {"upload_file": simple_uploaded_file}
    form.save_m2m = Mock()

    with patch.object(forms.ModelForm, "save", return_value=mock_model_instance):
        with patch("fileindex.forms.default_storage") as mock_storage:
            mock_storage.save.return_value = "uploads/temp/test.txt"
            mock_storage.path.return_value = "/tmp/uploads/temp/test.txt"
            mock_storage.exists.return_value = True

            with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
                mock_indexed_file = IndexedFileFactory.build()
                mock_create.return_value = (mock_indexed_file, True)

                result = form.save(commit=False)

                assert result == mock_model_instance
                assert mock_model_instance.indexed_file == mock_indexed_file
                mock_model_instance.save.assert_not_called()
                form.save_m2m.assert_not_called()


@pytest.mark.django_db
def test_indexed_file_upload_mixin_custom_path_prefix(simple_uploaded_file, mock_model_instance):
    """Test custom upload path prefix."""

    class TestForm(IndexedFileUploadMixin, forms.ModelForm):
        upload_file = forms.FileField()

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"
        upload_path_prefix = "custom/uploads"

    form = TestForm()
    form.instance = mock_model_instance
    form.cleaned_data = {"upload_file": simple_uploaded_file}
    form.save_m2m = Mock()

    with patch.object(forms.ModelForm, "save", return_value=mock_model_instance):
        with patch("fileindex.forms.default_storage") as mock_storage:
            mock_storage.save.return_value = "custom/uploads/test.txt"
            mock_storage.path.return_value = "/tmp/custom/uploads/test.txt"
            mock_storage.exists.return_value = True

            with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
                mock_indexed_file = IndexedFileFactory.build()
                mock_create.return_value = (mock_indexed_file, True)

                form.save(commit=True)

                # Verify custom path was used
                call_args = mock_storage.save.call_args[0][0]
                assert call_args.startswith("custom/uploads/")


@pytest.mark.django_db
def test_indexed_file_upload_mixin_cleanup_on_error(simple_uploaded_file, mock_model_instance):
    """Test that temporary file is cleaned up on error."""

    class TestForm(IndexedFileUploadMixin, forms.ModelForm):
        upload_file = forms.FileField()

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"

    form = TestForm()
    form.instance = mock_model_instance
    form.cleaned_data = {"upload_file": simple_uploaded_file}

    with patch.object(forms.ModelForm, "save", return_value=mock_model_instance):
        with patch("fileindex.forms.default_storage") as mock_storage:
            mock_storage.save.return_value = "uploads/temp/test.txt"
            mock_storage.path.return_value = "/tmp/uploads/temp/test.txt"
            mock_storage.exists.return_value = True

            with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
                mock_create.side_effect = ValueError("Database error")

                with pytest.raises(ValueError):
                    form.save(commit=True)

                # Verify cleanup was called
                mock_storage.delete.assert_called_once_with("uploads/temp/test.txt")


@pytest.mark.django_db
def test_indexed_file_upload_mixin_adds_field_automatically():
    """Test that mixin adds upload field if not present."""

    class TestForm(IndexedFileUploadMixin, forms.ModelForm):
        # No upload_file field defined

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"

    form = TestForm()

    # Check that the field was added
    assert "upload_file" in form.fields
    assert isinstance(form.fields["upload_file"], forms.FileField)
    assert form.fields["upload_file"].required is False


@pytest.mark.django_db
def test_indexed_file_model_form_integration():
    """Test ModelForm integration."""

    class TestModelForm(IndexedFileModelForm):
        upload_file = forms.FileField()

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"

    form = TestModelForm()

    # Verify it inherits from both mixins
    assert hasattr(form, "_create_indexed_file")  # From IndexedFileUploadMixin
    assert hasattr(form, "upload_path_prefix")  # From IndexedFileUploadMixin

    # Test that it can be instantiated and has the upload field
    assert "upload_file" in form.fields


@pytest.mark.django_db
def test_indexed_file_upload_mixin_handles_indexed_file_instance(mock_model_instance):
    """Test that mixin handles IndexedFile instance correctly (formset scenario)."""

    class TestForm(IndexedFileUploadMixin, forms.ModelForm):
        upload_file = forms.FileField(required=False)

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"

    form = TestForm()
    form.instance = mock_model_instance

    # Create an IndexedFile instance (simulating what Django admin formsets might pass)
    existing_indexed_file = IndexedFileFactory.build()
    existing_indexed_file.id = 123
    existing_indexed_file.sha512 = "abc123" * 20  # Simulate a hash

    # Set the IndexedFile instance as the "uploaded file" value
    form.cleaned_data = {"upload_file": existing_indexed_file}
    form.save_m2m = Mock()

    with patch.object(forms.ModelForm, "save", return_value=mock_model_instance):
        result = form.save(commit=True)

        # Should use the existing IndexedFile directly without trying to process it
        assert result == mock_model_instance
        assert mock_model_instance.indexed_file == existing_indexed_file
        mock_model_instance.save.assert_called_once()
