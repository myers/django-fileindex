"""
Service module for file import operations.
"""

import logging
import os

from .models import IndexedFile

logger = logging.getLogger(__name__)


def should_import_file(filepath: str) -> bool:
    """
    Check if a file should be imported based on various criteria.

    Args:
        filepath: Path to the file to check

    Returns:
        bool: True if file should be imported, False otherwise
    """
    # Skip hidden files
    if os.path.basename(filepath).startswith("."):
        return False

    # Skip temporary files
    if filepath.endswith((".tmp", ".temp", "~")):
        return False

    # Skip empty files
    try:
        if os.path.getsize(filepath) == 0:
            return False
    except OSError:
        return False

    # Add more criteria as needed
    return True


def import_single_file(
    filepath: str, only_hard_link: bool = False, remove_after_import: bool = False
) -> tuple[IndexedFile | None, bool, str | None]:
    """
    Import a single file into the index.

    Args:
        filepath: Path to the file to import
        only_hard_link: If True, only create hard links (no copying)
        remove_after_import: If True, delete the original file after successful import

    Returns:
        Tuple of (indexed_file, created, error_message)
    """
    if not should_import_file(filepath):
        logger.info(f"Skipping file {filepath} - does not meet import criteria")
        return None, False, "File does not meet import criteria"

    try:
        indexed_file, created = IndexedFile.objects.get_or_create_from_file(filepath, only_hard_link=only_hard_link)

        if created:
            logger.info(f"Successfully imported new file: {filepath}")
        else:
            logger.info(f"File already indexed: {filepath}")

        # Verify the indexed file exists
        if not os.path.exists(indexed_file.file.path):
            raise FileNotFoundError(f"Indexed file not found at {indexed_file.file.path}")

        # Remove original if requested
        if remove_after_import:
            os.unlink(filepath)
            logger.info(f"Removed original file: {filepath}")

        return indexed_file, created, None

    except Exception as e:
        logger.error(f"Error importing file {filepath}: {e}")
        return None, False, str(e)


def import_directory(
    dirpath: str,
    only_hard_link: bool = False,
    remove_after_import: bool = False,
    recursive: bool = True,
) -> dict[str, str]:
    """
    Import all files in a directory.

    Args:
        dirpath: Path to the directory to import
        only_hard_link: If True, only create hard links (no copying)
        remove_after_import: If True, delete original files after successful import
        recursive: If True, import files from subdirectories

    Returns:
        Dict mapping failed file paths to error messages
    """
    errors = {}

    if recursive:
        for root, dirs, files in os.walk(dirpath):
            dirs.sort()
            files.sort()

            for filename in files:
                filepath = os.path.join(root, filename)
                _, _, error = import_single_file(
                    filepath,
                    only_hard_link=only_hard_link,
                    remove_after_import=remove_after_import,
                )
                if error:
                    errors[filepath] = error
    else:
        # Non-recursive, only process immediate directory
        try:
            files = sorted(os.listdir(dirpath))
            for filename in files:
                filepath = os.path.join(dirpath, filename)
                if os.path.isfile(filepath):
                    _, _, error = import_single_file(
                        filepath,
                        only_hard_link=only_hard_link,
                        remove_after_import=remove_after_import,
                    )
                    if error:
                        errors[filepath] = error
        except OSError as e:
            logger.error(f"Error reading directory {dirpath}: {e}")
            errors[dirpath] = str(e)

    return errors


def import_paths(paths: list[str], only_hard_link: bool = False, remove_after_import: bool = False) -> dict[str, str]:
    """
    Import files from a list of paths (files or directories).

    Args:
        paths: List of file or directory paths to import
        only_hard_link: If True, only create hard links (no copying)
        remove_after_import: If True, delete original files after successful import

    Returns:
        Dict mapping failed file paths to error messages
    """
    errors = {}

    for path in paths:
        if os.path.isfile(path):
            _, _, error = import_single_file(
                path,
                only_hard_link=only_hard_link,
                remove_after_import=remove_after_import,
            )
            if error:
                errors[path] = error
        elif os.path.isdir(path):
            dir_errors = import_directory(
                path,
                only_hard_link=only_hard_link,
                remove_after_import=remove_after_import,
            )
            errors.update(dir_errors)
        else:
            errors[path] = f"Path does not exist or is not accessible: {path}"

    return errors
