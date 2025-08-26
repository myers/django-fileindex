"""Service for extracting metadata from media files."""

import logging
from typing import Any, Final, Literal

from PIL import Image
from thumbhash import image_to_thumbhash

from fileindex.services import media_analysis, mediainfo_analysis

# Type alias for metadata dictionary using Python 3.11 compatible syntax
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


def extract_required_metadata(mime_type: str | None, filepath: str) -> tuple[FileMetadata, bool]:
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
        logger.error(f"Failed to extract metadata for {filepath} (MIME: {mime_type}): {error_type}: {e}")
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

    try:
        # Open image once for all operations
        with Image.open(filepath) as img:
            image_info = {}

            # Extract and validate dimensions (required by constraints)
            if img.width > 0 and img.height > 0:
                image_info["width"] = img.width
                image_info["height"] = img.height
            else:
                logger.warning(f"Invalid dimensions for {filepath}: width={img.width}, height={img.height}")
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
                image_info["thumbhash"] = thumbhash_bytes.hex()
            else:
                image_info["thumbhash"] = thumbhash_bytes

            # Check for animation and set animated flag
            if mime_type in ANIMATED_IMAGE_FORMATS:
                duration_sec = media_analysis.get_duration(filepath, mime_type)
                if duration_sec and duration_sec > 0:
                    metadata["duration"] = int(duration_sec * SECONDS_TO_MS)
                    image_info["animated"] = True
                else:
                    image_info["animated"] = False
            else:
                image_info["animated"] = False

            # Store image info in structured format
            metadata["image"] = image_info

        # Extract MediaInfo metadata (supplemental to PIL/ffprobe)
        try:
            mediainfo_data = mediainfo_analysis.extract_mediainfo_metadata(filepath)
        except (ImportError, ValueError) as e:
            logger.warning(f"Could not extract MediaInfo metadata: {e}")
            mediainfo_data = {}
        if mediainfo_data:
            metadata["mediainfo"] = mediainfo_data

        # Ensure required dimensions are present for images
        if "image" not in metadata or "width" not in metadata["image"] or "height" not in metadata["image"]:
            logger.warning(f"Missing required dimensions for image {filepath}")
            is_corrupt = True

    except Exception as e:
        logger.error(f"Failed to extract image metadata from {filepath}: {e}")
        is_corrupt = True

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

    try:
        video_metadata = media_analysis.extract_video_metadata(filepath)

        # Check for required video stream first
        if "video" not in video_metadata:
            logger.warning(f"No video stream found in {filepath}")
            return {}, True

        # Validate required video fields before copying
        video = video_metadata["video"]
        if not (video.get("width") and video.get("height") and video.get("width") > 0 and video.get("height") > 0):
            logger.warning(f"Invalid video dimensions for {filepath}")
            return {}, True

        # Frame rate is required for video
        if not video.get("frame_rate") or video.get("frame_rate") <= 0:
            logger.warning(f"Missing or invalid frame rate for video {filepath}")
            return {}, True

        # Check for required duration and validate it's positive
        if "duration" not in video_metadata or video_metadata["duration"] <= 0:
            logger.warning(f"Missing or invalid duration for video {filepath}")
            return {}, True

        # All required fields are valid, copy the metadata
        metadata["video"] = video_metadata["video"]
        metadata["duration"] = video_metadata["duration"]

        # Copy optional fields
        if "audio" in video_metadata:
            metadata["audio"] = video_metadata["audio"]

        if "ffprobe" in video_metadata:
            metadata["ffprobe"] = video_metadata["ffprobe"]

        # Extract MediaInfo metadata (supplemental to ffprobe)
        try:
            mediainfo_data = mediainfo_analysis.extract_mediainfo_metadata(filepath)
        except (ImportError, ValueError) as e:
            logger.warning(f"Could not extract MediaInfo metadata: {e}")
            mediainfo_data = {}
        if mediainfo_data:
            metadata["mediainfo"] = mediainfo_data

    except Exception as e:
        logger.error(f"Failed to extract video metadata from {filepath}: {e}")
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

    try:
        audio_metadata = media_analysis.extract_audio_metadata(filepath)

        # Check for required duration and validate it's positive
        if "duration" not in audio_metadata or audio_metadata["duration"] <= 0:
            logger.warning(f"Missing or invalid duration for audio {filepath}")
            return {}, True

        # Duration is valid, copy all metadata
        metadata["duration"] = audio_metadata["duration"]

        # Copy audio info if present
        if "audio" in audio_metadata:
            metadata["audio"] = audio_metadata["audio"]

        # Copy ffprobe data if present
        if "ffprobe" in audio_metadata:
            metadata["ffprobe"] = audio_metadata["ffprobe"]

        # Extract MediaInfo metadata (supplemental to ffprobe)
        try:
            mediainfo_data = mediainfo_analysis.extract_mediainfo_metadata(filepath)
        except (ImportError, ValueError) as e:
            logger.warning(f"Could not extract MediaInfo metadata: {e}")
            mediainfo_data = {}
        if mediainfo_data:
            metadata["mediainfo"] = mediainfo_data

    except Exception as e:
        logger.error(f"Failed to extract audio metadata from {filepath}: {e}")
        is_corrupt = True

    return metadata, is_corrupt
