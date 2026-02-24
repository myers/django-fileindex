"""Tests for custom animated image duration parsers."""

from pathlib import Path

import pytest

from fileindex.services.animated_parsers import parse_avif_duration, parse_webp_duration
from fileindex.services.image_metadata import extract_image_metadata


class TestAnimatedParsers:
    """Test custom duration parsers for animated images."""

    @pytest.mark.parametrize(
        "filename,expected_duration_ms,parser_func",
        [
            ("animated.avif", 4000, parse_avif_duration),  # 4.0 seconds
            ("test_1.5sec.avif", 1500, parse_avif_duration),
            ("animated.webp", 840, parse_webp_duration),
            ("test_2sec.webp", 2000, parse_webp_duration),
        ],
    )
    def test_custom_parsers_on_sample_files(self, filename, expected_duration_ms, parser_func):
        """Test custom parsers extract correct durations from sample files."""
        sample_path = Path(__file__).parent / "sample_files" / filename

        if not sample_path.exists():
            pytest.skip(f"Sample file {filename} not found")

        file_path = str(sample_path)

        # Test the parser directly
        duration_ms = parser_func(file_path)

        assert duration_ms is not None, f"Parser failed to extract duration from {filename}"
        assert isinstance(duration_ms, int), f"Duration should be integer for {filename}"
        assert duration_ms > 0, f"Duration should be positive for {filename}"

        # Check if duration matches expected value (allow small tolerance for parsing differences)
        tolerance = max(10, expected_duration_ms * 0.01)  # 1% or 10ms, whichever is larger
        duration_diff = abs(duration_ms - expected_duration_ms)

        assert duration_diff <= tolerance, (
            f"Duration mismatch for {filename}: got {duration_ms}ms, "
            f"expected {expected_duration_ms}ms (diff: {duration_diff}ms, tolerance: {tolerance}ms)"
        )

    @pytest.mark.parametrize(
        "filename,mime_type,expected_duration_ms",
        [
            ("animated.avif", "image/avif", 4000),
            ("test_1.5sec.avif", "image/avif", 1500),
            ("animated.webp", "image/webp", 840),
            ("test_2sec.webp", "image/webp", 2000),
            ("test_3sec.gif", "image/gif", 3000),
        ],
    )
    def test_full_metadata_extraction_with_custom_parsers(self, filename, mime_type, expected_duration_ms):
        """Test that full metadata extraction uses custom parsers correctly."""
        sample_path = Path(__file__).parent / "sample_files" / filename

        if not sample_path.exists():
            pytest.skip(f"Sample file {filename} not found")

        file_path = str(sample_path)

        # Extract metadata using our service (should use custom parsers for AVIF/WebP)
        metadata, is_corrupt = extract_image_metadata(file_path, mime_type)

        # Should not be marked as corrupt
        assert not is_corrupt, f"Sample file {filename} was incorrectly marked as corrupt"

        # Should have image metadata
        assert "image" in metadata, f"No image metadata found for {filename}"
        image_info = metadata["image"]

        # Should be detected as animated
        assert image_info.get("animated") is True, f"Sample {filename} should be detected as animated"

        # Should have duration
        assert "duration" in metadata, f"Missing duration for animated {filename}"
        duration_ms = metadata["duration"]

        assert isinstance(duration_ms, int), f"Duration should be integer (ms) for {filename}"
        assert duration_ms > 0, f"Duration should be positive for {filename}: {duration_ms}ms"

        # Check if duration matches expected value
        tolerance = max(10, expected_duration_ms * 0.01)  # 1% or 10ms, whichever is larger
        duration_diff = abs(duration_ms - expected_duration_ms)

        assert duration_diff <= tolerance, (
            f"Full extraction duration mismatch for {filename}: got {duration_ms}ms, "
            f"expected {expected_duration_ms}ms (diff: {duration_diff}ms, tolerance: {tolerance}ms)"
        )

    def test_avif_parser_with_nonexistent_file(self):
        """Test AVIF parser handles missing files gracefully."""
        result = parse_avif_duration("/nonexistent/file.avif")
        assert result is None

    def test_webp_parser_with_nonexistent_file(self):
        """Test WebP parser handles missing files gracefully."""
        result = parse_webp_duration("/nonexistent/file.webp")
        assert result is None

    def test_avif_parser_with_invalid_file(self, tmp_path):
        """Test AVIF parser handles invalid files gracefully."""
        invalid_file = tmp_path / "invalid.avif"
        invalid_file.write_text("not an avif file")

        result = parse_avif_duration(str(invalid_file))
        assert result is None

    def test_webp_parser_with_invalid_file(self, tmp_path):
        """Test WebP parser handles invalid files gracefully."""
        invalid_file = tmp_path / "invalid.webp"
        invalid_file.write_text("not a webp file")

        result = parse_webp_duration(str(invalid_file))
        assert result is None

    def test_parsers_reject_static_images(self):
        """Test that parsers return None for static (non-animated) images if any exist."""
        # This test documents that the parsers should return None for static images
        # For now, we only have animated samples, so this is mostly documentation
        # If we add static AVIF/WebP samples later, they should return None
        pass

    def test_all_sample_files_processed(self):
        """Ensure all animated sample files are processed by the appropriate parser."""
        sample_dir = Path(__file__).parent / "sample_files"

        if not sample_dir.exists():
            pytest.skip("Sample files directory not found")

        animated_files = [
            ("animated.avif", "image/avif"),
            ("test_1.5sec.avif", "image/avif"),
            ("animated.webp", "image/webp"),
            ("test_2sec.webp", "image/webp"),
            ("test_3sec.gif", "image/gif"),
        ]

        processed_count = 0

        for filename, mime_type in animated_files:
            sample_path = sample_dir / filename

            if sample_path.exists():
                # Test that metadata extraction succeeds
                metadata, is_corrupt = extract_image_metadata(str(sample_path), mime_type)

                assert not is_corrupt, f"Failed to process {filename}"
                assert metadata.get("image", {}).get("animated") is True, f"{filename} not detected as animated"
                assert "duration" in metadata, f"No duration extracted for {filename}"

                processed_count += 1

        # Ensure we processed at least some files
        assert processed_count > 0, "No animated sample files were found or processed"
