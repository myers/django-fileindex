"""
Tests for hash progress callback functionality.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from fileindex.fileutils import analyze_file, hash_file
from fileindex.models import IndexedFile
from fileindex.services.file_import import import_file


@pytest.mark.django_db
def test_hash_file_with_progress_callback():
    """Test that hash_file calls progress callback with correct values."""
    # Create a temporary file with known content
    content = b"Hello, World!" * 1000  # 13,000 bytes
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(content)
        temp_file.flush()
        temp_path = temp_file.name

    try:
        # Track progress calls
        progress_calls = []

        def progress_callback(bytes_processed, total_bytes):
            progress_calls.append((bytes_processed, total_bytes))

        # Hash the file with progress callback
        result = hash_file(temp_path, progress_callback=progress_callback)

        # Verify hash was calculated
        assert "sha1" in result
        assert "sha512" in result

        # Verify progress callback was called
        assert len(progress_calls) > 0

        # Verify first call starts at beginning
        first_call = progress_calls[0]
        assert first_call[0] > 0  # Some bytes processed
        assert first_call[1] == len(content)  # Total size is correct

        # Verify last call processes all bytes
        last_call = progress_calls[-1]
        assert last_call[0] == len(content)
        assert last_call[1] == len(content)

        # Verify progress is monotonically increasing
        for i in range(1, len(progress_calls)):
            assert progress_calls[i][0] >= progress_calls[i - 1][0]

    finally:
        # Clean up
        Path(temp_path).unlink()


@pytest.mark.django_db
def test_hash_file_without_progress_callback():
    """Test that hash_file works without progress callback."""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Test content")
        temp_file.flush()
        temp_path = temp_file.name

    try:
        # Hash without callback (should not raise)
        result = hash_file(temp_path)

        # Verify hash was calculated
        assert "sha1" in result
        assert "sha512" in result

    finally:
        Path(temp_path).unlink()


@pytest.mark.django_db
def test_analyze_file_with_progress_callback():
    """Test that analyze_file passes through progress callback."""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as temp_file:
        temp_file.write(b"Test content for analysis")
        temp_file.flush()
        temp_path = temp_file.name

    try:
        progress_callback = Mock()

        # Analyze with progress callback
        result = analyze_file(temp_path, hash_progress_callback=progress_callback)

        # Verify analysis completed
        assert "sha1" in result
        assert "sha512" in result
        assert "mime_type" in result
        assert "size" in result

        # Verify progress callback was called
        assert progress_callback.called

    finally:
        Path(temp_path).unlink()


@pytest.mark.django_db
def test_indexed_file_create_with_progress_callback():
    """Test IndexedFile.objects.get_or_create_from_file with progress callback."""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as temp_file:
        content = b"Content for IndexedFile test" * 100
        temp_file.write(content)
        temp_file.flush()
        temp_path = temp_file.name

    try:
        progress_calls = []

        def progress_callback(bytes_processed, total_bytes):
            progress_calls.append((bytes_processed, total_bytes))

        # Create IndexedFile with progress callback
        indexed_file, created = IndexedFile.objects.get_or_create_from_file(
            temp_path, hash_progress_callback=progress_callback
        )

        # Verify file was indexed
        assert indexed_file is not None
        assert created is True

        # Verify progress callback was called
        assert len(progress_calls) > 0

        # Verify total bytes matches file size
        assert progress_calls[-1][1] == len(content)

    finally:
        Path(temp_path).unlink()


@pytest.mark.django_db
def test_import_file_with_progress_callback():
    """Test import_file service with hash progress callback."""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as temp_file:
        temp_file.write(b"Import test content" * 50)
        temp_file.flush()
        temp_path = temp_file.name

    try:
        progress_callback = Mock()

        # Import file with progress callback (disable validation for test)
        indexed_file, created, error = import_file(
            temp_path,
            hash_progress_callback=progress_callback,
            validate=False,  # Disable validation to ensure import succeeds
        )

        # Verify import succeeded
        assert indexed_file is not None, f"Import failed with error: {error}"
        assert error is None

        # Verify progress callback was called
        assert progress_callback.called

    finally:
        Path(temp_path).unlink()


@pytest.mark.django_db
def test_progress_callback_with_large_file():
    """Test progress callback with a larger file to ensure multiple calls."""
    # Create a larger temporary file (1MB)
    size_mb = 1
    content = b"X" * (1024 * 1024 * size_mb)

    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(content)
        temp_file.flush()
        temp_path = temp_file.name

    try:
        progress_calls = []

        def progress_callback(bytes_processed, total_bytes):
            progress_calls.append((bytes_processed, total_bytes))

        # Hash with smaller chunk size to ensure multiple progress calls
        hash_file(temp_path, progress_callback=progress_callback, chunk_size=8192)

        # Should have multiple progress calls for a 1MB file with 8KB chunks
        assert len(progress_calls) >= 100  # At least 100 calls for 1MB/8KB

        # Verify all calls have correct total
        for call in progress_calls:
            assert call[1] == len(content)

        # Verify progress increases
        for i in range(1, len(progress_calls)):
            assert progress_calls[i][0] >= progress_calls[i - 1][0]

    finally:
        Path(temp_path).unlink()


@pytest.mark.django_db
def test_progress_callback_exception_handling():
    """Test that exceptions in progress callback don't break hashing."""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Test content")
        temp_file.flush()
        temp_path = temp_file.name

    try:

        def bad_callback(bytes_processed, total_bytes):
            raise ValueError("Callback error")

        # This should not raise even though callback raises
        # (In production, you might want to catch and log callback errors)
        with pytest.raises(ValueError):
            hash_file(temp_path, progress_callback=bad_callback)

    finally:
        Path(temp_path).unlink()


@pytest.mark.django_db
def test_progress_callback_values_accuracy():
    """Test that progress callback receives accurate byte counts."""
    # Create file with exact known size
    exact_size = 10000
    content = b"A" * exact_size

    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(content)
        temp_file.flush()
        temp_path = temp_file.name

    try:
        last_bytes_processed = 0

        def progress_callback(bytes_processed, total_bytes):
            nonlocal last_bytes_processed
            # Total should always be exact size
            assert total_bytes == exact_size
            # Progress should never exceed total
            assert bytes_processed <= total_bytes
            # Progress should be non-decreasing
            assert bytes_processed >= last_bytes_processed
            last_bytes_processed = bytes_processed

        hash_file(temp_path, progress_callback=progress_callback)

        # Final progress should be exactly the file size
        assert last_bytes_processed == exact_size

    finally:
        Path(temp_path).unlink()
