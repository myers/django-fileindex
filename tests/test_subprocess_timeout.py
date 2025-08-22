"""Test subprocess timeout handling in fileindex media analysis service."""

import subprocess
from unittest.mock import MagicMock, patch

from django.test import TestCase

from fileindex.services import media_analysis


class SubprocessTimeoutTestCase(TestCase):
    """Test that subprocess calls have proper timeout handling."""

    @patch("subprocess.run")
    def test_get_duration_with_timeout(self, mock_run):
        """Test that MediaAnalysisService.get_duration uses timeout for ffprobe."""
        # Mock subprocess.run to check timeout parameter
        mock_result = MagicMock()
        mock_result.stdout = '{"format": {"duration": "5.0"}}'
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Call get_duration directly on service
        duration = media_analysis.get_duration("/path/to/test.gif", "image/gif")

        # Verify subprocess.run was called with timeout
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        self.assertIn("timeout", call_kwargs)
        self.assertEqual(call_kwargs["timeout"], 30)
        self.assertEqual(duration, 5.0)

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

        # Call extract_video_metadata directly on service
        metadata = media_analysis.extract_video_metadata("/path/to/test.mp4")

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

            # Call generate_video_thumbnail directly on service
            thumbnail_path = media_analysis.generate_video_thumbnail("/path/to/test.mp4")

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
        media_analysis._ffprobe_version = None

        # Get version
        version = media_analysis.get_ffprobe_version()

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
        media_analysis._ffprobe_version = None

        # First call should invoke subprocess
        version1 = media_analysis.get_cached_ffprobe_version()
        self.assertEqual(version1, "5.1.2")
        self.assertEqual(mock_run.call_count, 1)

        # Second call should use cache
        version2 = media_analysis.get_cached_ffprobe_version()
        self.assertEqual(version2, "5.1.2")
        self.assertEqual(mock_run.call_count, 1)  # Still 1, not called again

    @patch("subprocess.run")
    def test_subprocess_timeout_error_handling(self, mock_run):
        """Test that subprocess.TimeoutExpired is handled properly."""
        # Mock subprocess.run to raise TimeoutExpired
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["ffprobe"], timeout=30)

        # Call get_duration - should handle timeout gracefully
        duration = media_analysis.get_duration("/path/to/test.gif", "image/gif")

        # Should return None on timeout
        self.assertIsNone(duration)

    @patch("subprocess.run")
    def test_extract_video_metadata_failure(self, mock_run):
        """Test that extract_video_metadata raises ValueError on failure."""
        # Mock subprocess.run to simulate ffprobe failure
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ffprobe error"
        mock_run.return_value = mock_result

        # Should raise ValueError when ffprobe fails
        with self.assertRaises(ValueError) as context:
            media_analysis.extract_video_metadata("/path/to/test.mp4")

        self.assertIn("Could not extract video metadata", str(context.exception))

    @patch("subprocess.run")
    def test_extract_audio_metadata_failure(self, mock_run):
        """Test that extract_audio_metadata raises ValueError on failure."""
        # Mock subprocess.run to simulate ffprobe failure
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ffprobe error"
        mock_run.return_value = mock_result

        # Should raise ValueError when ffprobe fails
        with self.assertRaises(ValueError) as context:
            media_analysis.extract_audio_metadata("/path/to/test.mp3")

        self.assertIn("Could not extract audio metadata", str(context.exception))
        mock_run.assert_called_once()
