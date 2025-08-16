"""Service functions for media file analysis using external tools like ffprobe and ffmpeg."""

import contextlib
import json
import logging
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _run_ffprobe(file_path: str, timeout: int = 30) -> dict[str, Any] | None:
    """Run ffprobe and return parsed JSON output.

    Args:
        file_path: Path to the media file
        timeout: Command timeout in seconds

    Returns:
        Parsed JSON output from ffprobe or None on error
    """
    try:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            logger.error(f"ffprobe failed for {file_path}: {result.stderr}")
            return None

        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        logger.error(f"ffprobe timed out for {file_path}")
        return None
    except (subprocess.SubprocessError, json.JSONDecodeError) as e:
        logger.error(f"Error running ffprobe: {e}")
        return None


def get_duration(file_path: str, mime_type: str) -> float | None:
    """Get duration in seconds for gif/avif files using ffprobe.

    Args:
        file_path: Path to the media file
        mime_type: MIME type of the file

    Returns:
        Duration in seconds or None if unable to determine
    """
    if mime_type not in ["image/gif", "image/avif"]:
        return None

    data = _run_ffprobe(file_path)
    if not data:
        return None

    # Try to get duration from streams first, then format
    duration = None
    if "streams" in data and len(data["streams"]) > 0:
        duration = data["streams"][0].get("duration")
    if duration is None and "format" in data:
        duration = data["format"].get("duration")

    try:
        return float(duration) if duration else None
    except ValueError:
        return None


def extract_video_metadata(file_path: str) -> dict[str, float | int | None]:
    """Extract video metadata using ffprobe.

    Args:
        file_path: Path to the video file

    Returns:
        Dictionary with width, height, duration, and frame_rate

    Raises:
        ValueError: If video metadata cannot be extracted
    """
    data = _run_ffprobe(file_path)
    if not data:
        raise ValueError(
            f"Could not extract video metadata from {file_path}: ffprobe failed"
        )

    metadata = {}

    # Find video stream
    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if video_stream:
        metadata["width"] = video_stream.get("width")
        metadata["height"] = video_stream.get("height")

        # Parse frame rate
        r_frame_rate = video_stream.get("r_frame_rate", "0/1")
        if "/" in r_frame_rate:
            try:
                num, den = r_frame_rate.split("/")
                if int(den) != 0:
                    metadata["frame_rate"] = float(num) / float(den)
            except (ValueError, ZeroDivisionError):
                pass

    # Get duration from format or streams
    duration = None
    if "format" in data:
        duration = data["format"].get("duration")
    if duration is None and video_stream:
        duration = video_stream.get("duration")

    if duration:
        with suppress(ValueError):
            metadata["duration"] = float(duration)

    return metadata


def generate_video_thumbnail(
    video_path: str, seek_time: str = "00:00:00.5"
) -> str | None:
    """Generate thumbnail from video using ffmpeg.

    Args:
        video_path: Path to the video file
        seek_time: Time to seek to for thumbnail (default: 0.5 seconds)

    Returns:
        Path to generated thumbnail file or None on error
        Caller is responsible for cleaning up the returned file
    """
    try:
        # Create temporary thumbnail file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            thumbnail_path = tmp.name

        cmd = [
            "ffmpeg",
            "-i",
            video_path,
            "-ss",
            seek_time,
            "-vframes",
            "1",  # Extract 1 frame
            "-q:v",
            "2",  # High quality
            "-y",  # Overwrite output file
            thumbnail_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0 and Path(thumbnail_path).exists():
            return thumbnail_path
        else:
            logger.error(f"ffmpeg thumbnail generation failed: {result.stderr}")
            # Clean up failed thumbnail file
            with contextlib.suppress(OSError):
                Path(thumbnail_path).unlink()
            return None

    except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError) as e:
        logger.error(f"Error generating video thumbnail: {e}")
        return None


def extract_audio_metadata(file_path: str) -> dict[str, float | int | str | None]:
    """Extract audio metadata using ffprobe.

    Args:
        file_path: Path to the audio file

    Returns:
        Dictionary with duration, bitrate, sample_rate, channels, and tags

    Raises:
        ValueError: If audio metadata cannot be extracted
    """
    data = _run_ffprobe(file_path)
    if not data:
        raise ValueError(
            f"Could not extract audio metadata from {file_path}: ffprobe failed"
        )

    metadata = {}

    # Find audio stream
    audio_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            audio_stream = stream
            break

    if audio_stream:
        # Basic audio properties
        with suppress(ValueError, TypeError):
            metadata["sample_rate"] = int(audio_stream.get("sample_rate", 0)) or None

        metadata["channels"] = audio_stream.get("channels")

        # Get bitrate from stream or format
        bitrate = audio_stream.get("bit_rate")
        if not bitrate and "format" in data:
            bitrate = data["format"].get("bit_rate")
        if bitrate:
            with suppress(ValueError, TypeError):
                metadata["bitrate"] = int(bitrate)

    # Get duration from format
    if "format" in data:
        duration = data["format"].get("duration")
        if duration:
            with suppress(ValueError, TypeError):
                metadata["duration"] = float(duration)

        # Extract metadata tags (title, artist, album)
        tags = data["format"].get("tags", {})
        # Handle different tag name cases
        metadata["title"] = tags.get("title") or tags.get("TITLE")
        metadata["artist"] = tags.get("artist") or tags.get("ARTIST")
        metadata["album"] = tags.get("album") or tags.get("ALBUM")

    return metadata


def extract_image_dimensions_ffprobe(file_path: str) -> tuple[int, int] | None:
    """Extract image dimensions using ffprobe.

    Args:
        file_path: Path to the image file

    Returns:
        Tuple of (width, height) or None if unable to determine
    """
    data = _run_ffprobe(file_path)
    if not data:
        return None

    # Find video or image stream (ffprobe treats images as video streams)
    for stream in data.get("streams", []):
        if stream.get("codec_type") in ("video", "image"):
            width = stream.get("width")
            height = stream.get("height")
            if width and height:
                try:
                    return (int(width), int(height))
                except (ValueError, TypeError):
                    pass

    logger.warning(f"No image dimensions found in ffprobe output for {file_path}")
    return None


def extract_image_dimensions(file_path: str) -> tuple[int, int]:
    """Extract image dimensions using Pillow with fallback to ffprobe.

    Args:
        file_path: Path to the image file

    Returns:
        Tuple of (width, height)

    Raises:
        ValueError: If dimensions cannot be extracted by any method
    """
    from PIL import Image, ImageFile

    # Enable loading of truncated images
    ImageFile.LOAD_TRUNCATED_IMAGES = True

    # Try Pillow first
    try:
        with Image.open(file_path) as im:
            width, height = im.size
            return (width, height)
    except Exception as e:
        logger.warning(f"Pillow failed to open image {file_path}: {e}")

    # Try ffprobe as fallback
    dimensions = extract_image_dimensions_ffprobe(file_path)
    if dimensions:
        logger.info(f"Successfully extracted dimensions with ffprobe: {dimensions}")
        return dimensions

    # Both methods failed - raise exception to trigger corrupt flag
    error_msg = (
        f"Could not extract image dimensions from {file_path} using Pillow or ffprobe"
    )
    logger.error(error_msg)
    raise ValueError(error_msg)
