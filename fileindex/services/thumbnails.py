"""Service for generating thumbnails from video files."""

import contextlib
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


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
