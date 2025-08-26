"""Tests for Django system checks."""

from unittest.mock import patch

from django.core.checks import Warning

from fileindex import checks


class TestFFProbeChecks:
    """Test ffprobe availability checks."""

    @patch("fileindex.checks.get_ffprobe_version")
    def test_ffprobe_available(self, mock_get_version):
        """Test check passes when ffprobe is available."""
        mock_get_version.return_value = "4.4.2"

        result = checks.check_ffprobe_available(None)

        assert result == []
        mock_get_version.assert_called_once()

    @patch("fileindex.checks.get_ffprobe_version")
    def test_ffprobe_not_available(self, mock_get_version):
        """Test check fails when ffprobe is not available."""
        mock_get_version.return_value = None

        result = checks.check_ffprobe_available(None)

        assert len(result) == 1
        assert isinstance(result[0], Warning)
        assert result[0].id == "fileindex.W001"
        assert "ffprobe is not available" in result[0].msg

    @patch("fileindex.checks.get_ffprobe_version")
    def test_ffprobe_check_exception(self, mock_get_version):
        """Test check handles exceptions gracefully."""
        mock_get_version.side_effect = Exception("Test error")

        result = checks.check_ffprobe_available(None)

        assert len(result) == 1
        assert isinstance(result[0], Warning)
        assert result[0].id == "fileindex.W002"
        assert "Error checking ffprobe availability" in result[0].msg


class TestMediaInfoChecks:
    """Test MediaInfo availability checks."""

    @patch("fileindex.checks.is_pymediainfo_available")
    def test_mediainfo_available(self, mock_is_available):
        """Test check passes when MediaInfo is available."""
        mock_is_available.return_value = True

        result = checks.check_mediainfo_available(None)

        assert result == []
        mock_is_available.assert_called_once()

    @patch("fileindex.checks.is_pymediainfo_available")
    def test_mediainfo_not_available(self, mock_is_available):
        """Test check fails when MediaInfo is not available."""
        mock_is_available.return_value = False

        result = checks.check_mediainfo_available(None)

        assert len(result) == 1
        assert isinstance(result[0], Warning)
        assert result[0].id == "fileindex.W003"
        assert "MediaInfo (pymediainfo) is not available" in result[0].msg

    @patch("fileindex.checks.is_pymediainfo_available")
    def test_mediainfo_check_exception(self, mock_is_available):
        """Test check handles exceptions gracefully."""
        mock_is_available.side_effect = Exception("Test error")

        result = checks.check_mediainfo_available(None)

        assert len(result) == 1
        assert isinstance(result[0], Warning)
        assert result[0].id == "fileindex.W004"
        assert "Error checking MediaInfo availability" in result[0].msg
