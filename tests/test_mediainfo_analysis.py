"""Tests for MediaInfo analysis service."""

from unittest.mock import Mock, patch

import pytest

from fileindex.services import mediainfo_analysis


class TestMediaInfoAvailability:
    """Test MediaInfo availability checking."""

    def test_is_pymediainfo_available_when_installed(self):
        """Test pymediainfo availability when library is installed and functional."""
        with patch.object(mediainfo_analysis, "MediaInfo") as mock_mediainfo:
            mock_mediainfo.can_parse.return_value = True
            # Reset the global cache
            mediainfo_analysis._pymediainfo_available = None

            result = mediainfo_analysis.is_pymediainfo_available()

            assert result is True
            mock_mediainfo.can_parse.assert_called_once()

    def test_is_pymediainfo_available_when_not_installed(self):
        """Test pymediainfo availability when library is not installed."""
        with patch.object(mediainfo_analysis, "MediaInfo", None):
            # Reset the global cache
            mediainfo_analysis._pymediainfo_available = None

            result = mediainfo_analysis.is_pymediainfo_available()

            assert result is False

    def test_is_pymediainfo_available_when_not_functional(self):
        """Test pymediainfo availability when library is installed but not functional."""
        with patch.object(mediainfo_analysis, "MediaInfo") as mock_mediainfo:
            mock_mediainfo.can_parse.side_effect = Exception("MediaInfo not found")
            # Reset the global cache
            mediainfo_analysis._pymediainfo_available = None

            result = mediainfo_analysis.is_pymediainfo_available()

            assert result is False

    def test_is_pymediainfo_available_caches_result(self):
        """Test that availability check is cached."""
        with patch.object(mediainfo_analysis, "MediaInfo") as mock_mediainfo:
            mock_mediainfo.can_parse.return_value = True
            # Reset the global cache
            mediainfo_analysis._pymediainfo_available = None

            # First call
            result1 = mediainfo_analysis.is_pymediainfo_available()
            # Second call
            result2 = mediainfo_analysis.is_pymediainfo_available()

            assert result1 is True
            assert result2 is True
            # can_parse should only be called once due to caching
            mock_mediainfo.can_parse.assert_called_once()


class TestMetadataExtraction:
    """Test metadata extraction functions."""

    @patch("fileindex.services.mediainfo_analysis.is_pymediainfo_available")
    @patch.object(mediainfo_analysis, "MediaInfo")
    @patch("fileindex.services.mediainfo_analysis.Path")
    def test_extract_mediainfo_metadata_success(self, mock_path, mock_mediainfo_class, mock_available):
        """Test successful metadata extraction."""
        # Setup mocks
        mock_available.return_value = True
        mock_path.return_value.exists.return_value = True

        # Create mock track objects
        mock_general_track = Mock()
        mock_general_track.track_type = "General"
        mock_general_track.duration = 5000
        mock_general_track.recorded_date = "2004-10-04 14:43:30"
        # Mock dir() to return our attributes
        mock_general_track.__dict__ = {
            "track_type": "General",
            "duration": 5000,
            "recorded_date": "2004-10-04 14:43:30",
        }

        mock_video_track = Mock()
        mock_video_track.track_type = "Video"
        mock_video_track.width = 720
        mock_video_track.height = 480
        mock_video_track.__dict__ = {"track_type": "Video", "width": 720, "height": 480}

        # Mock MediaInfo.parse() return value
        mock_media_info = Mock()
        mock_media_info.tracks = [mock_general_track, mock_video_track]
        mock_mediainfo_class.parse.return_value = mock_media_info
        mock_mediainfo_class.version = "21.09"

        # Patch dir() to return our mock attributes
        with patch("builtins.dir") as mock_dir:
            mock_dir.side_effect = lambda obj: list(obj.__dict__.keys()) if hasattr(obj, "__dict__") else []

            result = mediainfo_analysis.extract_mediainfo_metadata("/path/to/file.mov")

        # Verify result structure
        assert "tracks" in result
        assert "version" in result
        assert result["version"] == "21.09"
        assert len(result["tracks"]) == 2

        # Check general track
        general_track = result["tracks"][0]
        assert general_track["track_type"] == "General"
        assert general_track["duration"] == 5000
        assert general_track["recorded_date"] == "2004-10-04 14:43:30"

        # Check video track
        video_track = result["tracks"][1]
        assert video_track["track_type"] == "Video"
        assert video_track["width"] == 720
        assert video_track["height"] == 480

    @patch("fileindex.services.mediainfo_analysis.is_pymediainfo_available")
    def test_extract_mediainfo_metadata_unavailable(self, mock_available):
        """Test metadata extraction when pymediainfo is not available."""
        mock_available.return_value = False

        with pytest.raises(ImportError, match="pymediainfo is not available"):
            mediainfo_analysis.extract_mediainfo_metadata("/path/to/file.mov")

    @patch("fileindex.services.mediainfo_analysis.is_pymediainfo_available")
    @patch("fileindex.services.mediainfo_analysis.Path")
    def test_extract_mediainfo_metadata_file_not_exists(self, mock_path, mock_available):
        """Test metadata extraction when file doesn't exist."""
        mock_available.return_value = True
        mock_path.return_value.exists.return_value = False

        with pytest.raises(ValueError, match="File does not exist"):
            mediainfo_analysis.extract_mediainfo_metadata("/path/to/nonexistent.mov")


class TestHelperFunctions:
    """Test helper functions for specific metadata types."""

    def test_find_dv_recording_date_found(self):
        """Test finding DV recording date when present."""
        mediainfo_data = {
            "tracks": [
                {"track_type": "General", "recorded_date": "2004-10-04 14:43:30", "duration": 5000},
                {"track_type": "Video", "width": 720},
            ]
        }

        result = mediainfo_analysis.find_dv_recording_date(mediainfo_data)

        assert result == "2004-10-04 14:43:30"

    def test_find_dv_recording_date_not_found(self):
        """Test finding DV recording date when not present."""
        mediainfo_data = {
            "tracks": [{"track_type": "General", "duration": 5000}, {"track_type": "Video", "width": 720}]
        }

        result = mediainfo_analysis.find_dv_recording_date(mediainfo_data)

        assert result is None

    def test_find_dv_timecode_found(self):
        """Test finding DV timecode when present."""
        mediainfo_data = {
            "tracks": [
                {"track_type": "General", "duration": 5000},
                {"track_type": "Video", "timecode": "00:00:00;06", "timecode_source": "DV", "scan_type": "Interlaced"},
            ]
        }

        result = mediainfo_analysis.find_dv_timecode(mediainfo_data)

        expected = {"timecode": "00:00:00;06", "timecode_source": "DV", "scan_type": "Interlaced"}
        assert result == expected

    def test_find_dv_timecode_not_found(self):
        """Test finding DV timecode when not present."""
        mediainfo_data = {
            "tracks": [{"track_type": "General", "duration": 5000}, {"track_type": "Video", "width": 720}]
        }

        result = mediainfo_analysis.find_dv_timecode(mediainfo_data)

        assert result is None

    def test_find_commercial_format_found(self):
        """Test finding commercial format when present."""
        mediainfo_data = {
            "tracks": [
                {"track_type": "General", "duration": 5000},
                {"track_type": "Video", "commercial_name": "DVCPRO", "format": "DV"},
            ]
        }

        result = mediainfo_analysis.find_commercial_format(mediainfo_data)

        assert result == "DVCPRO"

    def test_find_commercial_format_fallback_to_format(self):
        """Test finding commercial format falls back to format field."""
        mediainfo_data = {
            "tracks": [
                {"track_type": "General", "duration": 5000},
                {"track_type": "Video", "format": "DV", "width": 720},
            ]
        }

        result = mediainfo_analysis.find_commercial_format(mediainfo_data)

        assert result == "DV"

    def test_find_commercial_format_not_found(self):
        """Test finding commercial format when not present."""
        mediainfo_data = {
            "tracks": [{"track_type": "General", "duration": 5000}, {"track_type": "Video", "width": 720}]
        }

        result = mediainfo_analysis.find_commercial_format(mediainfo_data)

        assert result is None
