"""
Service functions for media file analysis using external tools like ffprobe
and ffmpeg.
"""

import contextlib
import json
import logging
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Cache for ffprobe version
_ffprobe_version: str | None = None


def get_ffprobe_version() -> str | None:
    """Get the version string of ffprobe.

    Returns:
        Version string like "4.4.2-0ubuntu0.22.04.1" or None if unable to determine
    """
    try:
        result = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            # Parse first line: "ffprobe version 4.4.2-0ubuntu0.22.04.1 ..."
            lines = result.stdout.split("\n")
            if lines and lines[0].startswith("ffprobe version"):
                # Extract version from "ffprobe version X.X.X ..."
                version_line = lines[0].replace("ffprobe version ", "")
                # Take the first word (version number)
                version = version_line.split(" ")[0]
                return version
    except FileNotFoundError:
        logger.warning("ffprobe not found. Please install ffmpeg/ffprobe.")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe version check timed out after 5 seconds")
        return None
    except Exception as e:
        logger.warning(f"Could not get ffprobe version: {e}")
    return None


def get_cached_ffprobe_version() -> str | None:
    """Get cached ffprobe version to avoid repeated subprocess calls.

    Returns:
        Cached version string or None
    """
    global _ffprobe_version
    if _ffprobe_version is None:
        _ffprobe_version = get_ffprobe_version()
    return _ffprobe_version


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


def extract_video_metadata(file_path: str) -> dict[str, Any]:
    """Extract video metadata using ffprobe.

    Args:
        file_path: Path to the video file

    Returns:
        Dictionary with 'video', 'audio', 'duration', and 'ffprobe' keys

    Raises:
        ValueError: If video metadata cannot be extracted
    """
    data = _run_ffprobe(file_path)
    if not data:
        raise ValueError(f"Could not extract video metadata from {file_path}: ffprobe failed")

    metadata = {}

    # Find video and audio streams
    video_stream = None
    audio_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and not video_stream:
            video_stream = stream
        elif stream.get("codec_type") == "audio" and not audio_stream:
            audio_stream = stream

    # Extract video information
    if video_stream:
        video_info = {}
        video_info["codec"] = video_stream.get("codec_name")
        video_info["width"] = video_stream.get("width")
        video_info["height"] = video_stream.get("height")

        # Video bitrate
        if video_bitrate := video_stream.get("bit_rate"):
            try:
                video_info["bitrate"] = int(video_bitrate)
            except (ValueError, TypeError):
                pass

        # Parse frame rate
        r_frame_rate = video_stream.get("r_frame_rate", "0/1")
        if "/" in r_frame_rate:
            try:
                num, den = r_frame_rate.split("/")
                if int(den) != 0:
                    video_info["frame_rate"] = float(num) / float(den)
            except (ValueError, ZeroDivisionError):
                pass

        metadata["video"] = video_info

    # Extract audio information
    if audio_stream:
        audio_info = {}
        audio_info["codec"] = audio_stream.get("codec_name")

        if audio_bitrate := audio_stream.get("bit_rate"):
            try:
                audio_info["bitrate"] = int(audio_bitrate)
            except (ValueError, TypeError):
                pass

        if sample_rate := audio_stream.get("sample_rate"):
            try:
                audio_info["sample_rate"] = int(sample_rate)
            except (ValueError, TypeError):
                pass

        audio_info["channels"] = audio_stream.get("channels")

        metadata["audio"] = audio_info

    # Get duration from format or streams (convert to milliseconds)
    duration = None
    if "format" in data:
        duration = data["format"].get("duration")
    if duration is None and video_stream:
        duration = video_stream.get("duration")
    if duration is None and audio_stream:
        duration = audio_stream.get("duration")

    if duration:
        with suppress(ValueError):
            metadata["duration"] = float(duration) * 1000  # Convert to milliseconds

    # Store complete ffprobe output with version
    metadata["ffprobe"] = {"version": get_cached_ffprobe_version(), "data": data}

    return metadata


def generate_video_thumbnail(video_path: str, seek_time: str = "00:00:00.5") -> str | None:
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


def extract_audio_metadata(file_path: str) -> dict[str, Any]:
    """Extract audio metadata using ffprobe.

    Args:
        file_path: Path to the audio file

    Returns:
        Dictionary with 'audio', 'duration', and 'ffprobe' keys

    Raises:
        ValueError: If audio metadata cannot be extracted
    """
    data = _run_ffprobe(file_path)
    if not data:
        raise ValueError(f"Could not extract audio metadata from {file_path}: ffprobe failed")

    metadata = {}

    # Find audio stream
    audio_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            audio_stream = stream
            break

    if audio_stream:
        audio_info = {}
        audio_info["codec"] = audio_stream.get("codec_name")

        # Basic audio properties
        with suppress(ValueError, TypeError):
            sample_rate = audio_stream.get("sample_rate")
            if sample_rate:
                audio_info["sample_rate"] = int(sample_rate)

        audio_info["channels"] = audio_stream.get("channels")

        # Get bitrate from stream or format
        bitrate = audio_stream.get("bit_rate")
        if not bitrate and "format" in data:
            bitrate = data["format"].get("bit_rate")
        if bitrate:
            with suppress(ValueError, TypeError):
                audio_info["bitrate"] = int(bitrate)

        metadata["audio"] = audio_info

    # Get duration from format (convert to milliseconds)
    if "format" in data:
        duration = data["format"].get("duration")
        if duration:
            with suppress(ValueError, TypeError):
                metadata["duration"] = float(duration) * 1000  # Convert to milliseconds

        # Extract metadata tags (title, artist, album)
        tags = data["format"].get("tags", {})
        if tags:
            audio_tags = {}
            # Handle different tag name cases
            if title := tags.get("title") or tags.get("TITLE"):
                audio_tags["title"] = title
            if artist := tags.get("artist") or tags.get("ARTIST"):
                audio_tags["artist"] = artist
            if album := tags.get("album") or tags.get("ALBUM"):
                audio_tags["album"] = album

            # Add tags to audio metadata if we have any
            if audio_tags and "audio" in metadata:
                metadata["audio"]["tags"] = audio_tags

    # Store complete ffprobe output with version
    metadata["ffprobe"] = {"version": get_cached_ffprobe_version(), "data": data}

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
    error_msg = f"Could not extract image dimensions from {file_path} using Pillow or ffprobe"
    logger.error(error_msg)
    raise ValueError(error_msg)
