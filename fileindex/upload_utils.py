"""
Utility functions for handling file uploads with IndexedFile integration.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import (
    TemporaryUploadedFile,
    UploadedFile,
)
from django.db import transaction

if TYPE_CHECKING:
    from .models import IndexedFile


def create_indexed_file_from_upload(
    uploaded_file: UploadedFile,
    path_prefix: str | None = None,
    derived_from: IndexedFile | None = None,
    derived_for: str | None = None,
    cleanup_on_error: bool = True,
    hash_progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[IndexedFile, bool]:
    """
    Create an IndexedFile from a Django UploadedFile.

    This function handles both InMemoryUploadedFile and TemporaryUploadedFile,
    saves the file temporarily, creates an IndexedFile, and cleans up.

    Args:
        uploaded_file: The uploaded file from a Django form
        path_prefix: Optional prefix for the temporary file path
        derived_from: Optional parent IndexedFile if this is a derivative
        derived_for: Optional string indicating the type of derivative
        cleanup_on_error: Whether to clean up temporary files on error
        hash_progress_callback: Optional callback(bytes_processed, total_bytes) for hash progress

    Returns:
        Tuple of (IndexedFile, created) where created is True if a new file was indexed

    Raises:
        ValueError: If the uploaded file is invalid
        IOError: If file operations fail
    """
    if not uploaded_file:
        raise ValueError("No file provided")

    path_prefix = path_prefix or "uploads/temp"

    # Handle different types of uploaded files
    if isinstance(uploaded_file, TemporaryUploadedFile):
        # File is already on disk, use its temporary path
        temp_path = uploaded_file.temporary_file_path()
        cleanup_temp = False  # Django will clean this up
    else:
        # File is in memory, save it to disk first
        file_name = default_storage.save(f"{path_prefix}/{uploaded_file.name}", ContentFile(uploaded_file.read()))
        temp_path = default_storage.path(file_name)
        cleanup_temp = True

    try:
        # Create IndexedFile from the file
        from .models import IndexedFile

        indexed_file, created = IndexedFile.objects.get_or_create_from_file(
            temp_path,
            derived_from=derived_from,
            derived_for=derived_for,
            hash_progress_callback=hash_progress_callback,
        )

        # Clean up temporary file if we created it
        if cleanup_temp and default_storage.exists(file_name):
            default_storage.delete(file_name)

        return indexed_file, created

    except Exception:
        # Clean up on error if requested
        if cleanup_on_error and cleanup_temp and default_storage.exists(file_name):
            default_storage.delete(file_name)
        raise


def validate_image_upload(
    file: UploadedFile | Path | str,
    allowed_formats: list[str] | None = None,
    max_size: int | None = None,
    min_dimensions: tuple[int, int] | None = None,
    max_dimensions: tuple[int, int] | None = None,
) -> None:
    """
    Validate an uploaded image file.

    Args:
        file: The file to validate (UploadedFile, Path, or string path)
        allowed_formats: List of allowed image formats (e.g., ['JPEG', 'PNG'])
        max_size: Maximum file size in bytes
        min_dimensions: Minimum (width, height) in pixels
        max_dimensions: Maximum (width, height) in pixels

    Raises:
        ValidationError: If the image fails validation
    """
    from PIL import Image

    # Default allowed formats if not specified
    if allowed_formats is None:
        allowed_formats = ["JPEG", "PNG", "GIF", "WEBP"]

    # Get file path or file object
    if isinstance(file, UploadedFile):
        file_obj = file
        file_size = file.size
    else:
        file_path = Path(file) if not isinstance(file, Path) else file
        if not file_path.exists():
            raise ValidationError(f"File does not exist: {file_path}")
        file_obj = open(file_path, "rb")
        file_size = file_path.stat().st_size

    try:
        # Open and validate the image
        with Image.open(file_obj) as img:
            # Check format
            if img.format not in allowed_formats:
                raise ValidationError(
                    f"Invalid image format '{img.format}'. Allowed formats: {', '.join(allowed_formats)}"
                )

            # Check dimensions
            width, height = img.size

            if min_dimensions:
                min_w, min_h = min_dimensions
                if width < min_w or height < min_h:
                    raise ValidationError(
                        f"Image dimensions {width}x{height} are below minimum required {min_w}x{min_h}"
                    )

            if max_dimensions:
                max_w, max_h = max_dimensions
                if width > max_w or height > max_h:
                    raise ValidationError(f"Image dimensions {width}x{height} exceed maximum allowed {max_w}x{max_h}")

        # Check file size
        if max_size and file_size > max_size:
            raise ValidationError(f"File size {file_size} bytes exceeds maximum {max_size} bytes")

    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        raise ValidationError(f"Invalid image file: {str(e)}") from e
    finally:
        # Close file if we opened it
        if not isinstance(file, UploadedFile) and hasattr(file_obj, "close"):
            file_obj.close()


def cleanup_failed_upload(file_path: str | Path) -> bool:
    """
    Clean up a file after a failed upload or processing.

    Args:
        file_path: Path to the file to clean up

    Returns:
        True if the file was deleted, False if it didn't exist
    """
    try:
        if isinstance(file_path, str) and file_path.startswith(default_storage.location):
            # It's a path within default storage
            rel_path = os.path.relpath(file_path, default_storage.location)
            if default_storage.exists(rel_path):
                default_storage.delete(rel_path)
                return True
        else:
            # It's a regular file path
            file_path = Path(file_path)
            if file_path.exists():
                file_path.unlink()
                return True
        return False
    except Exception:
        # Silently fail - this is cleanup code
        return False


def create_indexed_files_batch(
    files: list[UploadedFile], path_prefix: str | None = None, atomic: bool = True
) -> list[IndexedFile]:
    """
    Create IndexedFile instances from multiple uploaded files.

    Args:
        files: List of uploaded files
        path_prefix: Optional prefix for temporary file paths
        atomic: Whether to use a database transaction

    Returns:
        List of created IndexedFile instances

    Raises:
        ValidationError: If any file fails to process
    """
    path_prefix = path_prefix or "uploads/temp"
    indexed_files = []
    temp_files = []

    def process_files():
        for file in files:
            if not file:
                continue

            # Save the file temporarily
            file_name = default_storage.save(f"{path_prefix}/{file.name}", ContentFile(file.read()))
            temp_files.append(file_name)

            # Get the full path to the saved file
            file_path = default_storage.path(file_name)

            # Create IndexedFile from the saved file
            from .models import IndexedFile

            indexed_file, _ = IndexedFile.objects.get_or_create_from_file(file_path)
            indexed_files.append(indexed_file)

        return indexed_files

    try:
        if atomic:
            with transaction.atomic():
                result = process_files()
        else:
            result = process_files()

        # Clean up temporary files after successful processing
        for temp_file in temp_files:
            if default_storage.exists(temp_file):
                default_storage.delete(temp_file)

        return result

    except Exception as e:
        # Clean up all temporary files on error
        for temp_file in temp_files:
            if default_storage.exists(temp_file):
                default_storage.delete(temp_file)
        raise ValidationError(f"Failed to process files: {str(e)}") from e


def get_upload_path_for_model(instance, filename: str, base_path: str = "uploads") -> str:
    """
    Generate a consistent upload path for a model instance.

    This is useful for organizing uploaded files by model and instance ID.

    Args:
        instance: The model instance
        filename: Original filename
        base_path: Base directory for uploads

    Returns:
        Path string like 'uploads/app_label/model_name/instance_id/filename'
    """
    app_label = instance._meta.app_label
    model_name = instance._meta.model_name

    # Use instance ID if available, otherwise use 'new'
    instance_id = str(instance.pk) if instance.pk else "new"

    # Clean filename
    filename = Path(filename).name

    return f"{base_path}/{app_label}/{model_name}/{instance_id}/{filename}"
