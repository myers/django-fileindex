"""
Django FileIndex - A Django app for file deduplication and indexing using SHA hashes.
"""

# Latest migration name for external apps to depend on
# This allows other Django apps to safely reference our migrations
# without hardcoding migration names
LATEST_MIGRATION = "0003_alter_indexedfile_size_to_biginteger"

__version__ = "0.4.1"

# Import commonly used utilities for easier access
from .fields import IndexedFileField, MultipleIndexedFilesField
from .forms import (
    IndexedFileUploadMixin,
    MultipleIndexedFilesFormMixin,
    IndexedFileModelForm,
)
from .upload_utils import (
    create_indexed_file_from_upload,
    validate_image_upload,
    cleanup_failed_upload,
    create_indexed_files_batch,
    get_upload_path_for_model,
)

__all__ = [
    # Fields
    'IndexedFileField',
    'MultipleIndexedFilesField',
    # Forms
    'IndexedFileUploadMixin',
    'MultipleIndexedFilesFormMixin',
    'IndexedFileModelForm',
    # Utilities
    'create_indexed_file_from_upload',
    'validate_image_upload',
    'cleanup_failed_upload',
    'create_indexed_files_batch',
    'get_upload_path_for_model',
]