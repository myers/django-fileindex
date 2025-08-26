"""
Service functions for media file analysis using pymediainfo (MediaInfo library).

This module provides functions to extract rich metadata from media files using
the MediaInfo library via pymediainfo. It complements the existing ffprobe-based
extraction with additional metadata, especially useful for professional video
formats like DV tapes.
"""

import logging
from pathlib import Path
from typing import Any

try:
    from pymediainfo import MediaInfo
except ImportError:
    MediaInfo = None

logger = logging.getLogger(__name__)

# Global flag to track if pymediainfo is available
_pymediainfo_available: bool | None = None


def is_pymediainfo_available() -> bool:
    """Check if pymediainfo is available and functional.

    Returns:
        True if pymediainfo can be imported and used, False otherwise
    """
    global _pymediainfo_available

    if _pymediainfo_available is not None:
        return _pymediainfo_available

    if MediaInfo is None:
        logger.warning("pymediainfo is not installed")
        _pymediainfo_available = False
    else:
        try:
            # Try a simple operation to verify it works
            MediaInfo.can_parse()
            _pymediainfo_available = True
            logger.debug("pymediainfo is available and functional")
        except Exception as e:
            logger.warning(f"pymediainfo is installed but not functional: {e}")
            _pymediainfo_available = False

    return _pymediainfo_available


def extract_mediainfo_metadata(file_path: str) -> dict[str, Any]:
    """Extract metadata using pymediainfo (MediaInfo library).

    Args:
        file_path: Path to the media file

    Returns:
        Dictionary containing MediaInfo metadata with structure:
        {
            "tracks": [
                {"track_type": "General", "duration": 5000, ...},
                {"track_type": "Video", "width": 720, ...},
                {"track_type": "Audio", "channels": 2, ...}
            ],
            "version": "MediaInfo version string"
        }

    Raises:
        ValueError: If metadata extraction fails
        ImportError: If pymediainfo is not available
    """
    if not is_pymediainfo_available():
        raise ImportError("pymediainfo is not available")

    if not Path(file_path).exists():
        raise ValueError(f"File does not exist: {file_path}")

    try:
        # Parse the media file
        media_info = MediaInfo.parse(file_path)

        # Convert tracks to dictionaries
        tracks = []
        for track in media_info.tracks:
            track_data = {"track_type": track.track_type}

            # Add all available attributes to the track data
            for attr_name in dir(track):
                # Skip private attributes and methods
                if attr_name.startswith("_") or callable(getattr(track, attr_name)):
                    continue

                attr_value = getattr(track, attr_name)
                # Only include attributes that have values
                if attr_value is not None:
                    track_data[attr_name] = attr_value

            tracks.append(track_data)

        # Get MediaInfo version
        try:
            version = MediaInfo.version
        except AttributeError:
            version = "unknown"

        return {"tracks": tracks, "version": version}

    except Exception as e:
        error_msg = f"Failed to extract MediaInfo metadata from {file_path}: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg) from e


def find_dv_recording_date(mediainfo_data: dict[str, Any]) -> str | None:
    """Extract DV recording date from MediaInfo data.

    DV tapes embed the actual recording date/time in the video stream,
    which is different from file creation/modification dates.

    Args:
        mediainfo_data: Output from extract_mediainfo_metadata()

    Returns:
        ISO format date string (e.g. "2004-10-04 14:43:30") or None
    """
    if not mediainfo_data or "tracks" not in mediainfo_data:
        return None

    for track in mediainfo_data["tracks"]:
        if track.get("track_type") == "General":
            # Look for recorded date (actual recording time)
            recorded_date = track.get("recorded_date")
            if recorded_date:
                return str(recorded_date)

    return None


def find_dv_timecode(mediainfo_data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract SMPTE timecode information from DV MediaInfo data.

    Args:
        mediainfo_data: Output from extract_mediainfo_metadata()

    Returns:
        Dictionary with timecode info or None
        Example: {"timecode": "00:00:00;06", "timecode_source": "DV", "drop_frame": True}
    """
    if not mediainfo_data or "tracks" not in mediainfo_data:
        return None

    timecode_info = {}

    for track in mediainfo_data["tracks"]:
        if track.get("track_type") == "Video":
            # Look for various timecode fields
            if "timecode" in track:
                timecode_info["timecode"] = track["timecode"]
            if "timecode_source" in track:
                timecode_info["timecode_source"] = track["timecode_source"]
            if "frame_rate_mode" in track:
                timecode_info["frame_rate_mode"] = track["frame_rate_mode"]
            if "scan_type" in track:
                timecode_info["scan_type"] = track["scan_type"]
            if "scan_order" in track:
                timecode_info["scan_order"] = track["scan_order"]

    return timecode_info if timecode_info else None


def find_commercial_format(mediainfo_data: dict[str, Any]) -> str | None:
    """Extract commercial format name from MediaInfo data.

    For DV files, this identifies specific variants like DVCPRO, DVCAM, MiniDV.

    Args:
        mediainfo_data: Output from extract_mediainfo_metadata()

    Returns:
        Commercial format string or None
    """
    if not mediainfo_data or "tracks" not in mediainfo_data:
        return None

    for track in mediainfo_data["tracks"]:
        if track.get("track_type") == "Video":
            # Look for commercial format
            commercial_format = track.get("commercial_name")
            if commercial_format:
                return str(commercial_format)

            # Fallback to format field
            format_name = track.get("format")
            if format_name:
                return str(format_name)

    return None


# Essential field definitions for filtering MediaInfo data
ESSENTIAL_GENERAL_FIELDS = [
    "format",
    "commercial_name",
    "duration",
    "recorded_date",
    "frame_rate",
    "frame_count",
    "overall_bit_rate",
    "overall_bit_rate_mode",
]

ESSENTIAL_VIDEO_FIELDS = [
    "format",
    "commercial_name",
    "codec_id",
    "width",
    "height",
    "time_code_of_first_frame",
    "time_code_source",
    "scan_type",
    "scan_order",
    "standard",
    "encoding_settings",
    "bit_rate",
    "frame_rate",
    "frame_rate_mode",
    "delay",
    "chroma_subsampling",
    "bit_depth",
]

ESSENTIAL_AUDIO_FIELDS = [
    "format",
    "codec_id",
    "channel_s",
    "sampling_rate",
    "bit_depth",
    "bit_rate",
    "bit_rate_mode",
    "muxing_mode",
    "delay",
    "stream_identifier",
    "track_id",
]


def normalize_recorded_date(date_str: str) -> str:
    """Convert MediaInfo date format to ISO 8601 naive datetime.

    Args:
        date_str: Date string from MediaInfo (e.g., "2004-10-04 14:43:30.000")

    Returns:
        ISO 8601 formatted naive datetime string (e.g., "2004-10-04T14:43:30.000")

    Note:
        The returned datetime is naive (no timezone info) because DV cameras
        record whatever local time is set on the camera's internal clock,
        without any timezone awareness.
    """
    if not date_str or not isinstance(date_str, str):
        return date_str

    # Replace space with T for proper ISO 8601 format (but keep it naive)
    if " " in date_str and "T" not in date_str:
        return date_str.replace(" ", "T")
    return date_str


def extract_filtered_mediainfo_metadata(file_path: str) -> dict[str, Any]:
    """Extract filtered MediaInfo metadata keeping only essential information.

    Args:
        file_path: Path to the media file

    Returns:
        Dictionary containing filtered MediaInfo metadata with structure:
        {
            "general": {...essential general metadata...},
            "video": {...essential video metadata...},
            "audio_streams": [...essential audio metadata...],
            "version": "MediaInfo version string"
        }

    Raises:
        ValueError: If metadata extraction fails
        ImportError: If pymediainfo is not available
    """
    # Get raw MediaInfo data
    raw_data = extract_mediainfo_metadata(file_path)

    filtered_data = {"version": raw_data.get("version", "unknown")}

    if "tracks" not in raw_data:
        return filtered_data

    # Process each track type
    general_info = {}
    video_info = {}
    audio_streams = []

    for track in raw_data["tracks"]:
        track_type = track.get("track_type")

        if track_type == "General":
            # Extract essential general information
            for field in ESSENTIAL_GENERAL_FIELDS:
                if field in track:
                    value = track[field]
                    # Normalize recorded_date to ISO 8601 format
                    if field == "recorded_date":
                        value = normalize_recorded_date(value)
                    general_info[field] = value

        elif track_type == "Video":
            # Extract essential video information
            for field in ESSENTIAL_VIDEO_FIELDS:
                if field in track:
                    video_info[field] = track[field]

        elif track_type == "Audio":
            # Extract essential audio information
            audio_info = {}
            for field in ESSENTIAL_AUDIO_FIELDS:
                if field in track:
                    audio_info[field] = track[field]

            # Only include audio streams that have meaningful data
            if audio_info:
                audio_streams.append(audio_info)

    # Add sections only if they contain data
    if general_info:
        filtered_data["general"] = general_info
    if video_info:
        filtered_data["video"] = video_info
    if audio_streams:
        filtered_data["audio_streams"] = audio_streams

    return filtered_data
