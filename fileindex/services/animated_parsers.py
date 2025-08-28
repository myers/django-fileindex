"""Custom parsers for extracting duration from animated image formats.

These parsers handle formats where Pillow doesn't provide duration metadata.
Optimized for streaming file access and minimal memory usage.
"""

import logging
import struct
from typing import BinaryIO, Final

logger = logging.getLogger(__name__)

# Constants
WEBP_SIGNATURE: Final[bytes] = b"WEBP"
RIFF_SIGNATURE: Final[bytes] = b"RIFF"
AVIF_FTYP: Final[bytes] = b"ftyp"

# Buffer sizes for streaming
AVIF_SEARCH_BUFFER_SIZE: Final[int] = 8192  # 8KB chunks for searching mvhd
WEBP_CHUNK_HEADER_SIZE: Final[int] = 8
ANMF_MIN_DATA_SIZE: Final[int] = 16


def parse_avif_duration(file_path: str) -> int | None:
    """Extract total duration from AVIF file using ISOBMFF box structure.

    AVIF files use the ISOBMFF/HEIF container format. Duration is stored in
    the mvhd (movie header) box with an associated timescale.
    Uses streaming approach to handle large files efficiently.

    Args:
        file_path: Path to the AVIF file

    Returns:
        Total duration in milliseconds or None if not animated/error
    """
    try:
        with open(file_path, "rb") as f:
            return _parse_avif_duration_streaming(f, file_path)
    except Exception as e:
        logger.error(f"Failed to parse AVIF duration from {file_path}: {e}")
        return None


def _parse_avif_duration_streaming(f: BinaryIO, file_path: str) -> int | None:
    """Stream-based AVIF duration parsing to avoid loading entire file into memory."""
    mvhd_pos = _find_mvhd_box_streaming(f)
    if mvhd_pos == -1:
        logger.debug(f"No mvhd box found in {file_path}, likely not animated")
        return None

    # Seek to mvhd box start
    f.seek(mvhd_pos)

    # Read mvhd box header and version info
    mvhd_header = f.read(8)  # 4 bytes 'mvhd' + 1 byte version + 3 bytes flags
    if len(mvhd_header) < 8:
        logger.warning(f"Incomplete mvhd header in {file_path}")
        return None

    version = mvhd_header[4]

    # Skip creation and modification times, then read timescale and duration
    if version == 0:
        # Skip 32-bit creation and modification times
        f.seek(8, 1)
        timescale_duration = f.read(8)  # 4 bytes timescale + 4 bytes duration
        if len(timescale_duration) < 8:
            logger.warning(f"Incomplete timescale/duration in {file_path}")
            return None
        timescale = struct.unpack(">I", timescale_duration[:4])[0]
        duration = struct.unpack(">I", timescale_duration[4:8])[0]
    elif version == 1:
        # Skip 64-bit creation and modification times
        f.seek(16, 1)
        timescale_duration = f.read(12)  # 4 bytes timescale + 8 bytes duration
        if len(timescale_duration) < 12:
            logger.warning(f"Incomplete timescale/duration in {file_path}")
            return None
        timescale = struct.unpack(">I", timescale_duration[:4])[0]
        duration = struct.unpack(">Q", timescale_duration[4:12])[0]
    else:
        logger.warning(f"Unknown mvhd version {version} in {file_path}")
        return None

    if timescale == 0:
        logger.warning(f"Invalid timescale (0) in {file_path}")
        return None

    # Calculate duration in milliseconds
    duration_ms = int(duration * 1000 / timescale)

    if duration_ms > 0:
        logger.debug(f"AVIF duration: {duration_ms}ms (timescale: {timescale})")
        return duration_ms
    else:
        return None


def _find_mvhd_box_streaming(f: BinaryIO) -> int:
    """Find mvhd box position using streaming search to avoid loading entire file."""
    f.seek(0)
    buffer = b""
    position = 0

    while True:
        chunk = f.read(AVIF_SEARCH_BUFFER_SIZE)
        if not chunk:
            break

        # Combine with previous partial buffer
        search_data = buffer + chunk

        # Look for mvhd pattern
        mvhd_offset = search_data.find(b"mvhd")
        if mvhd_offset != -1:
            return position + mvhd_offset

        # Keep last few bytes for next search in case mvhd spans chunks
        buffer = search_data[-8:] if len(search_data) >= 8 else search_data
        position += len(chunk)

    return -1


def parse_webp_duration(file_path: str) -> int | None:
    """Extract total duration from animated WebP file.

    WebP uses RIFF container format. Animated WebP files contain ANMF chunks
    with frame durations stored as 24-bit values.
    Uses streaming approach with early exit optimization.

    Args:
        file_path: Path to the WebP file

    Returns:
        Total duration in milliseconds or None if not animated/error
    """
    try:
        with open(file_path, "rb") as f:
            return _parse_webp_duration_streaming(f, file_path)
    except Exception as e:
        logger.error(f"Failed to parse WebP duration from {file_path}: {e}")
        return None


def _parse_webp_duration_streaming(f: BinaryIO, file_path: str) -> int | None:
    """Stream-based WebP duration parsing with early exit optimization."""
    # Validate RIFF/WebP headers
    if not _validate_webp_headers(f, file_path):
        return None

    total_duration = 0
    frame_count = 0
    has_anim_chunk = False

    # Parse chunks with early exit optimization
    while True:
        chunk_header = f.read(WEBP_CHUNK_HEADER_SIZE)
        if len(chunk_header) < WEBP_CHUNK_HEADER_SIZE:
            break

        chunk_fourcc = chunk_header[:4]
        chunk_size = struct.unpack("<I", chunk_header[4:8])[0]

        if chunk_fourcc == b"ANIM":
            # Animation parameters chunk - confirms this is animated WebP
            has_anim_chunk = True
            f.seek(chunk_size, 1)  # Skip ANIM data
        elif chunk_fourcc == b"ANMF":
            # Animation frame chunk
            frame_duration = _parse_anmf_chunk_duration(f, chunk_size, file_path)
            if frame_duration is not None:
                total_duration += frame_duration
                frame_count += 1
            else:
                # Skip remaining chunk data if parsing failed
                f.seek(chunk_size, 1)
        else:
            # Skip non-animation chunks
            f.seek(chunk_size, 1)

        # Align to even boundary if necessary
        if chunk_size % 2 == 1:
            f.seek(1, 1)

        # Early exit optimization: if we found animation frames but no ANIM chunk,
        # we likely have enough info for a basic animated WebP
        if frame_count > 1 and total_duration > 0 and not has_anim_chunk:
            # Continue parsing to get complete duration, but we know it's animated
            pass

    # Only return duration if we found multiple animated frames
    if frame_count > 1 and total_duration > 0:
        logger.debug(f"WebP duration: {total_duration}ms ({frame_count} frames)")
        return total_duration
    else:
        logger.debug(f"WebP not animated or no duration found: {frame_count} frames, {total_duration}ms")
        return None


def _validate_webp_headers(f: BinaryIO, file_path: str) -> bool:
    """Validate RIFF and WebP headers efficiently."""
    f.seek(0)

    # Check RIFF header (first 4 bytes)
    riff_header = f.read(4)
    if riff_header != RIFF_SIGNATURE:
        logger.warning(f"Not a RIFF file: {file_path}")
        return False

    # Skip file size (4 bytes)
    f.seek(4, 1)

    # Check WebP signature (next 4 bytes)
    webp_sig = f.read(4)
    if webp_sig != WEBP_SIGNATURE:
        logger.warning(f"Not a WebP file: {file_path}")
        return False

    return True


def _parse_anmf_chunk_duration(f: BinaryIO, chunk_size: int, file_path: str) -> int | None:
    """Parse duration from ANMF chunk efficiently."""
    # ANMF chunk structure:
    # 0-2: Frame X
    # 3-5: Frame Y
    # 6-8: Frame Width minus 1
    # 9-11: Frame Height minus 1
    # 12-14: Frame Duration (24-bit, little-endian)
    # 15: Flags

    # We only need bytes 12-14 for duration, but read minimum required
    anmf_data = f.read(min(chunk_size, ANMF_MIN_DATA_SIZE))

    if len(anmf_data) >= 15:
        # Extract 24-bit duration (bytes 12-14)
        duration_bytes = anmf_data[12:15] + b"\x00"  # Add padding for 32-bit unpack
        try:
            frame_duration = struct.unpack("<I", duration_bytes)[0]

            # Skip rest of chunk data
            remaining = chunk_size - len(anmf_data)
            if remaining > 0:
                f.seek(remaining, 1)

            return frame_duration
        except struct.error as e:
            logger.warning(f"Failed to unpack ANMF duration in {file_path}: {e}")
    else:
        logger.warning(f"ANMF chunk too small in {file_path}: {len(anmf_data)} bytes")

    # Skip rest of chunk if parsing failed
    remaining = chunk_size - len(anmf_data)
    if remaining > 0:
        f.seek(remaining, 1)

    return None
