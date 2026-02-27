"""Tests that metadata TypedDicts in models.py match actual extraction output."""

import tempfile
from contextlib import suppress
from pathlib import Path
from typing import get_type_hints
from unittest.mock import patch

import pytest
from PIL import Image

from fileindex.models import (
    AudioMetadata,
    ImageMetadata,
    VideoMetadata,
)


def get_typed_dict_keys(td):
    """Get all keys defined in a TypedDict."""
    return set(get_type_hints(td).keys())


# --- Image metadata structure ---


@pytest.fixture
def create_test_image():
    """Create a temporary test image file."""
    created_files = []

    def _create(suffix=".png", size=(800, 600), color="red"):
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            img = Image.new("RGB", size, color=color)
            img.save(tmp.name)
            created_files.append(tmp.name)
            return tmp.name

    yield _create

    for filepath in created_files:
        with suppress(FileNotFoundError):
            Path(filepath).unlink()


def test_image_metadata_has_image_key():
    """ImageMetadata should have an 'image' key for nested image info."""
    keys = get_typed_dict_keys(ImageMetadata)
    assert "image" in keys, f"ImageMetadata should have 'image' key for nested structure. Has: {keys}"


def test_image_metadata_no_flat_width_height():
    """ImageMetadata should NOT have flat width/height/thumbhash at root level."""
    keys = get_typed_dict_keys(ImageMetadata)
    assert "width" not in keys, "width should be nested under 'image', not at root"
    assert "height" not in keys, "height should be nested under 'image', not at root"
    assert "thumbhash" not in keys, "thumbhash should be nested under 'image', not at root"


def test_image_metadata_has_optional_duration():
    """ImageMetadata should have 'duration' at root (for animated images)."""
    keys = get_typed_dict_keys(ImageMetadata)
    assert "duration" in keys


def test_image_extraction_conforms_to_typeddict(create_test_image):
    """Actual image extraction output should only contain keys defined in ImageMetadata."""
    from fileindex.services.image_metadata import extract_image_metadata

    tmp_path = create_test_image()
    metadata, is_corrupt = extract_image_metadata(tmp_path, "image/png")

    assert not is_corrupt
    allowed_keys = get_typed_dict_keys(ImageMetadata)
    actual_keys = set(metadata.keys())
    unexpected = actual_keys - allowed_keys
    assert not unexpected, f"Image extraction produced keys not in ImageMetadata: {unexpected}"


def test_image_extraction_image_subkeys(create_test_image):
    """The 'image' sub-dict should contain width, height, thumbhash, animated."""
    from fileindex.services.image_metadata import extract_image_metadata

    tmp_path = create_test_image()
    metadata, is_corrupt = extract_image_metadata(tmp_path, "image/png")

    assert not is_corrupt
    assert "image" in metadata
    image_info = metadata["image"]
    assert "width" in image_info
    assert "height" in image_info
    assert "thumbhash" in image_info
    assert "animated" in image_info


# --- Video metadata structure ---


def test_video_metadata_has_video_key():
    """VideoMetadata should have a 'video' key for nested stream info."""
    keys = get_typed_dict_keys(VideoMetadata)
    assert "video" in keys, f"VideoMetadata should have 'video' key. Has: {keys}"


def test_video_metadata_no_flat_dimensions():
    """VideoMetadata should NOT have flat width/height/frame_rate at root."""
    keys = get_typed_dict_keys(VideoMetadata)
    assert "width" not in keys, "width should be nested under 'video', not at root"
    assert "height" not in keys, "height should be nested under 'video', not at root"
    assert "frame_rate" not in keys, "frame_rate should be nested under 'video', not at root"


def test_video_metadata_has_mediainfo():
    """VideoMetadata should include optional 'mediainfo' key."""
    keys = get_typed_dict_keys(VideoMetadata)
    assert "mediainfo" in keys, f"VideoMetadata should have 'mediainfo' key. Has: {keys}"


@patch("fileindex.services.media_metadata.ffprobe.run_ffprobe")
@patch("fileindex.services.media_metadata._extract_mediainfo_metadata")
def test_video_extraction_conforms_to_typeddict(mock_mediainfo, mock_ffprobe):
    """Actual video extraction output should only contain keys defined in VideoMetadata."""
    from fileindex.services.media_metadata import extract_video_metadata

    mock_ffprobe.return_value = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30/1",
                "bit_rate": "5000000",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "bit_rate": "128000",
                "sample_rate": "48000",
                "channels": 2,
            },
        ],
        "format": {"duration": "60.0"},
    }
    mock_mediainfo.return_value = {"version": "24.0", "general": {"format": "MPEG-4"}}

    metadata, is_corrupt = extract_video_metadata("/fake/video.mp4")

    assert not is_corrupt
    allowed_keys = get_typed_dict_keys(VideoMetadata)
    actual_keys = set(metadata.keys())
    unexpected = actual_keys - allowed_keys
    assert not unexpected, f"Video extraction produced keys not in VideoMetadata: {unexpected}"


# --- Audio metadata structure ---


def test_audio_metadata_has_mediainfo():
    """AudioMetadata should include optional 'mediainfo' key."""
    keys = get_typed_dict_keys(AudioMetadata)
    assert "mediainfo" in keys, f"AudioMetadata should have 'mediainfo' key. Has: {keys}"


@patch("fileindex.services.media_metadata.ffprobe.run_ffprobe")
@patch("fileindex.services.media_metadata._extract_mediainfo_metadata")
def test_audio_extraction_conforms_to_typeddict(mock_mediainfo, mock_ffprobe):
    """Actual audio extraction output should only contain keys defined in AudioMetadata."""
    from fileindex.services.media_metadata import extract_audio_metadata

    mock_ffprobe.return_value = {
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "mp3",
                "sample_rate": "44100",
                "channels": 2,
                "bit_rate": "320000",
            },
        ],
        "format": {
            "duration": "180.0",
            "bit_rate": "320000",
            "tags": {"title": "Test", "artist": "Artist"},
        },
    }
    mock_mediainfo.return_value = {"version": "24.0", "general": {"format": "MPEG Audio"}}

    metadata, is_corrupt = extract_audio_metadata("/fake/audio.mp3")

    assert not is_corrupt
    allowed_keys = get_typed_dict_keys(AudioMetadata)
    actual_keys = set(metadata.keys())
    unexpected = actual_keys - allowed_keys
    assert not unexpected, f"Audio extraction produced keys not in AudioMetadata: {unexpected}"


# --- Factory metadata structure ---


@pytest.mark.django_db
def test_image_factory_metadata_matches_typeddict():
    """ImageFileFactory metadata should match ImageMetadata structure."""
    from fileindex.factories import ImageFileFactory

    image_file = ImageFileFactory()
    metadata = image_file.metadata

    assert "image" in metadata, f"ImageFileFactory metadata should have 'image' key. Has: {set(metadata.keys())}"
    assert "width" not in metadata, "ImageFileFactory should not have flat 'width'"
    assert "height" not in metadata, "ImageFileFactory should not have flat 'height'"


@pytest.mark.django_db
def test_video_factory_metadata_matches_typeddict():
    """VideoFileFactory metadata should match VideoMetadata structure."""
    from fileindex.factories import VideoFileFactory

    video_file = VideoFileFactory()
    metadata = video_file.metadata

    assert "video" in metadata, f"VideoFileFactory metadata should have 'video' key. Has: {set(metadata.keys())}"
    assert "width" not in metadata, "VideoFileFactory should not have flat 'width'"
    assert "height" not in metadata, "VideoFileFactory should not have flat 'height'"
    assert "frame_rate" not in metadata, "VideoFileFactory should not have flat 'frame_rate'"
    assert "duration" in metadata
