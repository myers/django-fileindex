"""
Service functions for media file analysis using pymediainfo (MediaInfo library).

This module provides functions to extract rich metadata from media files using
the MediaInfo library via pymediainfo. It complements the existing ffprobe-based
extraction with additional metadata, especially useful for professional video
formats like DV tapes.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Global flag to track if pymediainfo is available
_pymediainfo_available: Optional[bool] = None


def is_pymediainfo_available() -> bool:
    """Check if pymediainfo is available and functional.
    
    Returns:
        True if pymediainfo can be imported and used, False otherwise
    """
    global _pymediainfo_available
    
    if _pymediainfo_available is not None:
        return _pymediainfo_available
    
    try:
        from pymediainfo import MediaInfo
        # Try a simple operation to verify it works
        MediaInfo.can_parse()
        _pymediainfo_available = True
        logger.debug("pymediainfo is available and functional")
    except ImportError:
        logger.warning("pymediainfo is not installed")
        _pymediainfo_available = False
    except Exception as e:
        logger.warning(f"pymediainfo is installed but not functional: {e}")
        _pymediainfo_available = False
    
    return _pymediainfo_available


def extract_mediainfo_metadata(file_path: str) -> Dict[str, Any]:
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
        from pymediainfo import MediaInfo
        
        # Parse the media file
        media_info = MediaInfo.parse(file_path)
        
        # Convert tracks to dictionaries
        tracks = []
        for track in media_info.tracks:
            track_data = {"track_type": track.track_type}
            
            # Add all available attributes to the track data
            for attr_name in dir(track):
                # Skip private attributes and methods
                if attr_name.startswith('_') or callable(getattr(track, attr_name)):
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
        
        return {
            "tracks": tracks,
            "version": version
        }
        
    except Exception as e:
        error_msg = f"Failed to extract MediaInfo metadata from {file_path}: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)


def get_mediainfo_for_video(file_path: str) -> Dict[str, Any]:
    """Extract video-specific metadata using MediaInfo.
    
    This function extracts metadata specifically useful for video files,
    with special attention to DV format metadata.
    
    Args:
        file_path: Path to the video file
        
    Returns:
        Dictionary with MediaInfo data, empty if extraction fails
    """
    try:
        return extract_mediainfo_metadata(file_path)
    except (ImportError, ValueError) as e:
        logger.warning(f"Could not extract MediaInfo metadata: {e}")
        return {}


def get_mediainfo_for_audio(file_path: str) -> Dict[str, Any]:
    """Extract audio-specific metadata using MediaInfo.
    
    Args:
        file_path: Path to the audio file
        
    Returns:
        Dictionary with MediaInfo data, empty if extraction fails
    """
    try:
        return extract_mediainfo_metadata(file_path)
    except (ImportError, ValueError) as e:
        logger.warning(f"Could not extract MediaInfo metadata: {e}")
        return {}


def get_mediainfo_for_image(file_path: str) -> Dict[str, Any]:
    """Extract image-specific metadata using MediaInfo.
    
    Args:
        file_path: Path to the image file
        
    Returns:
        Dictionary with MediaInfo data, empty if extraction fails
    """
    try:
        return extract_mediainfo_metadata(file_path)
    except (ImportError, ValueError) as e:
        logger.warning(f"Could not extract MediaInfo metadata: {e}")
        return {}


def find_dv_recording_date(mediainfo_data: Dict[str, Any]) -> Optional[str]:
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


def find_dv_timecode(mediainfo_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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


def find_commercial_format(mediainfo_data: Dict[str, Any]) -> Optional[str]:
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