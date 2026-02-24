"""Service for routing metadata extraction to specialized services."""

import logging
from typing import Any

from fileindex.services import image_metadata, media_metadata

# Type alias for metadata dictionary using Python 3.11 compatible syntax
FileMetadata = dict[str, Any]

logger = logging.getLogger(__name__)


def extract_metadata(file_path: str, mime_type: str | None = None) -> tuple[FileMetadata, bool]:
    """Extract metadata from media files.

    This is the main entry point for metadata extraction. It determines the file type
    and routes to the appropriate extraction service.

    Args:
        file_path: Path to the media file
        mime_type: MIME type of the file (auto-detected if None)

    Returns:
        A tuple of (metadata dict, is_corrupt flag).
        The metadata dict contains extracted metadata.
        The is_corrupt flag is True if extraction failed.
    """
    # Auto-detect mime type if not provided
    if mime_type is None:
        import mimetypes

        mime_type, _ = mimetypes.guess_type(file_path)

    try:
        if mime_type and mime_type.startswith("image/"):
            return image_metadata.extract_image_metadata(file_path, mime_type)
        elif mime_type and mime_type.startswith("video/"):
            return media_metadata.extract_video_metadata(file_path)
        elif mime_type and mime_type.startswith("audio/"):
            return media_metadata.extract_audio_metadata(file_path)
        else:
            # No metadata extraction needed for other file types
            return {}, False

    except Exception as e:
        # If metadata extraction fails, mark as corrupt to satisfy constraints
        error_type = type(e).__name__
        logger.error(f"Failed to extract metadata for {file_path} (MIME: {mime_type}): {error_type}: {e}")
        return {}, True
