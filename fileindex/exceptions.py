"""
Custom exceptions and error types for django-fileindex.
"""

from enum import Enum


class ImportErrorType(Enum):
    """Error types for file import operations."""

    VALIDATION_FAILED = "VALIDATION_FAILED"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    IMPORT_FAILED = "IMPORT_FAILED"
    FILE_NOT_EXISTS = "FILE_NOT_EXISTS"
    DELETE_FAILED = "DELETE_FAILED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"

    def __str__(self) -> str:
        """Return the string value for backwards compatibility."""
        return self.value
