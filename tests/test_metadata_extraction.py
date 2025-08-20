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
        assert metadata["width"] == 800
        assert metadata["height"] == 600
        assert "thumbhash" in metadata
        assert "animated" not in metadata  # PNG is not animated

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
            assert metadata["width"] == 100
            assert metadata["height"] == 100
            assert metadata["duration"] == 2500  # 2.5 * 1000
            assert metadata["animated"] is True

    def test_extract_video_metadata_valid(self):
        """Test extracting metadata from a valid video."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_video_metadata") as mock_extract:
            mock_extract.return_value = {
                "width": 1920,
                "height": 1080,
                "duration": 120.5,
                "frame_rate": 30.0,
            }

            metadata, is_corrupt = _extract_video_metadata("/fake/video.mp4")

            assert not is_corrupt
            assert metadata["width"] == 1920
            assert metadata["height"] == 1080
            assert metadata["duration"] == 120500  # 120.5 * 1000
            assert metadata["frame_rate"] == 30.0

    def test_extract_video_metadata_missing_fields(self):
        """Test handling of video with missing required fields."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_video_metadata") as mock_extract:
            mock_extract.return_value = {
                "width": 1920,
                "height": 1080,
                # Missing duration and frame_rate
            }

            metadata, is_corrupt = _extract_video_metadata("/fake/video.mp4")

            assert is_corrupt
            assert metadata["width"] == 1920
            assert metadata["height"] == 1080
            assert "duration" not in metadata
            assert "frame_rate" not in metadata

    def test_extract_video_metadata_invalid_values(self):
        """Test handling of video with invalid metadata values."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_video_metadata") as mock_extract:
            mock_extract.return_value = {
                "width": -1,  # Invalid
                "height": 0,  # Invalid
                "duration": -5,  # Invalid
                "frame_rate": 0,  # Invalid
            }

            metadata, is_corrupt = _extract_video_metadata("/fake/video.mp4")

            assert is_corrupt
            # No valid values should be included
            assert "width" not in metadata
            assert "height" not in metadata
            assert "duration" not in metadata
            assert "frame_rate" not in metadata

    def test_extract_audio_metadata_valid(self):
        """Test extracting metadata from a valid audio file."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_audio_metadata") as mock_extract:
            mock_extract.return_value = {
                "duration": 180.75,
            }

            metadata, is_corrupt = _extract_audio_metadata("/fake/audio.mp3")

            assert not is_corrupt
            assert metadata["duration"] == 180750  # 180.75 * 1000

    def test_extract_audio_metadata_missing_duration(self):
        """Test handling of audio with missing duration."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_audio_metadata") as mock_extract:
            mock_extract.return_value = {}

            metadata, is_corrupt = _extract_audio_metadata("/fake/audio.mp3")

            assert is_corrupt
            assert "duration" not in metadata

    def test_extract_audio_metadata_invalid_duration(self):
        """Test handling of audio with invalid duration."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_audio_metadata") as mock_extract:
            mock_extract.return_value = {
                "duration": -10,  # Invalid
            }

            metadata, is_corrupt = _extract_audio_metadata("/fake/audio.mp3")

            assert is_corrupt
            assert "duration" not in metadata

    def test_extract_required_metadata_image(self, create_test_image):
        """Test main extraction function with image."""
        tmp_path = create_test_image(suffix=".jpg", size=(640, 480), color="green")

        metadata, is_corrupt = extract_required_metadata("image/jpeg", tmp_path)

        assert not is_corrupt
        assert metadata["width"] == 640
        assert metadata["height"] == 480
        assert "thumbhash" in metadata

    def test_extract_required_metadata_video(self):
        """Test main extraction function with video."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_video_metadata") as mock_extract:
            mock_extract.return_value = {
                "width": 1280,
                "height": 720,
                "duration": 60.0,
                "frame_rate": 24.0,
            }

            metadata, is_corrupt = extract_required_metadata("video/mp4", "/fake/video.mp4")

            assert not is_corrupt
            assert metadata["width"] == 1280
            assert metadata["height"] == 720
            assert metadata["duration"] == 60000
            assert metadata["frame_rate"] == 24.0

    def test_extract_required_metadata_audio(self):
        """Test main extraction function with audio."""
        with patch("fileindex.services.metadata_extraction.media_analysis.extract_audio_metadata") as mock_extract:
            mock_extract.return_value = {
                "duration": 240.0,
            }

            metadata, is_corrupt = extract_required_metadata("audio/mpeg", "/fake/audio.mp3")

            assert not is_corrupt
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
            assert metadata["thumbhash"] == "010203"

        # Test with string return
        with patch("fileindex.services.metadata_extraction.image_to_thumbhash") as mock_thumbhash:
            mock_thumbhash.return_value = "abcdef"

            metadata, is_corrupt = _extract_image_metadata(tmp_path, "image/png")

            assert not is_corrupt
            assert metadata["thumbhash"] == "abcdef"
