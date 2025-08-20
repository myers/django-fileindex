"""
Form mixins and utilities for handling file uploads with IndexedFile integration.
"""

from django import forms
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

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
            uploaded_file: The uploaded file from the form

        Returns:
            IndexedFile: The created IndexedFile instance
        """
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


class MultipleIndexedFilesFormMixin:
    """
    Mixin for forms that need to handle multiple file uploads.

    Usage:
        class DocumentUploadForm(MultipleIndexedFilesFormMixin, forms.Form):
            files = forms.FileField(
                widget=forms.ClearableFileInput(attrs={'multiple': True})
            )

            multiple_files_field_name = 'files'

            def save_indexed_files(self, indexed_files):
                # Custom logic to handle the created IndexedFile instances
                for indexed_file in indexed_files:
                    Document.objects.create(file=indexed_file)
    """

    multiple_files_field_name = "files"  # Override in subclass
    upload_path_prefix = "uploads/temp"  # Override in subclass

    def clean(self):
        """
        Process multiple file uploads during form validation.
        """
        cleaned_data = super().clean()

        files = self.files.getlist(self.multiple_files_field_name)
        if files:
            indexed_files = self._create_indexed_files(files)
            cleaned_data["indexed_files"] = indexed_files

        return cleaned_data

    def _create_indexed_files(self, files):
        """
        Create IndexedFile instances from multiple uploaded files.

        Args:
            files: List of uploaded files

        Returns:
            List[IndexedFile]: List of created IndexedFile instances
        """
        indexed_files = []
        temp_files = []

        try:
            with transaction.atomic():
                for file in files:
                    # Save the file temporarily
                    file_name = default_storage.save(
                        f"{self.upload_path_prefix}/{file.name}",
                        ContentFile(file.read()),
                    )
                    temp_files.append(file_name)

                    # Get the full path to the saved file
                    file_path = default_storage.path(file_name)

                    # Create IndexedFile from the saved file
                    indexed_file, _ = IndexedFile.objects.get_or_create_from_file(file_path)
                    indexed_files.append(indexed_file)

            # Clean up temporary files after successful processing
            for temp_file in temp_files:
                if default_storage.exists(temp_file):
                    default_storage.delete(temp_file)

            return indexed_files

        except Exception:
            # Clean up all temporary files on error
            for temp_file in temp_files:
                if default_storage.exists(temp_file):
                    default_storage.delete(temp_file)
            raise

    def save_indexed_files(self, indexed_files):
        """
        Override this method to handle the created IndexedFile instances.

        Args:
            indexed_files: List of IndexedFile instances
        """
        raise NotImplementedError("Subclasses must implement save_indexed_files method")


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
