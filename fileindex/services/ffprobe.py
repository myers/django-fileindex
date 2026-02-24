"""Service for ffprobe utilities and subprocess management."""

import json
import logging
import subprocess
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


def run_ffprobe(file_path: str, timeout: int = 30) -> dict[str, Any] | None:
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
