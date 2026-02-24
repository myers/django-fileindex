"""Service for extracting metadata from image files using ONLY Pillow."""

import logging
from itertools import chain
from typing import Any, Final, Literal

from PIL import Image, ImageFile, ImageOps

from .animated_parsers import parse_avif_duration, parse_webp_duration
from .thumbhash import rgba_to_thumb_hash

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


def extract_image_metadata(file_path: str, mime_type: str) -> tuple[FileMetadata, bool]:
    """Extract metadata from image files using ONLY Pillow.

    Args:
        file_path: Path to the image file.
        mime_type: MIME type of the image.

    Returns:
        Tuple of (metadata dict, is_corrupt flag).
        If Pillow cannot handle the image, it's marked as corrupt.
    """
    metadata: FileMetadata = {}
    is_corrupt = False

    # Enable loading of truncated images
    ImageFile.LOAD_TRUNCATED_IMAGES = True

    try:
        # Open image once for all operations
        with Image.open(file_path) as img:
            image_info = {}

            # Extract and validate dimensions (required by constraints)
            if img.width > 0 and img.height > 0:
                image_info["width"] = img.width
                image_info["height"] = img.height
            else:
                logger.warning(f"Invalid dimensions for {file_path}: width={img.width}, height={img.height}")
                return metadata, True

            # Generate thumbhash
            thumbhash = _generate_thumbhash(file_path)
            if thumbhash:
                image_info["thumbhash"] = thumbhash
            else:
                logger.warning(f"Failed to generate thumbhash for {file_path}")
                return metadata, True

            # Check for animation and extract duration
            if mime_type in ANIMATED_IMAGE_FORMATS:
                duration_ms = _extract_animated_duration(img, file_path, mime_type)
                if duration_ms and duration_ms > 0:
                    metadata["duration"] = duration_ms
                    image_info["animated"] = True
                else:
                    image_info["animated"] = False
            else:
                image_info["animated"] = False

            # Store image info in structured format
            metadata["image"] = image_info

        # Ensure required dimensions are present for images
        if "image" not in metadata or "width" not in metadata["image"] or "height" not in metadata["image"]:
            logger.warning(f"Missing required dimensions for image {file_path}")
            is_corrupt = True

    except Exception as e:
        logger.error(f"Failed to extract image metadata from {file_path} using Pillow: {e}")
        is_corrupt = True

    return metadata, is_corrupt


def _generate_thumbhash(file_path: str) -> str | None:
    """Generate thumbhash from image file path.

    Args:
        file_path: Path to the image file

    Returns:
        Hex string of thumbhash or None on error
    """
    try:
        with Image.open(file_path) as img:
            img = img.convert("RGBA")
            img.thumbnail(THUMBHASH_MAX_SIZE)
            img = ImageOps.exif_transpose(img)
            rgba = list(chain.from_iterable(img.get_flattened_data()))
            thumb_hash = rgba_to_thumb_hash(img.width, img.height, rgba)
            return bytes(thumb_hash).hex()
    except Exception as e:
        logger.error(f"Failed to generate thumbhash: {e}")
        return None


def _extract_animated_duration(img: Image.Image, file_path: str, mime_type: str) -> int | None:
    """Extract total duration from animated image.

    Uses custom parsers for AVIF and WebP (where Pillow doesn't provide duration),
    falls back to Pillow for GIF.

    Args:
        img: PIL Image object (must be opened)
        file_path: Path to the image file
        mime_type: MIME type of the image

    Returns:
        Total duration in milliseconds or None if not animated/error
    """
    try:
        # Use custom parsers for AVIF and WebP (Pillow doesn't provide duration)
        if mime_type == "image/avif":
            return parse_avif_duration(file_path)
        elif mime_type == "image/webp":
            return parse_webp_duration(file_path)
        elif mime_type == "image/gif":
            # Use Pillow for GIF (it works correctly)
            return _extract_gif_duration_with_pillow(img)
        else:
            logger.warning(f"Unknown animated format: {mime_type}")
            return None

    except Exception as e:
        logger.error(f"Failed to extract animated duration from {file_path}: {e}")
        return None


def _extract_gif_duration_with_pillow(img: Image.Image) -> int | None:
    """Extract total duration from GIF using Pillow (works correctly for GIF).

    Args:
        img: PIL Image object (must be opened)

    Returns:
        Total duration in milliseconds or None if not animated/error
    """
    try:
        # Check if image has multiple frames
        if not hasattr(img, "seek"):
            return None

        total_duration = 0
        frame_count = 0

        # Start from beginning
        img.seek(0)

        while True:
            try:
                # Get frame duration in milliseconds
                # For GIF, Pillow provides this correctly
                frame_duration = img.info.get("duration")
                if frame_duration is None:
                    logger.warning("GIF frame missing duration, skipping")
                    break

                total_duration += frame_duration
                frame_count += 1

                # Move to next frame
                img.seek(img.tell() + 1)
            except EOFError:
                # End of animation reached
                break
            except Exception:
                # Error seeking to next frame
                break

        # Return to first frame
        img.seek(0)

        # Only return duration if we found multiple frames
        if frame_count > 1 and total_duration > 0:
            return total_duration
        else:
            return None

    except Exception as e:
        logger.error(f"Failed to extract GIF duration with Pillow: {e}")
        return None
