"""Service for extracting metadata from video and audio files using ffprobe and MediaInfo."""

import logging
from contextlib import suppress
from typing import Any

from fileindex.services import ffprobe

# Type alias for metadata dictionary using Python 3.11 compatible syntax
FileMetadata = dict[str, Any]

logger = logging.getLogger(__name__)


def extract_video_metadata(file_path: str) -> tuple[FileMetadata, bool]:
    """Extract metadata from video files using ffprobe and MediaInfo.

    Args:
        file_path: Path to the video file.

    Returns:
        Tuple of (metadata dict, is_corrupt flag).
    """
    metadata: FileMetadata = {}
    is_corrupt = False

    try:
        # Call ffprobe once and get all data
        ffprobe_data = ffprobe.run_ffprobe(file_path)
        if not ffprobe_data:
            logger.warning(f"ffprobe failed for video file {file_path}")
            return {}, True

        # Extract video metadata from ffprobe data
        video_metadata = _extract_video_metadata_from_ffprobe(ffprobe_data, file_path)

        # Check for required video stream first
        if "video" not in video_metadata:
            logger.warning(f"No video stream found in {file_path}")
            return {}, True

        # Validate required video fields before copying
        video = video_metadata["video"]
        if not (video.get("width") and video.get("height") and video.get("width") > 0 and video.get("height") > 0):
            logger.warning(f"Invalid video dimensions for {file_path}")
            return {}, True

        # Frame rate is required for video
        if not video.get("frame_rate") or video.get("frame_rate") <= 0:
            logger.warning(f"Missing or invalid frame rate for video {file_path}")
            return {}, True

        # Check for required duration and validate it's positive
        if "duration" not in video_metadata or video_metadata["duration"] <= 0:
            logger.warning(f"Missing or invalid duration for video {file_path}")
            return {}, True

        # All required fields are valid, copy the metadata
        metadata["video"] = video_metadata["video"]
        metadata["duration"] = video_metadata["duration"]

        # Copy optional fields
        if "audio" in video_metadata:
            metadata["audio"] = video_metadata["audio"]

        if "ffprobe" in video_metadata:
            metadata["ffprobe"] = video_metadata["ffprobe"]

        # Extract filtered MediaInfo metadata (supplemental to ffprobe)
        mediainfo_data = _extract_mediainfo_metadata(file_path)
        if mediainfo_data:
            metadata["mediainfo"] = mediainfo_data

    except Exception as e:
        logger.error(f"Failed to extract video metadata from {file_path}: {e}")
        is_corrupt = True

    return metadata, is_corrupt


def extract_audio_metadata(file_path: str) -> tuple[FileMetadata, bool]:
    """Extract metadata from audio files using ffprobe and MediaInfo.

    Args:
        file_path: Path to the audio file.

    Returns:
        Tuple of (metadata dict, is_corrupt flag).
    """
    metadata: FileMetadata = {}
    is_corrupt = False

    try:
        # Call ffprobe once and get all data
        ffprobe_data = ffprobe.run_ffprobe(file_path)
        if not ffprobe_data:
            logger.warning(f"ffprobe failed for audio file {file_path}")
            return {}, True

        # Extract audio metadata from ffprobe data
        audio_metadata = _extract_audio_metadata_from_ffprobe(ffprobe_data, file_path)

        # Check for required duration and validate it's positive
        if "duration" not in audio_metadata or audio_metadata["duration"] <= 0:
            logger.warning(f"Missing or invalid duration for audio {file_path}")
            return {}, True

        # Duration is valid, copy all metadata
        metadata["duration"] = audio_metadata["duration"]

        # Copy audio info if present
        if "audio" in audio_metadata:
            metadata["audio"] = audio_metadata["audio"]

        # Copy ffprobe data if present
        if "ffprobe" in audio_metadata:
            metadata["ffprobe"] = audio_metadata["ffprobe"]

        # Extract filtered MediaInfo metadata (supplemental to ffprobe)
        mediainfo_data = _extract_mediainfo_metadata(file_path)
        if mediainfo_data:
            metadata["mediainfo"] = mediainfo_data

    except Exception as e:
        logger.error(f"Failed to extract audio metadata from {file_path}: {e}")
        is_corrupt = True

    return metadata, is_corrupt


def _extract_video_metadata_from_ffprobe(data: dict[str, Any], file_path: str) -> dict[str, Any]:
    """Extract video metadata from ffprobe JSON data.

    Args:
        data: Parsed JSON output from ffprobe
        file_path: Path to the video file (for logging)

    Returns:
        Dictionary with 'video', 'audio', 'duration', and 'ffprobe' keys
    """
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
    metadata["ffprobe"] = {"version": ffprobe.get_cached_ffprobe_version(), "data": data}

    return metadata


def _extract_audio_metadata_from_ffprobe(data: dict[str, Any], file_path: str) -> dict[str, Any]:
    """Extract audio metadata from ffprobe JSON data.

    Args:
        data: Parsed JSON output from ffprobe
        file_path: Path to the audio file (for logging)

    Returns:
        Dictionary with 'audio', 'duration', and 'ffprobe' keys
    """
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
    metadata["ffprobe"] = {"version": ffprobe.get_cached_ffprobe_version(), "data": data}

    return metadata


def _extract_mediainfo_metadata(file_path: str) -> dict[str, Any] | None:
    """Extract filtered MediaInfo metadata.

    Args:
        file_path: Path to the media file

    Returns:
        Filtered MediaInfo metadata dict or None if unavailable
    """
    try:
        from fileindex.services import mediainfo_analysis

        mediainfo_data = mediainfo_analysis.extract_filtered_mediainfo_metadata(file_path)
        # Return data if it has more than just version info
        if mediainfo_data and len(mediainfo_data) > 1:
            return mediainfo_data
    except (ImportError, ValueError) as e:
        logger.warning(f"Could not extract MediaInfo metadata: {e}")

    return None
