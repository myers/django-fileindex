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
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30/1",
                "duration": "60.0"
            }],
            "format": {"duration": "60.0"}
        }"""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Call extract_video_metadata directly on service
        metadata = media_analysis.extract_video_metadata("/path/to/test.mp4")

        # Verify subprocess.run was called with timeout
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        self.assertIn("timeout", call_kwargs)
        self.assertEqual(call_kwargs["timeout"], 30)

        # Verify metadata extraction
        self.assertEqual(metadata["width"], 1920)
        self.assertEqual(metadata["height"], 1080)
        self.assertEqual(metadata["duration"], 60.0)
        self.assertEqual(metadata["frame_rate"], 30.0)

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
