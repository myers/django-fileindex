"""Tests for the directory watch service."""

from unittest.mock import Mock, patch

from fileindex.services.watch import DirectoryWatcher, WatchEventHandler

# WatchEventHandler tests


def test_event_handler_init():
    """Test event handler initialization."""
    callback = Mock()
    handler = WatchEventHandler(callback)

    assert handler.callback == callback
    assert handler.processed_files == set()


def test_on_created_file_event():
    """Test handling of file creation events."""
    callback = Mock()
    handler = WatchEventHandler(callback)

    # Create mock event
    event = Mock()
    event.is_directory = False
    event.src_path = "/path/to/file.txt"

    # Handle event
    handler.on_created(event)

    # Callback should be called with file path
    callback.assert_called_once_with("/path/to/file.txt")


def test_on_created_directory_event_ignored():
    """Test that directory creation events are ignored."""
    callback = Mock()
    handler = WatchEventHandler(callback)

    # Create mock directory event
    event = Mock()
    event.is_directory = True
    event.src_path = "/path/to/dir"

    # Handle event
    handler.on_created(event)

    # Callback should not be called for directories
    callback.assert_not_called()


def test_on_moved_file_event():
    """Test handling of file move events."""
    callback = Mock()
    handler = WatchEventHandler(callback)

    # Create mock event
    event = Mock()
    event.is_directory = False
    event.dest_path = "/path/to/moved_file.txt"

    # Handle event
    handler.on_moved(event)

    # Callback should be called with destination path
    callback.assert_called_once_with("/path/to/moved_file.txt")


def test_on_close_file_event():
    """Test handling of file close events."""
    callback = Mock()
    handler = WatchEventHandler(callback)

    # Create mock event
    event = Mock()
    event.is_directory = False
    event.src_path = "/path/to/file.txt"

    # Handle event
    handler.on_close(event)

    # Callback should be called with file path
    callback.assert_called_once_with("/path/to/file.txt")


def test_duplicate_file_events_ignored():
    """Test that duplicate file events are ignored."""
    callback = Mock()
    handler = WatchEventHandler(callback)

    # Create mock event
    event = Mock()
    event.is_directory = False
    event.src_path = "/path/to/file.txt"

    # Handle same event multiple times
    handler.on_created(event)
    handler.on_created(event)
    handler.on_created(event)

    # Callback should only be called once
    callback.assert_called_once_with("/path/to/file.txt")


def test_processed_files_cache_clearing():
    """Test that the processed files cache is cleared periodically."""
    callback = Mock()
    handler = WatchEventHandler(callback)

    # Add more than 1000 files to trigger cache clearing
    for i in range(1001):
        handler.processed_files.add(f"file_{i}.txt")

    # Cache should be cleared when checking a new file
    event = Mock()
    event.is_directory = False
    event.src_path = "new_file.txt"

    # The cache clearing happens inside _should_process_file
    handler.on_created(event)

    # After clearing and adding the new file, cache should only contain the new file
    assert len(handler.processed_files) == 1
    assert "new_file.txt" in handler.processed_files


# DirectoryWatcher tests


def test_directory_watcher_init():
    """Test DirectoryWatcher initialization."""
    paths = ["/path1", "/path2"]
    watcher = DirectoryWatcher(
        paths=paths,
        delete_after=True,
        recursive=False,
        validate=False,
    )

    assert watcher.paths == paths
    assert watcher.delete_after is True
    assert watcher.recursive is False
    assert watcher.validate is False
    assert watcher.observer is None


def test_directory_watcher_with_callbacks():
    """Test DirectoryWatcher initialization with callbacks."""
    file_callback = Mock()
    progress_callback = Mock()

    watcher = DirectoryWatcher(
        paths=["/test"],
        file_event_callback=file_callback,
        import_progress_callback=progress_callback,
    )

    assert watcher.file_event_callback == file_callback
    assert watcher.import_progress_callback == progress_callback


@patch("fileindex.services.watch.import_directory")
def test_import_existing_files(mock_import_directory):
    """Test importing existing files from directories."""
    # Setup mock return value
    mock_import_directory.return_value = {
        "total_files": 10,
        "imported": 8,
        "created": 5,
        "skipped": 2,
        "errors": {},
    }

    paths = ["/path1", "/path2"]
    callback = Mock()
    watcher = DirectoryWatcher(
        paths=paths,
        import_progress_callback=callback,
    )

    # Import existing files
    results = watcher.import_existing_files()

    # Should call import_directory for each path
    assert mock_import_directory.call_count == 2
    mock_import_directory.assert_any_call(
        "/path1",
        recursive=True,
        delete_after=False,
        validate=True,
        progress_callback=callback,
    )
    mock_import_directory.assert_any_call(
        "/path2",
        recursive=True,
        delete_after=False,
        validate=True,
        progress_callback=callback,
    )

    # Should return results for each path
    assert "/path1" in results
    assert "/path2" in results
    assert results["/path1"]["imported"] == 8


@patch("fileindex.services.watch.import_file")
def test_handle_file_event_success(mock_import_file):
    """Test handling successful file import events."""
    # Setup mock for successful import
    mock_import_file.return_value = (Mock(), True, None)  # (file, created, error)

    callback = Mock()
    watcher = DirectoryWatcher(
        paths=["/test"],
        file_event_callback=callback,
    )

    # Handle file event
    watcher.handle_file_event("/path/to/file.txt")

    # Should call import_file
    mock_import_file.assert_called_once_with(
        "/path/to/file.txt",
        delete_after=False,
        validate=True,
    )

    # Should call callback with success
    callback.assert_called_once_with("/path/to/file.txt", True, "Created")


@patch("fileindex.services.watch.import_file")
def test_handle_file_event_already_exists(mock_import_file):
    """Test handling file import when file already exists."""
    # Setup mock for existing file
    mock_import_file.return_value = (Mock(), False, None)  # (file, created, error)

    callback = Mock()
    watcher = DirectoryWatcher(
        paths=["/test"],
        file_event_callback=callback,
    )

    # Handle file event
    watcher.handle_file_event("/path/to/file.txt")

    # Should call callback with "Already indexed"
    callback.assert_called_once_with("/path/to/file.txt", True, "Already indexed")


@patch("fileindex.services.watch.import_file")
def test_handle_file_event_validation_failure(mock_import_file):
    """Test handling file import validation failures."""
    from fileindex.exceptions import ImportErrorType

    # Setup mock for validation failure
    mock_import_file.return_value = (None, False, ImportErrorType.VALIDATION_FAILED)

    callback = Mock()
    watcher = DirectoryWatcher(
        paths=["/test"],
        file_event_callback=callback,
    )

    # Handle file event
    watcher.handle_file_event("/path/to/file.txt")

    # Should call callback with skipped message
    callback.assert_called_once_with("/path/to/file.txt", False, "Skipped: validation failed")


@patch("fileindex.services.watch.import_file")
def test_handle_file_event_error(mock_import_file):
    """Test handling file import errors."""
    from fileindex.exceptions import ImportErrorType

    # Setup mock for import error
    mock_import_file.return_value = (None, False, ImportErrorType.PERMISSION_DENIED)

    callback = Mock()
    watcher = DirectoryWatcher(
        paths=["/test"],
        file_event_callback=callback,
    )

    # Handle file event
    watcher.handle_file_event("/path/to/file.txt")

    # Should call callback with error message
    callback.assert_called_once_with("/path/to/file.txt", False, "Error: PERMISSION_DENIED")


@patch("fileindex.services.watch.import_file")
def test_handle_file_event_no_callback(mock_import_file):
    """Test handling file events without callback."""
    # Setup mock for successful import
    mock_import_file.return_value = (Mock(), True, None)

    # No callback provided
    watcher = DirectoryWatcher(paths=["/test"])

    # Should not raise error when handling event
    watcher.handle_file_event("/path/to/file.txt")

    # Should still call import_file
    mock_import_file.assert_called_once()


@patch("fileindex.services.watch.import_file")
def test_handle_file_event_with_delete_after(mock_import_file):
    """Test handling file events with delete_after option."""
    # Setup mock for successful import
    mock_import_file.return_value = (Mock(), True, None)

    watcher = DirectoryWatcher(
        paths=["/test"],
        delete_after=True,
    )

    # Handle file event
    watcher.handle_file_event("/path/to/file.txt")

    # Should call import_file with delete_after=True
    mock_import_file.assert_called_once_with(
        "/path/to/file.txt",
        delete_after=True,
        validate=True,
    )


@patch("fileindex.services.watch.PollingObserver")
def test_start_watching(mock_observer_class):
    """Test starting the directory watcher."""
    mock_observer = Mock()
    mock_observer.is_alive.return_value = False
    mock_observer_class.return_value = mock_observer

    watcher = DirectoryWatcher(paths=["/path1", "/path2"])

    # Start watching
    observer = watcher.start_watching()

    # Should create observer
    mock_observer_class.assert_called_once()

    # Should schedule handler for each path
    assert mock_observer.schedule.call_count == 2

    # Should start observer
    mock_observer.start.assert_called_once()

    # Should return observer
    assert observer == mock_observer


@patch("fileindex.services.watch.PollingObserver")
def test_start_watching_already_running(mock_observer_class):
    """Test starting watcher when already running."""
    mock_observer = Mock()
    mock_observer.is_alive.return_value = True

    watcher = DirectoryWatcher(paths=["/path1"])
    watcher.observer = mock_observer

    # Try to start watching again
    observer = watcher.start_watching()

    # Should not create new observer
    mock_observer_class.assert_not_called()

    # Should return existing observer
    assert observer == mock_observer


def test_stop_watching():
    """Test stopping the directory watcher."""
    mock_observer = Mock()
    mock_observer.is_alive.return_value = True

    watcher = DirectoryWatcher(paths=["/path1"])
    watcher.observer = mock_observer

    # Stop watching
    watcher.stop_watching()

    # Should stop and join observer
    mock_observer.stop.assert_called_once()
    mock_observer.join.assert_called_once()


def test_stop_watching_not_running():
    """Test stopping watcher when not running."""
    mock_observer = Mock()
    mock_observer.is_alive.return_value = False

    watcher = DirectoryWatcher(paths=["/path1"])
    watcher.observer = mock_observer

    # Stop watching
    watcher.stop_watching()

    # Should not try to stop observer
    mock_observer.stop.assert_not_called()


def test_stop_watching_no_observer():
    """Test stopping watcher when no observer exists."""
    watcher = DirectoryWatcher(paths=["/path1"])

    # Should not raise error
    watcher.stop_watching()


@patch("fileindex.services.watch.PollingObserver")
def test_watch_and_wait(mock_observer_class):
    """Test watch_and_wait convenience method."""
    mock_observer = Mock()
    # is_alive called in start_watching, watch_and_wait loop, and stop_watching
    mock_observer.is_alive.side_effect = [False, True, False, False]
    mock_observer_class.return_value = mock_observer

    watcher = DirectoryWatcher(paths=["/path1"])

    # Watch and wait
    watcher.watch_and_wait()

    # Should start observer
    mock_observer.start.assert_called_once()

    # Should join observer at least once
    assert mock_observer.join.call_count >= 1

    # Should stop observer
    mock_observer.stop.assert_called_once()


def test_watch_and_wait_stops_gracefully():
    """Test that watch_and_wait stops the observer gracefully when loop ends."""
    mock_observer = Mock()
    # Simulate observer becoming not alive after one iteration
    mock_observer.is_alive.side_effect = [False, True, False, False]

    watcher = DirectoryWatcher(paths=["/path1"])
    watcher.observer = mock_observer

    # Override start_watching to not create a new observer
    watcher.start_watching = Mock(return_value=mock_observer)

    # Watch and wait - should exit when is_alive returns False
    watcher.watch_and_wait()

    # Should have joined the observer at least once
    assert mock_observer.join.call_count >= 1

    # Should stop observer when done
    mock_observer.stop.assert_called_once()


@patch("fileindex.services.watch.PollingObserver")
def test_watch_and_wait_multiple_paths(mock_observer_class):
    """Test watch_and_wait with multiple paths."""
    mock_observer = Mock()
    mock_observer.is_alive.side_effect = [False, False, False]
    mock_observer_class.return_value = mock_observer

    paths = ["/path1", "/path2", "/path3"]
    watcher = DirectoryWatcher(paths=paths, recursive=False)

    # Start watching (not wait)
    watcher.start_watching()

    # Should schedule handler for each path
    assert mock_observer.schedule.call_count == 3

    # Check that recursive=False is respected
    calls = mock_observer.schedule.call_args_list
    for call in calls:
        assert call[1]["recursive"] is False
