"""
Form mixins and utilities for handling file uploads with IndexedFile integration.
"""

from django import forms
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .models import IndexedFile


class IndexedFileUploadMixin:
    """
    Mixin for ModelForms that need to handle file uploads and create IndexedFile
    entries.

    Usage:
        class TapeImageForm(IndexedFileUploadMixin, forms.ModelForm):
            upload_file = forms.FileField()

            class Meta:
                model = TapeImage
                fields = ['image_type', 'description']

            # The model field to store IndexedFile
            indexed_file_field_name = 'indexed_file'
            upload_field_name = 'upload_file'  # The form field for file upload
    """

    indexed_file_field_name = "indexed_file"  # Override in subclass
    upload_field_name = "upload_file"  # Override in subclass
    upload_path_prefix = "uploads/temp"  # Override in subclass for custom paths

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add the upload field if not already present
        if self.upload_field_name and self.upload_field_name not in self.fields:
            self.fields[self.upload_field_name] = forms.FileField(
                required=False, label="Upload File", help_text="Select a file to upload"
            )

    def save(self, commit=True):
        """
        Save the form and handle file upload to create IndexedFile.
        """
        instance = super().save(commit=False)

        # Handle file upload if present
        uploaded_file = self.cleaned_data.get(self.upload_field_name)
        if uploaded_file:
            indexed_file = self._create_indexed_file(uploaded_file)
            setattr(instance, self.indexed_file_field_name, indexed_file)

        if commit:
            instance.save()
            self.save_m2m()

        return instance

    def _create_indexed_file(self, uploaded_file):
        """
        Create an IndexedFile from an uploaded file.

        Args:
            uploaded_file: The uploaded file from the form or an existing IndexedFile instance

        Returns:
            IndexedFile: The created or existing IndexedFile instance
        """
        # Handle case where uploaded_file is already an IndexedFile instance
        # This can happen in Django admin inline formsets
        if isinstance(uploaded_file, IndexedFile):
            return uploaded_file

        # Save the file temporarily
        file_name = default_storage.save(
            f"{self.upload_path_prefix}/{uploaded_file.name}",
            ContentFile(uploaded_file.read()),
        )

        try:
            # Get the full path to the saved file
            file_path = default_storage.path(file_name)

            # Create IndexedFile from the saved file
            indexed_file, _ = IndexedFile.objects.get_or_create_from_file(file_path)

            # Delete the temporary file since IndexedFile creates its own copy
            if default_storage.exists(file_name):
                default_storage.delete(file_name)

            return indexed_file

        except Exception:
            # Clean up on error
            if default_storage.exists(file_name):
                default_storage.delete(file_name)
            raise


class IndexedFileModelForm(IndexedFileUploadMixin, forms.ModelForm):
    """
    A ModelForm that automatically handles file uploads with IndexedFile creation.

    This is a convenience class that combines IndexedFileUploadMixin with ModelForm.

    Usage:
        class TapeImageForm(IndexedFileModelForm):
            class Meta:
                model = TapeImage
                fields = ['image_type', 'description']

            indexed_file_field_name = 'indexed_file'

            # Optionally customize the upload field
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.fields['upload_file'].help_text = "Upload an image for this tape"
    """

    pass
