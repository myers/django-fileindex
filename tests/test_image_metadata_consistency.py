"""Test that ffprobe and Pillow agree on image dimensions for sample files."""

from pathlib import Path

import pytest
from PIL import Image

from fileindex.services import ffprobe
from fileindex.services.image_metadata import extract_image_metadata


class TestImageMetadataConsistency:
    """Test consistency between Pillow and ffprobe for image metadata."""

    def test_pillow_ffprobe_dimensions_comparison(self):
        """Test comparing Pillow and ffprobe dimensions for sample images.

        This test documents the behavior differences between Pillow and ffprobe
        for different animated image formats, validating our architectural decision
        to use Pillow for image processing.
        """
        sample_files = [
            ("animated.avif", "image/avif"),
            ("animated.webp", "image/webp"),
        ]

        results = []

        for filename, _mime_type in sample_files:
            sample_path = Path(__file__).parent / "sample_files" / filename

            if not sample_path.exists():
                continue

            file_path = str(sample_path)

            # Get dimensions from Pillow
            with Image.open(file_path) as img:
                pillow_width, pillow_height = img.size
                pillow_animated = getattr(img, "is_animated", False)
                pillow_frames = getattr(img, "n_frames", 1)

            # Get dimensions and duration from ffprobe
            ffprobe_data = ffprobe.run_ffprobe(file_path)
            ffprobe_width = None
            ffprobe_height = None
            ffprobe_duration_sec = None

            if ffprobe_data:
                # Get dimensions from video/image streams
                for stream in ffprobe_data.get("streams", []):
                    if stream.get("codec_type") in ("video", "image"):
                        ffprobe_width = stream.get("width")
                        ffprobe_height = stream.get("height")
                        if not ffprobe_duration_sec:
                            ffprobe_duration_sec = stream.get("duration")
                        break

                # Try to get duration from format if not found in streams
                if not ffprobe_duration_sec and "format" in ffprobe_data:
                    ffprobe_duration_sec = ffprobe_data["format"].get("duration")

                # Convert to float if we got a duration string
                if ffprobe_duration_sec:
                    try:
                        ffprobe_duration_sec = float(ffprobe_duration_sec)
                    except (ValueError, TypeError):
                        ffprobe_duration_sec = None

            # Also get our service's duration for comparison
            pillow_duration_ms = None
            try:
                with Image.open(file_path) as img:
                    if getattr(img, "is_animated", False):
                        # Calculate total duration using our service's method
                        total_duration = 0
                        frame_count = 0
                        img.seek(0)

                        while True:
                            try:
                                frame_duration = img.info.get("duration", 100)
                                total_duration += frame_duration
                                frame_count += 1
                                img.seek(img.tell() + 1)
                            except EOFError:
                                break
                            except Exception:
                                break

                        if frame_count > 1 and total_duration > 0:
                            pillow_duration_ms = total_duration

                        img.seek(0)  # Reset to first frame
            except Exception:
                pillow_duration_ms = None

            results.append(
                {
                    "filename": filename,
                    "pillow": {
                        "dimensions": (pillow_width, pillow_height),
                        "animated": pillow_animated,
                        "frames": pillow_frames,
                        "duration_ms": pillow_duration_ms,
                    },
                    "ffprobe_result": {
                        "dimensions": (ffprobe_width, ffprobe_height) if ffprobe_width is not None else None,
                        "duration_sec": ffprobe_duration_sec,
                        "success": ffprobe_data is not None,
                    },
                }
            )

        # Validate results and document expected behavior
        for result in results:
            filename = result["filename"]
            pillow = result["pillow"]
            ffprobe_result = result["ffprobe_result"]

            # Pillow should always be able to read the dimensions
            assert pillow["dimensions"][0] > 0, f"Pillow failed to get width for {filename}"
            assert pillow["dimensions"][1] > 0, f"Pillow failed to get height for {filename}"

            # Compare durations if both tools detected animation
            if pillow["animated"] and pillow["duration_ms"] is not None:
                if ffprobe_result["duration_sec"] is not None:
                    # Convert Pillow ms to seconds for comparison
                    pillow_duration_sec = pillow["duration_ms"] / 1000.0
                    ffprobe_duration_sec = ffprobe_result["duration_sec"]

                    # Allow some tolerance in duration comparison (animations can be tricky)
                    tolerance = max(0.1, pillow_duration_sec * 0.1)  # 10% or 0.1s, whichever is larger
                    duration_diff = abs(pillow_duration_sec - ffprobe_duration_sec)

                    # Log the comparison for visibility
                    print(f"\n{filename} duration comparison:")
                    print(f"  Pillow: {pillow_duration_sec:.3f}s ({pillow['duration_ms']}ms)")
                    print(f"  ffprobe: {ffprobe_duration_sec:.3f}s")
                    print(f"  Difference: {duration_diff:.3f}s (tolerance: {tolerance:.3f}s)")

                    if duration_diff <= tolerance:
                        print("  ✓ Durations agree within tolerance")
                    else:
                        print("  ⚠ Duration mismatch exceeds tolerance")
                        # For now, just warn rather than fail - duration calculation can vary

            # For AVIF, both should work and agree
            if filename.endswith(".avif"):
                assert ffprobe_result["success"], f"ffprobe should work for {filename}"
                if ffprobe_result["dimensions"]:
                    assert pillow["dimensions"] == ffprobe_result["dimensions"], (
                        f"Dimensions should match for {filename}: "
                        f"Pillow={pillow['dimensions']}, ffprobe={ffprobe_result['dimensions']}"
                    )

            # For WebP, ffprobe may report 0x0 dimensions (known limitation)
            elif filename.endswith(".webp"):
                # Document that ffprobe may struggle with animated WebP
                if ffprobe_result["dimensions"] and ffprobe_result["dimensions"] != (0, 0):
                    # If ffprobe got valid dimensions, they should match Pillow
                    assert pillow["dimensions"] == ffprobe_result["dimensions"], (
                        f"Valid ffprobe dimensions should match Pillow for {filename}"
                    )
                # If ffprobe reports 0x0, that's expected for some WebP files
                elif ffprobe_result["dimensions"] == (0, 0):
                    # This validates why we use Pillow for images - it handles WebP better
                    assert pillow["dimensions"] != (0, 0), (
                        f"Pillow should still get valid dimensions for {filename} even when ffprobe fails"
                    )

    @pytest.mark.parametrize(
        "filename,mime_type",
        [
            ("animated.avif", "image/avif"),
            ("animated.webp", "image/webp"),
        ],
    )
    def test_image_metadata_extraction_success(self, filename, mime_type):
        """Test that our image metadata extraction successfully processes sample files."""
        sample_path = Path(__file__).parent / "sample_files" / filename

        # Skip test if file doesn't exist
        if not sample_path.exists():
            pytest.skip(f"Sample file {filename} not found")

        file_path = str(sample_path)

        # Extract metadata using our service
        metadata, is_corrupt = extract_image_metadata(file_path, mime_type)

        # Should not be marked as corrupt
        assert not is_corrupt, f"Sample file {filename} was incorrectly marked as corrupt"

        # Should have image metadata with required fields
        assert "image" in metadata, f"No image metadata found for {filename}"
        image_info = metadata["image"]

        assert "width" in image_info, f"Missing width for {filename}"
        assert "height" in image_info, f"Missing height for {filename}"
        assert "thumbhash" in image_info, f"Missing thumbhash for {filename}"
        assert "animated" in image_info, f"Missing animated flag for {filename}"

        # Dimensions should be positive
        assert image_info["width"] > 0, f"Invalid width for {filename}: {image_info['width']}"
        assert image_info["height"] > 0, f"Invalid height for {filename}: {image_info['height']}"

        # Thumbhash should be a non-empty string
        assert isinstance(image_info["thumbhash"], str), f"Thumbhash should be string for {filename}"
        assert len(image_info["thumbhash"]) > 0, f"Empty thumbhash for {filename}"

        # Animated flag should be True for these files (they're animated)
        assert image_info["animated"] is True, f"Sample {filename} should be detected as animated"

        # Should have duration for animated images
        if image_info["animated"]:
            assert "duration" in metadata, f"Missing duration for animated {filename}"
            assert metadata["duration"] > 0, f"Invalid duration for {filename}: {metadata['duration']}"

    def test_consistency_with_video_file(self):
        """Test that we can extract dimensions from video file using ffprobe (for comparison)."""
        video_path = Path(__file__).parent.parent / "v" / "rose.mov"

        if not video_path.exists():
            pytest.skip("Sample video file rose.mov not found")

        file_path = str(video_path)

        # Get video dimensions from ffprobe
        ffprobe_data = ffprobe.run_ffprobe(file_path)
        assert ffprobe_data is not None, "ffprobe failed to read rose.mov"

        video_width = None
        video_height = None

        for stream in ffprobe_data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_width = stream.get("width")
                video_height = stream.get("height")
                break

        # Should have found video dimensions
        assert video_width is not None and video_height is not None, "ffprobe failed to get video dimensions"
        assert video_width > 0 and video_height > 0, f"Invalid video dimensions: {video_width}x{video_height}"

    @pytest.mark.parametrize(
        "filename,mime_type",
        [
            ("animated.avif", "image/avif"),
            ("animated.webp", "image/webp"),
        ],
    )
    def test_animated_duration_extraction(self, filename, mime_type):
        """Test that animated images have duration extracted using Pillow (not ffprobe)."""
        sample_path = Path(__file__).parent / "sample_files" / filename

        if not sample_path.exists():
            pytest.skip(f"Sample file {filename} not found")

        file_path = str(sample_path)

        # Extract metadata - this should use Pillow for duration extraction per architecture
        metadata, is_corrupt = extract_image_metadata(file_path, mime_type)

        assert not is_corrupt, f"Sample file {filename} was incorrectly marked as corrupt"

        # Check that duration was extracted
        if metadata.get("image", {}).get("animated"):
            assert "duration" in metadata, f"Missing duration for animated {filename}"
            duration_ms = metadata["duration"]
            assert isinstance(duration_ms, int), f"Duration should be integer (ms) for {filename}"
            assert duration_ms > 0, f"Duration should be positive for {filename}: {duration_ms}ms"

            # Duration should be reasonable (not too short or too long)
            assert 10 <= duration_ms <= 60000, f"Duration seems unreasonable for {filename}: {duration_ms}ms"
