"""Service for extracting metadata from media files."""

import logging
from typing import Any, Final, Literal

from PIL import Image
from thumbhash import image_to_thumbhash

from fileindex.services import media_analysis

# Type alias for metadata dictionary (Python 3.11 compatible)
FileMetadata = dict[str, Any]

# Constants with Final annotation for better type checking
THUMBHASH_MAX_SIZE: Final[tuple[int, int]] = (100, 100)
SECONDS_TO_MS: Final[int] = 1000

# Supported animated image formats
AnimatedImageFormat = Literal["image/gif", "image/webp", "image/avif"]
ANIMATED_IMAGE_FORMATS: Final[list[AnimatedImageFormat]] = [
    "image/gif",
    "image/webp",
    "image/avif",
]

logger = logging.getLogger(__name__)


def extract_required_metadata(
    mime_type: str | None, filepath: str
) -> tuple[FileMetadata, bool]:
    """Extract metadata required by database constraints.

    Args:
        mime_type: The MIME type of the file.
        filepath: The actual filesystem path to the file.

    Returns:
        A tuple of (metadata dict, is_corrupt flag).
        The metadata dict contains extracted metadata.
        The is_corrupt flag is True if extraction failed.
    """
    metadata: FileMetadata = {}
    is_corrupt: bool = False

    try:
        if mime_type and mime_type.startswith("image/"):
            return _extract_image_metadata(filepath, mime_type)
        elif mime_type and mime_type.startswith("video/"):
            return _extract_video_metadata(filepath)
        elif mime_type and mime_type.startswith("audio/"):
            return _extract_audio_metadata(filepath)
        else:
            # No metadata extraction needed for other file types
            return metadata, is_corrupt

    except Exception as e:
        # If metadata extraction fails, mark as corrupt to satisfy constraints
        error_type = type(e).__name__
        logger.error(
            f"Failed to extract metadata for {filepath} "
            f"(MIME: {mime_type}): "
            f"{error_type}: {e}"
        )
        return {}, True


def _extract_image_metadata(filepath: str, mime_type: str) -> tuple[FileMetadata, bool]:
    """Extract metadata from image files.

    Args:
        filepath: Path to the image file.
        mime_type: MIME type of the image.

    Returns:
        Tuple of (metadata dict, is_corrupt flag).
    """
    metadata: FileMetadata = {}
    is_corrupt = False

    # Open image once for all operations
    with Image.open(filepath) as img:
        # Extract and validate dimensions (required by constraints)
        if img.width > 0 and img.height > 0:
            metadata["width"] = img.width
            metadata["height"] = img.height
        else:
            logger.warning(
                f"Invalid dimensions for {filepath}: "
                f"width={img.width}, height={img.height}"
            )
            return metadata, True

        # Generate thumbhash
        img_for_thumbhash = img
        if img.mode != "RGBA":
            img_for_thumbhash = img.convert("RGBA")

        # Create a copy for thumbnail to avoid modifying original
        img_thumb = img_for_thumbhash.copy()
        img_thumb.thumbnail(THUMBHASH_MAX_SIZE, Image.Resampling.LANCZOS)

        thumbhash_bytes = image_to_thumbhash(img_thumb)
        # Handle both bytes and str return types from image_to_thumbhash
        if isinstance(thumbhash_bytes, bytes):
            metadata["thumbhash"] = thumbhash_bytes.hex()
        else:
            metadata["thumbhash"] = thumbhash_bytes

    # Ensure required dimensions are present for images
    if "width" not in metadata or "height" not in metadata:
        logger.warning(f"Missing required dimensions for image {filepath}")
        is_corrupt = True
        return metadata, is_corrupt

    # Handle animated images (extract duration if animated)
    if mime_type in ANIMATED_IMAGE_FORMATS:
        duration_sec = media_analysis.get_duration(filepath, mime_type)
        if duration_sec and duration_sec > 0:
            metadata["duration"] = int(duration_sec * SECONDS_TO_MS)
            metadata["animated"] = True

    return metadata, is_corrupt


def _extract_video_metadata(filepath: str) -> tuple[FileMetadata, bool]:
    """Extract metadata from video files.

    Args:
        filepath: Path to the video file.

    Returns:
        Tuple of (metadata dict, is_corrupt flag).
    """
    metadata: FileMetadata = {}
    is_corrupt = False

    # Extract required metadata (dimensions, duration, frame_rate)
    video_metadata = media_analysis.extract_video_metadata(filepath)
    if video_metadata:
        # Validate video dimensions
        width = video_metadata.get("width")
        height = video_metadata.get("height")
        if width and height and width > 0 and height > 0:
            metadata["width"] = width
            metadata["height"] = height

        # Validate duration
        duration = video_metadata.get("duration")
        if duration and duration > 0:
            metadata["duration"] = int(duration * SECONDS_TO_MS)

        # Validate frame rate
        frame_rate = video_metadata.get("frame_rate")
        if frame_rate and frame_rate > 0:
            metadata["frame_rate"] = frame_rate

    # Ensure all required fields are present for video
    required_video_fields = ["width", "height", "duration", "frame_rate"]
    missing_fields = [f for f in required_video_fields if f not in metadata]
    if missing_fields:
        logger.warning(
            f"Missing required metadata for video {filepath}: {missing_fields}"
        )
        is_corrupt = True

    return metadata, is_corrupt


def _extract_audio_metadata(filepath: str) -> tuple[FileMetadata, bool]:
    """Extract metadata from audio files.

    Args:
        filepath: Path to the audio file.

    Returns:
        Tuple of (metadata dict, is_corrupt flag).
    """
    metadata: FileMetadata = {}
    is_corrupt = False

    # Extract duration (required by constraints)
    audio_metadata = media_analysis.extract_audio_metadata(filepath)
    if audio_metadata:
        # Validate duration is positive
        duration = audio_metadata.get("duration")
        if duration and duration > 0:
            metadata["duration"] = int(duration * SECONDS_TO_MS)

    # Ensure required duration field is present for audio
    if "duration" not in metadata:
        logger.warning(f"Missing required duration metadata for audio {filepath}")
        is_corrupt = True

    return metadata, is_corrupt
