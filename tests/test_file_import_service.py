"""
Tests for the file import service module.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from fileindex.exceptions import ImportErrorType
from fileindex.services.file_import import (
    batch_import_files,
    find_importable_files,
    import_directory,
    import_file,
)


@pytest.fixture
def temp_test_file():
    """Create a temporary test file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("test content")
        temp_path = f.name

    yield temp_path

    # Cleanup
    try:
        os.unlink(temp_path)
    except FileNotFoundError:
        pass


@pytest.fixture
def temp_test_dir():
    """Create a temporary test directory with files."""
    temp_dir = tempfile.mkdtemp()

    # Create some test files
    test_files = []
    for i in range(3):
        file_path = os.path.join(temp_dir, f"test{i}.txt")
        with open(file_path, "w") as f:
            f.write(f"content {i}")
        test_files.append(file_path)

    # Create a subdirectory with a file
    sub_dir = os.path.join(temp_dir, "subdir")
    os.makedirs(sub_dir)
    sub_file = os.path.join(sub_dir, "subfile.txt")
    with open(sub_file, "w") as f:
        f.write("sub content")
    test_files.append(sub_file)

    yield temp_dir, test_files

    # Cleanup
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.django_db
def test_import_file_success(temp_test_file):
    """Test successful file import."""
    with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
        mock_indexed_file = Mock()
        mock_indexed_file.sha512 = "abcdef1234567890" * 4  # 64 chars
        mock_create.return_value = (mock_indexed_file, True)

        with patch("fileindex.services.file_import.should_import", return_value=True):
            indexed_file, created, error = import_file(temp_test_file)

            assert indexed_file == mock_indexed_file
            assert created is True
            assert error is None
            mock_create.assert_called_once_with(temp_test_file, only_hard_link=False, hash_progress_callback=None)


@pytest.mark.django_db
def test_import_file_already_exists(temp_test_file):
    """Test importing a file that already exists in the index."""
    with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
        mock_indexed_file = Mock()
        mock_indexed_file.sha512 = "abcdef1234567890" * 4
        mock_create.return_value = (mock_indexed_file, False)  # Already exists

        with patch("fileindex.services.file_import.should_import", return_value=True):
            indexed_file, created, error = import_file(temp_test_file)

            assert indexed_file == mock_indexed_file
            assert created is False
            assert error is None


def test_import_file_validation_fails(temp_test_file):
    """Test importing a file that fails validation."""
    with patch("fileindex.services.file_import.should_import", return_value=False):
        indexed_file, created, error = import_file(temp_test_file, validate=True)

        assert indexed_file is None
        assert created is False
        assert error == ImportErrorType.VALIDATION_FAILED


def test_import_file_not_exists():
    """Test importing a non-existent file."""
    indexed_file, created, error = import_file("/nonexistent/file.txt", validate=False)

    assert indexed_file is None
    assert created is False
    assert error == ImportErrorType.FILE_NOT_EXISTS


@pytest.mark.django_db
def test_import_file_with_delete_after(temp_test_file):
    """Test deleting file after successful import."""
    with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
        mock_indexed_file = Mock()
        mock_indexed_file.sha512 = "abcdef1234567890" * 4
        mock_create.return_value = (mock_indexed_file, True)

        with patch("fileindex.services.file_import.should_import", return_value=True):
            indexed_file, created, error = import_file(temp_test_file, delete_after=True)

            assert indexed_file == mock_indexed_file
            assert created is True
            assert error is None
            # File should be deleted
            assert not os.path.exists(temp_test_file)


@pytest.mark.django_db
def test_import_file_only_hard_link(temp_test_file):
    """Test importing with only hard link option."""
    with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
        mock_indexed_file = Mock()
        mock_indexed_file.sha512 = "abcdef1234567890" * 4
        mock_create.return_value = (mock_indexed_file, True)

        with patch("fileindex.services.file_import.should_import", return_value=True):
            indexed_file, created, error = import_file(temp_test_file, only_hard_link=True)

            assert indexed_file == mock_indexed_file
            mock_create.assert_called_once_with(temp_test_file, only_hard_link=True, hash_progress_callback=None)


@pytest.mark.django_db
def test_import_file_with_exception(temp_test_file):
    """Test importing when an exception occurs."""
    with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
        mock_create.side_effect = Exception("Database connection failed")

        with patch("fileindex.services.file_import.should_import", return_value=True):
            indexed_file, created, error = import_file(temp_test_file)

            assert indexed_file is None
            assert created is False
            assert error == ImportErrorType.IMPORT_FAILED


@pytest.mark.django_db
def test_import_directory_recursive(temp_test_dir):
    """Test importing all files from a directory recursively."""
    temp_dir, test_files = temp_test_dir

    with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
        mock_indexed_file = Mock()
        mock_indexed_file.sha512 = "abcdef1234567890" * 4
        mock_create.return_value = (mock_indexed_file, True)

        with patch("fileindex.services.file_import.should_import", return_value=True):
            stats = import_directory(temp_dir, recursive=True)

            assert stats["total_files"] == 4  # 3 in root + 1 in subdir
            assert stats["imported"] == 4
            assert stats["created"] == 4
            assert stats["skipped"] == 0
            assert len(stats["errors"]) == 0
            assert mock_create.call_count == 4


@pytest.mark.django_db
def test_import_directory_non_recursive(temp_test_dir):
    """Test importing files from a directory without recursion."""
    temp_dir, test_files = temp_test_dir

    with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
        mock_indexed_file = Mock()
        mock_indexed_file.sha512 = "abcdef1234567890" * 4
        mock_create.return_value = (mock_indexed_file, True)

        with patch("fileindex.services.file_import.should_import", return_value=True):
            stats = import_directory(temp_dir, recursive=False)

            assert stats["total_files"] == 3  # Only files in root
            assert stats["imported"] == 3
            assert stats["created"] == 3
            assert stats["skipped"] == 0
            assert mock_create.call_count == 3


@pytest.mark.django_db
def test_import_directory_with_validation_failures(temp_test_dir):
    """Test importing directory with some files failing validation."""
    temp_dir, test_files = temp_test_dir

    def mock_should_import(filepath):
        # Only accept files with '1' in the name
        return "1" in os.path.basename(filepath)

    with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
        mock_indexed_file = Mock()
        mock_indexed_file.sha512 = "abcdef1234567890" * 4
        mock_create.return_value = (mock_indexed_file, True)

        with patch("fileindex.services.file_import.should_import", side_effect=mock_should_import):
            stats = import_directory(temp_dir, recursive=True, validate=True)

            assert stats["total_files"] == 4
            assert stats["imported"] == 1  # Only test1.txt
            assert stats["created"] == 1
            assert stats["skipped"] == 3
            assert len(stats["errors"]) == 0


@pytest.mark.django_db
def test_import_directory_with_progress_callback(temp_test_dir):
    """Test import directory with progress callback."""
    temp_dir, test_files = temp_test_dir
    progress_calls = []

    def progress_callback(filepath, success, error_msg):
        progress_calls.append((filepath, success, error_msg))

    with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
        mock_indexed_file = Mock()
        mock_indexed_file.sha512 = "abcdef1234567890" * 4
        mock_create.return_value = (mock_indexed_file, True)

        with patch("fileindex.services.file_import.should_import", return_value=True):
            import_directory(temp_dir, recursive=True, progress_callback=progress_callback)

            assert len(progress_calls) == 4
            assert all(success for _, success, _ in progress_calls)


def test_import_directory_nonexistent():
    """Test importing from non-existent directory."""
    stats = import_directory("/nonexistent/directory")

    assert stats["total_files"] == 0
    assert stats["imported"] == 0
    assert stats["created"] == 0
    assert stats["skipped"] == 0
    assert len(stats["errors"]) == 0


@pytest.mark.django_db
def test_batch_import_files():
    """Test batch importing multiple files."""
    # Create temp files
    temp_files = []
    for i in range(3):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(f"content {i}")
            temp_files.append(f.name)

    try:
        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_indexed_file = Mock()
            mock_indexed_file.sha512 = "abcdef1234567890" * 4
            mock_create.return_value = (mock_indexed_file, True)

            with patch("fileindex.services.file_import.should_import", return_value=True):
                stats = batch_import_files(temp_files)

                assert stats["total_files"] == 3
                assert stats["imported"] == 3
                assert stats["created"] == 3
                assert stats["skipped"] == 0
                assert len(stats["errors"]) == 0
                assert mock_create.call_count == 3

    finally:
        # Cleanup
        for f in temp_files:
            try:
                os.unlink(f)
            except FileNotFoundError:
                pass


@pytest.mark.django_db
def test_batch_import_files_with_progress():
    """Test batch import with progress callback."""
    temp_files = []
    for i in range(2):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(f"content {i}")
            temp_files.append(f.name)

    progress_calls = []

    def progress_callback(filepath, success, error_msg):
        progress_calls.append((filepath, success, error_msg))

    try:
        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            mock_indexed_file = Mock()
            mock_indexed_file.sha512 = "abcdef1234567890" * 4
            mock_create.return_value = (mock_indexed_file, True)

            with patch("fileindex.services.file_import.should_import", return_value=True):
                batch_import_files(temp_files, progress_callback=progress_callback)

                assert len(progress_calls) == 2
                assert progress_calls[0] == (temp_files[0], True, None)
                assert progress_calls[1] == (temp_files[1], True, None)

    finally:
        for f in temp_files:
            try:
                os.unlink(f)
            except FileNotFoundError:
                pass


@pytest.mark.django_db
def test_batch_import_files_stop_on_error():
    """Test batch import stops on first error when requested."""
    temp_files = []
    for i in range(3):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(f"content {i}")
            temp_files.append(f.name)

    try:
        with patch("fileindex.models.IndexedFile.objects.get_or_create_from_file") as mock_create:
            # First succeeds, second fails
            mock_indexed_file = Mock()
            mock_indexed_file.sha512 = "abcdef1234567890" * 4
            mock_create.side_effect = [
                (mock_indexed_file, True),
                Exception("Database error"),
                (mock_indexed_file, True),
            ]

            with patch("fileindex.services.file_import.should_import", return_value=True):
                stats = batch_import_files(temp_files, stop_on_error=True)

                assert stats["imported"] == 1
                assert len(stats["errors"]) == 1
                # Should have stopped after second file
                assert mock_create.call_count == 2

    finally:
        for f in temp_files:
            try:
                os.unlink(f)
            except FileNotFoundError:
                pass


def test_find_importable_files(temp_test_dir):
    """Test finding importable files in a directory."""
    temp_dir, test_files = temp_test_dir

    with patch("fileindex.services.file_import.should_import", return_value=True):
        files = find_importable_files(temp_dir, recursive=True)

        assert len(files) == 4
        assert all(os.path.exists(f) for f in files)


def test_find_importable_files_with_validation(temp_test_dir):
    """Test finding importable files with validation."""
    temp_dir, test_files = temp_test_dir

    def mock_should_import(filepath):
        # Only accept .txt files with '0' in the name
        return filepath.endswith(".txt") and "0" in os.path.basename(filepath)

    with patch("fileindex.services.file_import.should_import", side_effect=mock_should_import):
        files = find_importable_files(temp_dir, recursive=True, validate=True)

        assert len(files) == 1
        assert "test0.txt" in files[0]


def test_find_importable_files_non_recursive(temp_test_dir):
    """Test finding files without recursion."""
    temp_dir, test_files = temp_test_dir

    with patch("fileindex.services.file_import.should_import", return_value=True):
        files = find_importable_files(temp_dir, recursive=False)

        assert len(files) == 3  # Only root directory files
        assert all("subdir" not in f for f in files)
