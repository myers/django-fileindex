"""
Django system checks for fileindex app.

This module provides system checks to verify that required external tools
are available and properly configured.
"""

from django.core.checks import Warning, register
from django.core.management.color import make_style

from fileindex.services.media_analysis import get_ffprobe_version
from fileindex.services.mediainfo_analysis import is_pymediainfo_available

style = make_style("ERROR")


@register()
def check_ffprobe_available(app_configs, **kwargs):
    """Check if ffprobe is available and functional.

    This check warns if ffprobe is not available, as it's used for
    video and audio metadata extraction.
    """
    errors = []

    try:
        version = get_ffprobe_version()
        if version is None:
            errors.append(
                Warning(
                    "ffprobe is not available or not functional",
                    hint=(
                        "Install ffmpeg/ffprobe for video and audio metadata extraction. "
                        "On macOS: brew install ffmpeg. On Ubuntu: apt install ffmpeg."
                    ),
                    id="fileindex.W001",
                )
            )
    except Exception as e:
        errors.append(
            Warning(
                f"Error checking ffprobe availability: {e}",
                hint="Ensure ffmpeg/ffprobe is properly installed and accessible.",
                id="fileindex.W002",
            )
        )

    return errors


@register()
def check_mediainfo_available(app_configs, **kwargs):
    """Check if MediaInfo (pymediainfo) is available and functional.

    This check warns if MediaInfo is not available. MediaInfo provides
    additional metadata extraction capabilities, especially useful for
    professional video formats like DV.
    """
    errors = []

    try:
        if not is_pymediainfo_available():
            errors.append(
                Warning(
                    "MediaInfo (pymediainfo) is not available or not functional",
                    hint=(
                        "Install pymediainfo for enhanced metadata extraction: "
                        "pip install pymediainfo. This provides additional metadata "
                        "for DV files and other professional video formats."
                    ),
                    id="fileindex.W003",
                )
            )
    except Exception as e:
        errors.append(
            Warning(
                f"Error checking MediaInfo availability: {e}",
                hint="Ensure pymediainfo is properly installed.",
                id="fileindex.W004",
            )
        )

    return errors
