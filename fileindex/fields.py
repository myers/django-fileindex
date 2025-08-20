"""
Custom Django form fields for handling file uploads with automatic IndexedFile creation.
"""

from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .models import IndexedFile


class IndexedFileField(forms.FileField):
    """
    A form field that automatically creates IndexedFile entries from uploaded files.

    Usage:
        class MyForm(forms.Form):
            document = IndexedFileField(
                required=False,
                allowed_extensions=['.pdf', '.doc', '.docx'],
                max_file_size=10 * 1024 * 1024  # 10MB
            )
    """

    def __init__(
        self,
        *args,
        allowed_extensions: list[str] | None = None,
        max_file_size: int | None = None,
        path_prefix: str | None = None,
        **kwargs,
    ):
        """
        Initialize the IndexedFileField.

        Args:
            allowed_extensions: List of allowed file extensions (e.g., ['.jpg', '.png'])
            max_file_size: Maximum file size in bytes
            path_prefix: Prefix for the temporary file path (e.g., 'uploads/temp')
        """
        self.allowed_extensions = allowed_extensions
        self.max_file_size = max_file_size
        self.path_prefix = path_prefix or "uploads/temp"
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        """
        Validate and process the uploaded file.

        Returns:
            IndexedFile: The created IndexedFile instance
        """
        file = super().clean(data, initial)

        if file is None:
            return None

        # Validate file extension
        if self.allowed_extensions:
            ext = Path(file.name).suffix.lower()
            if ext not in self.allowed_extensions:
                msg = f"File type not allowed. Allowed types: {', '.join(self.allowed_extensions)}"
                raise ValidationError(msg)

        # Validate file size
        if self.max_file_size and file.size > self.max_file_size:
            raise ValidationError(f"File size exceeds maximum allowed size of {self.max_file_size} bytes")

        # Save the file temporarily and create IndexedFile
        file_name = default_storage.save(f"{self.path_prefix}/{file.name}", ContentFile(file.read()))

        try:
            # Get the full path to the saved file
            file_path = default_storage.path(file_name)

            # Create IndexedFile from the saved file
            indexed_file, _ = IndexedFile.objects.get_or_create_from_file(file_path)

            # Delete the temporary file since IndexedFile creates its own copy
            if default_storage.exists(file_name):
                default_storage.delete(file_name)

            return indexed_file

        except Exception as e:
            # Clean up on error
            if default_storage.exists(file_name):
                default_storage.delete(file_name)
            raise ValidationError(f"Failed to process file: {str(e)}") from e


class MultipleIndexedFilesField(forms.FileField):
    """
    A form field that handles multiple file uploads and creates IndexedFile entries.

    Usage:
        class MyForm(forms.Form):
            images = MultipleIndexedFilesField(
                widget=forms.ClearableFileInput(attrs={'multiple': True}),
                allowed_extensions=['.jpg', '.png', '.gif'],
                max_file_size=5 * 1024 * 1024  # 5MB per file
            )
    """

    def __init__(
        self,
        *args,
        allowed_extensions: list[str] | None = None,
        max_file_size: int | None = None,
        max_files: int | None = None,
        path_prefix: str | None = None,
        **kwargs,
    ):
        """
        Initialize the MultipleIndexedFilesField.

        Args:
            allowed_extensions: List of allowed file extensions
            max_file_size: Maximum size per file in bytes
            max_files: Maximum number of files allowed
            path_prefix: Prefix for the temporary file paths
        """
        self.allowed_extensions = allowed_extensions
        self.max_file_size = max_file_size
        self.max_files = max_files
        self.path_prefix = path_prefix or "uploads/temp"

        # Default to multiple file input widget
        if "widget" not in kwargs:
            kwargs["widget"] = forms.ClearableFileInput(attrs={"multiple": True})

        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        """
        Validate and process multiple uploaded files.

        Returns:
            List[IndexedFile]: List of created IndexedFile instances
        """
        files = data if isinstance(data, list) else [data] if data else []

        if not files:
            if self.required:
                raise ValidationError("No files were uploaded")
            return []

        # Validate number of files
        if self.max_files and len(files) > self.max_files:
            raise ValidationError(f"Too many files. Maximum allowed: {self.max_files}")

        indexed_files = []
        temp_files = []

        try:
            for file in files:
                if file is None:
                    continue

                # Validate file extension
                if self.allowed_extensions:
                    ext = Path(file.name).suffix.lower()
                    if ext not in self.allowed_extensions:
                        raise ValidationError(
                            f"File '{file.name}' has invalid type. Allowed types: {', '.join(self.allowed_extensions)}"
                        )

                # Validate file size
                if self.max_file_size and file.size > self.max_file_size:
                    msg = f"File '{file.name}' exceeds maximum size of {self.max_file_size} bytes"
                    raise ValidationError(msg)

                # Save the file temporarily
                file_name = default_storage.save(f"{self.path_prefix}/{file.name}", ContentFile(file.read()))
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

        except Exception as e:
            # Clean up all temporary files on error
            for temp_file in temp_files:
                if default_storage.exists(temp_file):
                    default_storage.delete(temp_file)
            raise ValidationError(f"Failed to process files: {str(e)}") from e
