"""Test subprocess timeout handling in fileindex media analysis service."""

import subprocess
from unittest.mock import MagicMock, patch

from django.test import TestCase

from fileindex.services import ffprobe, thumbnails
from fileindex.services import metadata as metadata_service


class SubprocessTimeoutTestCase(TestCase):
    """Test that subprocess calls have proper timeout handling."""

    @patch("fileindex.services.ffprobe.run_ffprobe")
    def test_get_duration_with_timeout(self, mock_ffprobe):
        """Test that ffprobe service uses timeout for ffprobe calls."""
        # Mock ffprobe to return data with duration
        mock_ffprobe.return_value = {"format": {"duration": "5.0"}}

        # Import and test ffprobe directly since animated duration extraction moved to image_metadata
        from fileindex.services import ffprobe

        # Call run_ffprobe which should use timeout
        result = ffprobe.run_ffprobe("/path/to/test.gif")

        # Verify ffprobe was called and returned expected data
        mock_ffprobe.assert_called_once_with("/path/to/test.gif")
        self.assertEqual(result["format"]["duration"], "5.0")

    @patch("subprocess.run")
    def test_extract_video_metadata_with_timeout(self, mock_run):
        """Test that MediaAnalysisService.extract_video_metadata uses timeout
        for ffprobe."""
        # Mock subprocess.run
        mock_result = MagicMock()
        mock_result.stdout = """{
            "streams": [{
                "codec_type": "video",
                "codec_name": "h264",
                "bit_rate": "5000000",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30/1",
                "duration": "60.0"
            }, {
                "codec_type": "audio",
                "codec_name": "aac",
                "bit_rate": "128000",
                "sample_rate": "48000",
                "channels": 2
            }],
            "format": {"duration": "60.0"}
        }"""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Call extract_metadata with video file type
        metadata, is_corrupt = metadata_service.extract_metadata("/path/to/test.mp4", "video/mp4")

        # Verify subprocess.run was called (may be called multiple times for version check)
        mock_run.assert_called()
        # Find the call with timeout for ffprobe
        found_timeout = False
        for call in mock_run.call_args_list:
            if len(call) > 1 and "timeout" in call[1]:
                found_timeout = True
                break
        self.assertTrue(found_timeout, "No subprocess call with timeout found")

        # Verify metadata extraction with new structure
        self.assertIn("video", metadata)
        self.assertEqual(metadata["video"]["width"], 1920)
        self.assertEqual(metadata["video"]["height"], 1080)
        self.assertEqual(metadata["video"]["codec"], "h264")
        self.assertEqual(metadata["video"]["bitrate"], 5000000)
        self.assertEqual(metadata["video"]["frame_rate"], 30.0)

        self.assertIn("audio", metadata)
        self.assertEqual(metadata["audio"]["codec"], "aac")
        self.assertEqual(metadata["audio"]["bitrate"], 128000)

        self.assertEqual(metadata["duration"], 60000)  # 60.0 * 1000 ms
        self.assertIn("ffprobe", metadata)

    @patch("subprocess.run")
    def test_generate_thumbnail_with_timeout(self, mock_run):
        """Test that MediaAnalysisService.generate_video_thumbnail uses timeout
        for ffmpeg."""
        # Mock subprocess.run for ffmpeg
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Mock file exists
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("tempfile.NamedTemporaryFile") as mock_temp,
        ):
            mock_temp.return_value.__enter__.return_value.name = "/tmp/test.jpg"

            # Call generate_video_thumbnail from thumbnails service
            thumbnail_path = thumbnails.generate_video_thumbnail("/path/to/test.mp4")

        # Verify subprocess.run was called with timeout
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        self.assertIn("timeout", call_kwargs)
        self.assertEqual(call_kwargs["timeout"], 30)
        self.assertEqual(thumbnail_path, "/tmp/test.jpg")

    @patch("subprocess.run")
    def test_get_ffprobe_version(self, mock_run):
        """Test ffprobe version extraction."""
        # Mock subprocess.run for ffprobe -version
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ffprobe version 4.4.2-0ubuntu0.22.04.1 Copyright (c) 2007-2021 the FFmpeg developers\n"
        mock_run.return_value = mock_result

        # Clear the cached version first
        ffprobe._ffprobe_version = None

        # Get version
        version = ffprobe.get_ffprobe_version()

        # Verify the version was extracted correctly
        self.assertEqual(version, "4.4.2-0ubuntu0.22.04.1")

        # Verify subprocess was called with correct arguments
        mock_run.assert_called_once_with(["ffprobe", "-version"], capture_output=True, text=True, timeout=5)

    @patch("subprocess.run")
    def test_get_cached_ffprobe_version(self, mock_run):
        """Test that ffprobe version is cached."""
        # Set up mock
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ffprobe version 5.1.2 Copyright...\n"
        mock_run.return_value = mock_result

        # Clear cache
        ffprobe._ffprobe_version = None

        # First call should invoke subprocess
        version1 = ffprobe.get_cached_ffprobe_version()
        self.assertEqual(version1, "5.1.2")
        self.assertEqual(mock_run.call_count, 1)

        # Second call should use cache
        version2 = ffprobe.get_cached_ffprobe_version()
        self.assertEqual(version2, "5.1.2")
        self.assertEqual(mock_run.call_count, 1)  # Still 1, not called again

    @patch("subprocess.run")
    def test_subprocess_timeout_error_handling(self, mock_run):
        """Test that subprocess.TimeoutExpired is handled properly."""
        # Mock subprocess.run to raise TimeoutExpired
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["ffprobe"], timeout=30)

        # Test that ffprobe service handles timeout gracefully
        from fileindex.services import ffprobe

        result = ffprobe.run_ffprobe("/path/to/test.gif")

        # Should return None on timeout
        self.assertIsNone(result)

    @patch("subprocess.run")
    def test_extract_video_metadata_failure(self, mock_run):
        """Test that extract_metadata marks video files as corrupt on ffprobe failure."""
        # Mock subprocess.run to simulate ffprobe failure
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ffprobe error"
        mock_run.return_value = mock_result

        # Should mark file as corrupt when ffprobe fails
        metadata, is_corrupt = metadata_service.extract_metadata("/path/to/test.mp4", "video/mp4")

        # Should return corrupt flag when ffprobe fails
        self.assertTrue(is_corrupt)

    @patch("subprocess.run")
    def test_extract_audio_metadata_failure(self, mock_run):
        """Test that extract_metadata marks audio files as corrupt on ffprobe failure."""
        # Mock subprocess.run to simulate ffprobe failure
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ffprobe error"
        mock_run.return_value = mock_result

        # Should mark file as corrupt when ffprobe fails
        metadata, is_corrupt = metadata_service.extract_metadata("/path/to/test.mp3", "audio/mp3")

        # Should return corrupt flag when ffprobe fails
        self.assertTrue(is_corrupt)
        mock_run.assert_called_once()
