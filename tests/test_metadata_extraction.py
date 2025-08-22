"""Tests for the metadata extraction service using pytest."""

import tempfile
from contextlib import suppress
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from fileindex.services.metadata_extraction import (
    SECONDS_TO_MS,
    THUMBHASH_MAX_SIZE,
    _extract_audio_metadata,
    _extract_image_metadata,
    _extract_video_metadata,
    extract_required_metadata,
)


@pytest.fixture
def create_test_image():
    """Fixture that returns a factory function for creating test images."""
    created_files = []

    def _create_image(
        suffix: str = ".png",
        size: tuple[int, int] = (800, 600),
        color: str = "red",
    ) -> str:
        """Create a temporary test image file.

        Args:
            suffix: File extension for the image.
            size: Width and height of the image.
            color: Color of the image.

        Returns:
            Path to the temporary image file.
        """
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            img = Image.new("RGB", size, color=color)
            img.save(tmp.name)
            created_files.append(tmp.name)
            return tmp.name

    yield _create_image

    # Cleanup all created files
    for filepath in created_files:
        with suppress(FileNotFoundError):
            Path(filepath).unlink()


@pytest.mark.django_db
class TestMetadataExtraction:
    """Test metadata extraction functions using pytest."""

    def test_extract_image_metadata_valid(self, create_test_image):
        """Test extracting metadata from a valid image."""
        # Create a test image using the fixture
        tmp_path = create_test_image(suffix=".png", size=(800, 600), color="red")

        metadata, is_corrupt = _extract_image_metadata(tmp_path, "image/png")

        assert not is_corrupt
        assert "image" in metadata
        assert metadata["image"]["width"] == 800
        assert metadata["image"]["height"] == 600
        assert "thumbhash" in metadata["image"]
        assert metadata["image"]["animated"] is False  # PNG is not animated

    def test_extract_image_metadata_invalid_dimensions(self):
        """Test handling of image with invalid dimensions."""
        with patch("fileindex.services.metadata_extraction.Image.open") as mock_open:
            mock_img = MagicMock()
            mock_img.width = 0
            mock_img.height = 0
            mock_img.__enter__.return_value = mock_img
            mock_open.return_value = mock_img

            metadata, is_corrupt = _extract_image_metadata("/fake/path.jpg", "image/jpeg")

            assert is_corrupt
            assert metadata == {}

    def test_extract_animated_image_metadata(self, create_test_image):
        """Test extracting metadata from animated image formats."""
        # Create a test GIF image
        tmp_path = create_test_image(suffix=".gif", size=(100, 100), color="blue")

        with patch("fileindex.services.metadata_extraction.media_analysis.get_duration") as mock_duration:
            mock_duration.return_value = 2.5  # 2.5 seconds

            metadata, is_corrupt = _extract_image_metadata(tmp_path, "image/gif")

            assert not is_corrupt
            assert "image" in metadata
            assert metadata["image"]["width"] == 100
            assert metadata["image"]["height"] == 100
            assert metadata["duration"] == 2500  # 2.5 * 1000 (duration at root level)
            assert metadata["image"]["animated"] is True

    def test_extract_video_metadata_valid(self):
        """Test extracting metadata from a valid video."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_video_metadata") as mock_extract:
            mock_extract.return_value = {
                "video": {
                    "codec": "h264",
                    "width": 1920,
                    "height": 1080,
                    "bitrate": 5000000,
                    "frame_rate": 30.0,
                },
                "audio": {
                    "codec": "aac",
                    "bitrate": 128000,
                    "sample_rate": 48000,
                    "channels": 2,
                },
                "duration": 120500,  # Already in ms
                "ffprobe": {"version": "4.4.2", "data": {"streams": [], "format": {}}},
            }

            metadata, is_corrupt = _extract_video_metadata("/fake/video.mp4")

            assert not is_corrupt
            assert "video" in metadata
            assert metadata["video"]["width"] == 1920
            assert metadata["video"]["height"] == 1080
            assert metadata["video"]["codec"] == "h264"
            assert metadata["video"]["bitrate"] == 5000000
            assert metadata["video"]["frame_rate"] == 30.0
            assert "audio" in metadata
            assert metadata["audio"]["codec"] == "aac"
            assert metadata["audio"]["bitrate"] == 128000
            assert metadata["duration"] == 120500
            assert "ffprobe" in metadata
            assert metadata["ffprobe"]["version"] == "4.4.2"

    def test_extract_video_metadata_missing_fields(self):
        """Test handling of video with missing required fields."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_video_metadata") as mock_extract:
            mock_extract.return_value = {
                "video": {
                    "width": 1920,
                    "height": 1080,
                    # Missing frame_rate (required)
                },
                # Missing duration (required)
            }

            metadata, is_corrupt = _extract_video_metadata("/fake/video.mp4")

            assert is_corrupt  # Missing required fields
            # With new error handling, we return empty metadata when required fields are missing
            assert metadata == {}

    def test_extract_video_metadata_invalid_values(self):
        """Test handling of video with invalid metadata values."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_video_metadata") as mock_extract:
            mock_extract.return_value = {
                "video": {
                    "width": -1,  # Invalid
                    "height": 0,  # Invalid
                    "frame_rate": 0,  # Invalid
                },
                "duration": -5000,  # Invalid (negative)
            }

            metadata, is_corrupt = _extract_video_metadata("/fake/video.mp4")

            assert is_corrupt  # Invalid dimensions and frame rate
            # With new error handling, we return empty metadata when validation fails
            assert metadata == {}

    def test_extract_video_metadata_negative_duration(self):
        """Test handling of video with negative duration but valid other fields."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_video_metadata") as mock_extract:
            mock_extract.return_value = {
                "video": {
                    "width": 1920,
                    "height": 1080,
                    "frame_rate": 30.0,
                },
                "duration": -1000,  # Invalid (negative)
            }

            metadata, is_corrupt = _extract_video_metadata("/fake/video.mp4")

            assert is_corrupt  # Invalid duration
            assert metadata == {}

    def test_extract_audio_metadata_valid(self):
        """Test extracting metadata from a valid audio file."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_audio_metadata") as mock_extract:
            mock_extract.return_value = {
                "audio": {
                    "codec": "mp3",
                    "bitrate": 320000,
                    "sample_rate": 44100,
                    "channels": 2,
                    "tags": {"title": "Test Song", "artist": "Test Artist", "album": "Test Album"},
                },
                "duration": 180750,  # Already in ms
                "ffprobe": {"version": "4.4.2", "data": {"streams": [], "format": {}}},
            }

            metadata, is_corrupt = _extract_audio_metadata("/fake/audio.mp3")

            assert not is_corrupt
            assert "audio" in metadata
            assert metadata["audio"]["codec"] == "mp3"
            assert metadata["audio"]["bitrate"] == 320000
            assert metadata["audio"]["tags"]["title"] == "Test Song"
            assert metadata["duration"] == 180750
            assert "ffprobe" in metadata

    def test_extract_audio_metadata_missing_duration(self):
        """Test handling of audio with missing duration."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_audio_metadata") as mock_extract:
            mock_extract.return_value = {
                "audio": {
                    "codec": "mp3",
                    "bitrate": 128000,
                },
                # Missing duration (required)
            }

            metadata, is_corrupt = _extract_audio_metadata("/fake/audio.mp3")

            assert is_corrupt  # Missing required duration
            # With new error handling, we return empty metadata when required fields are missing
            assert metadata == {}

    def test_extract_audio_metadata_invalid_duration(self):
        """Test handling of audio with invalid duration."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_audio_metadata") as mock_extract:
            mock_extract.return_value = {
                "audio": {
                    "codec": "mp3",
                },
                "duration": -10000,  # Invalid (negative)
            }

            metadata, is_corrupt = _extract_audio_metadata("/fake/audio.mp3")

            # With new validation, negative duration is rejected
            assert is_corrupt
            assert metadata == {}

    def test_extract_required_metadata_image(self, create_test_image):
        """Test main extraction function with image."""
        tmp_path = create_test_image(suffix=".jpg", size=(640, 480), color="green")

        metadata, is_corrupt = extract_required_metadata("image/jpeg", tmp_path)

        assert not is_corrupt
        assert "image" in metadata
        assert metadata["image"]["width"] == 640
        assert metadata["image"]["height"] == 480
        assert "thumbhash" in metadata["image"]

    def test_extract_required_metadata_video(self):
        """Test main extraction function with video."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_video_metadata") as mock_extract:
            mock_extract.return_value = {
                "video": {
                    "codec": "h264",
                    "width": 1280,
                    "height": 720,
                    "frame_rate": 24.0,
                },
                "duration": 60000,  # Already in ms
                "ffprobe": {"version": "4.4.2", "data": {}},
            }

            metadata, is_corrupt = extract_required_metadata("video/mp4", "/fake/video.mp4")

            assert not is_corrupt
            assert "video" in metadata
            assert metadata["video"]["width"] == 1280
            assert metadata["video"]["height"] == 720
            assert metadata["video"]["frame_rate"] == 24.0
            assert metadata["duration"] == 60000

    def test_extract_required_metadata_audio(self):
        """Test main extraction function with audio."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_audio_metadata") as mock_extract:
            mock_extract.return_value = {
                "audio": {
                    "codec": "mp3",
                    "bitrate": 192000,
                },
                "duration": 240000,  # Already in ms
                "ffprobe": {"version": "4.4.2", "data": {}},
            }

            metadata, is_corrupt = extract_required_metadata("audio/mpeg", "/fake/audio.mp3")

            assert not is_corrupt
            assert "audio" in metadata
            assert metadata["audio"]["codec"] == "mp3"
            assert metadata["duration"] == 240000

    def test_extract_required_metadata_unknown_type(self):
        """Test main extraction function with unknown file type."""
        metadata, is_corrupt = extract_required_metadata("application/pdf", "/fake/document.pdf")

        assert not is_corrupt
        assert metadata == {}

    def test_extract_required_metadata_none_mime_type(self):
        """Test main extraction function with None mime type."""
        metadata, is_corrupt = extract_required_metadata(None, "/fake/file")

        assert not is_corrupt
        assert metadata == {}

    def test_extract_required_metadata_exception_handling(self):
        """Test exception handling in main extraction function."""
        with patch("fileindex.services.metadata_extraction.Image.open") as mock_open:
            mock_open.side_effect = Exception("Test error")

            metadata, is_corrupt = extract_required_metadata("image/jpeg", "/fake/image.jpg")

            assert is_corrupt
            assert metadata == {}

    def test_thumbhash_max_size_constant(self):
        """Test that THUMBHASH_MAX_SIZE constant is properly defined."""
        assert THUMBHASH_MAX_SIZE == (100, 100)

    def test_seconds_to_ms_constant(self):
        """Test that SECONDS_TO_MS constant is properly defined."""
        assert SECONDS_TO_MS == 1000

    def test_thumbhash_bytes_handling(self, create_test_image):
        """Test that thumbhash handles both bytes and string return types."""
        tmp_path = create_test_image(suffix=".png", size=(50, 50), color="yellow")

        # Test with bytes return
        with patch("fileindex.services.metadata_extraction.image_to_thumbhash") as mock_thumbhash:
            mock_thumbhash.return_value = b"\x01\x02\x03"

            metadata, is_corrupt = _extract_image_metadata(tmp_path, "image/png")

            assert not is_corrupt
            assert metadata["image"]["thumbhash"] == "010203"

        # Test with string return
        with patch("fileindex.services.metadata_extraction.image_to_thumbhash") as mock_thumbhash:
            mock_thumbhash.return_value = "abcdef"

            metadata, is_corrupt = _extract_image_metadata(tmp_path, "image/png")

            assert not is_corrupt
            assert metadata["image"]["thumbhash"] == "abcdef"
