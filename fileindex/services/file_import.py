"""
Service module for file import operations.

This module provides reusable functions for importing files into the IndexedFile system,
used by management commands and other parts of the application.
"""

import logging
import os
from collections.abc import Callable
from typing import Any

from fileindex.exceptions import ImportErrorType
from fileindex.models import IndexedFile
from fileindex.services.file_validation import should_import

logger = logging.getLogger(__name__)


def import_file(
    filepath: str,
    only_hard_link: bool = False,
    delete_after: bool = False,
    validate: bool = True,
    hash_progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[IndexedFile | None, bool, ImportErrorType | None]:
    """
    Import a single file into the IndexedFile system.

    Args:
        filepath: Path to the file to import
        only_hard_link: If True, only create hard links (no copying)
        delete_after: If True, delete the original file after successful import
        validate: If True, check if file should be imported using validation rules
        hash_progress_callback: Optional callback(bytes_processed, total_bytes) for hash progress

    Returns:
        Tuple of (indexed_file, created, error_message)
        - indexed_file: The IndexedFile instance if successful, None if failed
        - created: True if a new file was indexed, False if already existed
        - error_message: Error message if failed, None if successful
    """
    # Validate if file should be imported
    if validate and not should_import(filepath):
        logger.debug(f"Skipping file (validation failed): {filepath}")
        return None, False, ImportErrorType.VALIDATION_FAILED

    # Check if file exists
    if not os.path.exists(filepath):
        logger.error(f"File does not exist: {filepath}")
        return None, False, ImportErrorType.FILE_NOT_EXISTS

    try:
        # Import the file
        indexed_file, created = IndexedFile.objects.get_or_create_from_file(
            filepath, only_hard_link=only_hard_link, hash_progress_callback=hash_progress_callback
        )

        # Delete original if requested and import was successful
        if delete_after and indexed_file:
            try:
                os.unlink(filepath)
                logger.info(f"Deleted original file: {filepath}")
            except OSError as e:
                logger.warning(f"Could not delete original file {filepath}: {e}")

        logger.info(f"{'Created' if created else 'Found existing'} IndexedFile: {indexed_file.sha512[:10]}...")
        return indexed_file, created, None

    except Exception as e:
        logger.error(f"Failed to import {filepath}: {str(e)}")
        return None, False, ImportErrorType.IMPORT_FAILED


def import_directory(
    dirpath: str,
    recursive: bool = True,
    only_hard_link: bool = False,
    delete_after: bool = False,
    validate: bool = True,
    progress_callback: Callable[[str, bool, str | None], None] | None = None,
    hash_progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """
    Import all files from a directory.

    Args:
        dirpath: Path to the directory to import from
        recursive: If True, process subdirectories recursively
        only_hard_link: If True, only create hard links (no copying)
        delete_after: If True, delete original files after successful import
        validate: If True, check if files should be imported using validation rules
        progress_callback: Optional callback function(filepath, success, error_msg) called for each file
        hash_progress_callback: Optional callback(bytes_processed, total_bytes) for hash progress

    Returns:
        Dictionary with import statistics:
        - total_files: Total number of files processed
        - imported: Number of successfully imported files
        - created: Number of new files created
        - skipped: Number of files skipped (validation or already exists)
        - errors: Dictionary of filepath -> error_message for failed imports
    """
    stats = {
        "total_files": 0,
        "imported": 0,
        "created": 0,
        "skipped": 0,
        "errors": {},
    }

    if not os.path.exists(dirpath):
        logger.error(f"Directory does not exist: {dirpath}")
        return stats

    if not os.path.isdir(dirpath):
        logger.error(f"Path is not a directory: {dirpath}")
        return stats

    # Walk the directory
    for root, dirs, files in os.walk(dirpath):
        # Sort for consistent ordering
        dirs.sort()
        files.sort()

        # Process each file
        for filename in files:
            filepath = os.path.join(root, filename)
            stats["total_files"] += 1

            # Import the file
            indexed_file, created, error = import_file(
                filepath,
                only_hard_link=only_hard_link,
                delete_after=delete_after,
                validate=validate,
                hash_progress_callback=hash_progress_callback,
            )

            # Update statistics
            if error:
                if error == ImportErrorType.VALIDATION_FAILED:
                    stats["skipped"] += 1
                else:
                    stats["errors"][filepath] = str(error)
            else:
                stats["imported"] += 1
                if created:
                    stats["created"] += 1

            # Call progress callback if provided
            if progress_callback:
                progress_callback(filepath, error is None, str(error) if error else None)

        # Stop recursion if not recursive
        if not recursive:
            break

    return stats


def batch_import_files(
    file_paths: list[str],
    only_hard_link: bool = False,
    delete_after: bool = False,
    validate: bool = True,
    progress_callback: Callable[[str, bool, str | None], None] | None = None,
    stop_on_error: bool = False,
    hash_progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """
    Import multiple files in batch.

    Args:
        file_paths: List of file paths to import
        only_hard_link: If True, only create hard links (no copying)
        delete_after: If True, delete original files after successful import
        validate: If True, check if files should be imported using validation rules
        progress_callback: Optional callback(filepath, success, error_msg)
        stop_on_error: If True, stop processing on first error
        hash_progress_callback: Optional callback(bytes_processed, total_bytes) for hash progress

    Returns:
        Dictionary with import statistics (same as import_directory)
    """
    stats = {
        "total_files": len(file_paths),
        "imported": 0,
        "created": 0,
        "skipped": 0,
        "errors": {},
    }

    for filepath in file_paths:
        # Import the file
        indexed_file, created, error = import_file(
            filepath,
            only_hard_link=only_hard_link,
            delete_after=delete_after,
            validate=validate,
            hash_progress_callback=hash_progress_callback,
        )

        # Update statistics
        if error:
            if error == ImportErrorType.VALIDATION_FAILED:
                stats["skipped"] += 1
            else:
                stats["errors"][filepath] = str(error)
                if stop_on_error:
                    logger.error(f"Stopping batch import due to error: {error}")
                    break
        else:
            stats["imported"] += 1
            if created:
                stats["created"] += 1

        # Call progress callback if provided
        if progress_callback:
            progress_callback(filepath, error is None, error)

    return stats


def find_importable_files(
    dirpath: str,
    recursive: bool = True,
    validate: bool = True,
) -> list[str]:
    """
    Find all files in a directory that can be imported.

    Args:
        dirpath: Path to the directory to scan
        recursive: If True, scan subdirectories recursively
        validate: If True, only include files that pass validation

    Returns:
        List of file paths that can be imported
    """
    importable_files = []

    if not os.path.exists(dirpath) or not os.path.isdir(dirpath):
        return importable_files

    for root, dirs, files in os.walk(dirpath):
        dirs.sort()
        files.sort()

        for filename in files:
            filepath = os.path.join(root, filename)

            # Check if file should be imported
            if not validate or should_import(filepath):
                importable_files.append(filepath)

        if not recursive:
            break

    return importable_files
