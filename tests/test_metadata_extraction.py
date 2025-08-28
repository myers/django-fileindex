"""Tests for the metadata extraction service using pytest."""

import tempfile
from contextlib import suppress
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from fileindex.services.metadata import extract_metadata


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
    """Test metadata extraction functionality."""

    def test_extract_metadata_image(self, create_test_image):
        """Test that extract_metadata correctly handles image files."""
        tmp_path = create_test_image()

        metadata, is_corrupt = extract_metadata(tmp_path, "image/png")

        # Should not be corrupt
        assert not is_corrupt

        # Should contain image metadata
        assert "image" in metadata
        assert "width" in metadata["image"]
        assert "height" in metadata["image"]
        assert metadata["image"]["width"] == 800
        assert metadata["image"]["height"] == 600
        assert "thumbhash" in metadata["image"]

    @patch("fileindex.services.media_metadata.extract_video_metadata")
    def test_extract_metadata_video(self, mock_extract):
        """Test that extract_metadata correctly handles video files."""
        mock_extract.return_value = (
            {
                "video": {"width": 1920, "height": 1080, "frame_rate": 30.0, "codec": "h264"},
                "duration": 60000,
            },
            False,
        )

        metadata, is_corrupt = extract_metadata("/fake/video.mp4", "video/mp4")

        assert not is_corrupt
        assert "video" in metadata
        assert metadata["video"]["width"] == 1920
        assert metadata["video"]["height"] == 1080
        assert metadata["duration"] == 60000
        mock_extract.assert_called_once_with("/fake/video.mp4")

    @patch("fileindex.services.media_metadata.extract_audio_metadata")
    def test_extract_metadata_audio(self, mock_extract):
        """Test that extract_metadata correctly handles audio files."""
        mock_extract.return_value = (
            {
                "audio": {"codec": "mp3", "bitrate": 320000},
                "duration": 180000,
            },
            False,
        )

        metadata, is_corrupt = extract_metadata("/fake/audio.mp3", "audio/mp3")

        assert not is_corrupt
        assert "audio" in metadata
        assert metadata["audio"]["codec"] == "mp3"
        assert metadata["duration"] == 180000
        mock_extract.assert_called_once_with("/fake/audio.mp3")

    def test_extract_metadata_unknown_type(self):
        """Test that extract_metadata handles unknown file types."""
        metadata, is_corrupt = extract_metadata("/fake/file.txt", "text/plain")

        # Should not be corrupt and have empty metadata
        assert not is_corrupt
        assert metadata == {}

    def test_extract_metadata_none_mime_type(self, create_test_image):
        """Test that extract_metadata auto-detects MIME type when None."""
        tmp_path = create_test_image()

        metadata, is_corrupt = extract_metadata(tmp_path, None)

        # Should auto-detect as image and extract metadata
        assert not is_corrupt
        assert "image" in metadata
        assert "width" in metadata["image"]
        assert "height" in metadata["image"]

    @patch("fileindex.services.image_metadata.extract_image_metadata")
    def test_extract_metadata_exception_handling(self, mock_extract):
        """Test that extract_metadata handles exceptions properly."""
        mock_extract.side_effect = Exception("Test exception")

        metadata, is_corrupt = extract_metadata("/fake/image.jpg", "image/jpeg")

        # Should mark as corrupt when exception occurs
        assert is_corrupt
        assert metadata == {}
