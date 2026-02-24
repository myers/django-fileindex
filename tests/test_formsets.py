"""
Tests for Django formsets with IndexedFile fields.

These tests ensure that the IndexedFileUploadMixin works correctly with Django admin
inline formsets, which can pass IndexedFile instances instead of uploaded files.
"""

from unittest.mock import Mock, patch

import pytest
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile

from fileindex.factories import IndexedFileFactory
from fileindex.forms import IndexedFileUploadMixin
from tests.test_forms import FileTestModel


@pytest.mark.django_db
def test_inline_formset_with_new_file_upload():
    """Test form handling in formset context with new file uploads."""

    class TestForm(IndexedFileUploadMixin, forms.ModelForm):
        upload_file = forms.FileField(required=False)

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"

    # Create a mock instance
    mock_instance = FileTestModel(name="test")
    mock_instance.save = Mock()

    # Simulate form data with file upload
    test_file = SimpleUploadedFile("test.txt", b"test content", content_type="text/plain")

    form = TestForm()
    form.instance = mock_instance
    form.cleaned_data = {
        "upload_file": test_file,
        "name": "Test name",
    }
    form.save_m2m = Mock()

    with patch("fileindex.forms.default_storage") as mock_storage:
        mock_storage.save.return_value = "uploads/temp/test.txt"
        mock_storage.path.return_value = "/tmp/uploads/temp/test.txt"
        mock_storage.exists.return_value = True

        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_indexed_file = IndexedFileFactory.build()
            mock_create.return_value = (mock_indexed_file, True)

            with patch.object(forms.ModelForm, "save", return_value=mock_instance):
                # Save the form
                result = form.save(commit=True)

                # Verify IndexedFile was created and assigned
                assert result.indexed_file == mock_indexed_file
                mock_instance.save.assert_called_once()


@pytest.mark.django_db
def test_inline_formset_with_existing_indexed_file():
    """Test form handling when IndexedFile instance is passed instead of file."""

    class TestForm(IndexedFileUploadMixin, forms.ModelForm):
        upload_file = forms.FileField(required=False)

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"

    # Create an existing IndexedFile instance
    existing_indexed_file = IndexedFileFactory.build()
    existing_indexed_file.id = 456
    existing_indexed_file.sha512 = "def456" * 20

    # Create a mock instance
    mock_instance = FileTestModel(name="test")
    mock_instance.save = Mock()

    form = TestForm()
    form.instance = mock_instance
    form.cleaned_data = {
        "upload_file": existing_indexed_file,  # Pass IndexedFile instance instead of file
        "name": "Updated name",
    }
    form.save_m2m = Mock()

    with patch.object(forms.ModelForm, "save", return_value=mock_instance):
        # Save the form - should handle IndexedFile instance without error
        result = form.save(commit=True)

        # Should use the existing IndexedFile directly
        assert result.indexed_file == existing_indexed_file
        mock_instance.save.assert_called_once()


@pytest.mark.django_db
def test_inline_formset_mixed_scenarios():
    """Test handling both new uploads and existing IndexedFiles."""

    class TestForm(IndexedFileUploadMixin, forms.ModelForm):
        upload_file = forms.FileField(required=False)

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"

    # Test 1: New file upload
    test_file = SimpleUploadedFile("new.txt", b"new content", content_type="text/plain")
    mock_instance1 = FileTestModel(name="test1")
    mock_instance1.save = Mock()

    form1 = TestForm()
    form1.instance = mock_instance1
    form1.cleaned_data = {"upload_file": test_file, "name": "New"}
    form1.save_m2m = Mock()

    # Test 2: Existing IndexedFile instance
    existing_file = IndexedFileFactory.build()
    existing_file.id = 999
    mock_instance2 = FileTestModel(name="test2")
    mock_instance2.save = Mock()

    form2 = TestForm()
    form2.instance = mock_instance2
    form2.cleaned_data = {"upload_file": existing_file, "name": "Existing"}
    form2.save_m2m = Mock()

    with patch("fileindex.forms.default_storage") as mock_storage:
        mock_storage.save.return_value = "uploads/temp/new.txt"
        mock_storage.path.return_value = "/tmp/uploads/temp/new.txt"
        mock_storage.exists.return_value = True

        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            new_indexed_file = IndexedFileFactory.build()
            mock_create.return_value = (new_indexed_file, True)

            with patch.object(forms.ModelForm, "save", return_value=mock_instance1):
                result1 = form1.save(commit=True)

            with patch.object(forms.ModelForm, "save", return_value=mock_instance2):
                result2 = form2.save(commit=True)

            # First form should create new IndexedFile
            assert result1.indexed_file == new_indexed_file

            # Second form should use existing IndexedFile
            assert result2.indexed_file == existing_file

            # Both should save successfully
            mock_instance1.save.assert_called_once()
            mock_instance2.save.assert_called_once()


@pytest.mark.django_db
def test_formset_with_none_values():
    """Test form handling None values in upload fields."""

    class TestForm(IndexedFileUploadMixin, forms.ModelForm):
        upload_file = forms.FileField(required=False)

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"

    mock_instance = FileTestModel(name="test")
    mock_instance.save = Mock()

    form = TestForm()
    form.instance = mock_instance
    form.cleaned_data = {"upload_file": None, "name": "No file"}
    form.save_m2m = Mock()

    with patch.object(forms.ModelForm, "save", return_value=mock_instance):
        result = form.save(commit=True)

        # Should handle None gracefully
        assert result.indexed_file is None
        mock_instance.save.assert_called_once()


@pytest.mark.django_db
def test_formset_error_handling():
    """Test error handling when processing files."""

    class TestForm(IndexedFileUploadMixin, forms.ModelForm):
        upload_file = forms.FileField(required=False)

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"

    test_file = SimpleUploadedFile("error.txt", b"error content", content_type="text/plain")
    mock_instance = FileTestModel(name="test")

    form = TestForm()
    form.instance = mock_instance
    form.cleaned_data = {"upload_file": test_file, "name": "Will fail"}
    form.save_m2m = Mock()

    with patch("fileindex.forms.default_storage") as mock_storage:
        mock_storage.save.return_value = "uploads/temp/error.txt"
        mock_storage.path.return_value = "/tmp/uploads/temp/error.txt"
        mock_storage.exists.return_value = True

        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_create.side_effect = ValueError("Database error")

            with patch.object(forms.ModelForm, "save", return_value=mock_instance):
                with pytest.raises(ValueError):
                    form.save(commit=True)

                # Should clean up temporary file
                mock_storage.delete.assert_called_with("uploads/temp/error.txt")


@pytest.mark.django_db
def test_formset_scenario_reproduces_original_error():
    """Test that reproduces the original AttributeError: 'IndexedFile' object has no attribute 'name'."""

    # First, demonstrate the original error would occur without the fix
    class BrokenMixin:
        """Mixin without the fix - will try to access .name on IndexedFile."""

        upload_field_name = "upload_file"
        indexed_file_field_name = "indexed_file"
        upload_path_prefix = "uploads/temp"

        def save(self, commit=True):
            instance = super().save(commit=False)
            uploaded_file = self.cleaned_data.get(self.upload_field_name)
            if uploaded_file:
                # This will fail if uploaded_file is an IndexedFile instance
                # simulating the original bug
                try:
                    _ = uploaded_file.name  # Will raise AttributeError
                except AttributeError as e:
                    # The original error that would occur
                    raise AttributeError("'IndexedFile' object has no attribute 'name'") from e
            return instance

    class BrokenForm(BrokenMixin, forms.ModelForm):
        upload_file = forms.FileField(required=False)

        class Meta:
            model = FileTestModel
            fields = ["name"]

    # Pass an IndexedFile instance as would happen in Django admin formsets
    existing_file = IndexedFileFactory.build()
    mock_instance = FileTestModel(name="test")

    form = BrokenForm()
    form.instance = mock_instance
    form.cleaned_data = {"upload_file": existing_file, "name": "Test"}

    # This should raise the original error
    with patch.object(forms.ModelForm, "save", return_value=mock_instance):
        with pytest.raises(AttributeError) as exc_info:
            form.save(commit=True)

        assert "'IndexedFile' object has no attribute 'name'" in str(exc_info.value)

    # Now test that our fixed form handles it correctly
    class FixedForm(IndexedFileUploadMixin, forms.ModelForm):
        upload_file = forms.FileField(required=False)

        class Meta:
            model = FileTestModel
            fields = ["name"]

        indexed_file_field_name = "indexed_file"
        upload_field_name = "upload_file"

    mock_instance2 = FileTestModel(name="test2")
    mock_instance2.save = Mock()

    fixed_form = FixedForm()
    fixed_form.instance = mock_instance2
    fixed_form.cleaned_data = {"upload_file": existing_file, "name": "Fixed"}
    fixed_form.save_m2m = Mock()

    with patch.object(forms.ModelForm, "save", return_value=mock_instance2):
        # Should handle IndexedFile instance without error
        result = fixed_form.save(commit=True)
        assert result.indexed_file == existing_file
        mock_instance2.save.assert_called_once()
