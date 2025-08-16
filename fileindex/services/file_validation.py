"""File validation service for security checks."""

from pathlib import Path

# Security configuration for file imports
ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".avif",
    ".mp4",
    ".webm",
    ".pdf",
}
DISALLOWED_PATTERNS = ["..", "/etc/", "/proc/", "/sys/"]


def should_import_filename(filename):
    """Check if a filename is safe to import"""
    if not filename:
        return False

    # Check for path traversal attempts
    if any(pattern in filename.lower() for pattern in DISALLOWED_PATTERNS):
        return False

    # Check file extension
    path = Path(filename)
    return path.suffix.lower() in ALLOWED_EXTENSIONS


def should_import(filepath):
    """Check if a file path is safe to import"""
    if not filepath:
        return False

    path = Path(filepath)

    # Basic security checks
    if not path.exists():
        return False

    # Check if it's actually a file (not a directory or symlink)
    if not path.is_file():
        return False

    # Check file size (reject files larger than 100MB)
    if path.stat().st_size > 100 * 1024 * 1024:
        return False

    return should_import_filename(str(path))