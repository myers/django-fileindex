"""
Service module for directory watching and file import operations.

This module provides reusable functionality for watching directories
and automatically importing new files as they are created or modified.
"""

import logging
from collections.abc import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

from fileindex.exceptions import ImportErrorType
from fileindex.services.file_import import import_directory, import_file

logger = logging.getLogger(__name__)


class WatchEventHandler(FileSystemEventHandler):
    """
    Event handler for file system events that triggers file imports.
    """

    def __init__(self, callback: Callable[[str], None]):
        """
        Initialize the event handler.

        Args:
            callback: Function to call with the file path when a file event occurs
        """
        self.callback = callback
        self.processed_files = set()

    def _should_process_file(self, filepath: str) -> bool:
        """Check if we should process this file event."""
        # Avoid processing the same file multiple times in quick succession
        if filepath in self.processed_files:
            return False

        # Clear cache periodically to prevent memory issues
        if len(self.processed_files) > 1000:
            self.processed_files.clear()

        self.processed_files.add(filepath)
        return True

    def on_close(self, event):
        """Handle file close events."""
        if not event.is_directory and self._should_process_file(event.src_path):
            self.callback(event.src_path)

    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory and self._should_process_file(event.src_path):
            self.callback(event.src_path)

    def on_moved(self, event):
        """Handle file move events."""
        if not event.is_directory and self._should_process_file(event.dest_path):
            self.callback(event.dest_path)


class DirectoryWatcher:
    """
    Service for watching directories and importing files.
    """

    def __init__(
        self,
        paths: list[str],
        delete_after: bool = False,
        recursive: bool = True,
        validate: bool = True,
        file_event_callback: Callable[[str, bool, str], None] | None = None,
        import_progress_callback: Callable[[str, bool, str | None], None] | None = None,
    ):
        """
        Initialize the directory watcher.

        Args:
            paths: List of directory paths to watch
            delete_after: Delete original files after successful import
            recursive: Watch subdirectories recursively
            validate: Validate files before importing
            file_event_callback: Callback for file events (filepath, success, message)
            import_progress_callback: Callback for initial import progress (filepath, success)
        """
        self.paths = paths
        self.delete_after = delete_after
        self.recursive = recursive
        self.validate = validate
        self.file_event_callback = file_event_callback
        self.import_progress_callback = import_progress_callback
        self.observer = None

    def import_existing_files(self) -> dict[str, dict]:
        """
        Import existing files from all watched directories.

        Returns:
            Dictionary mapping directory paths to import statistics
        """
        results = {}

        for path in self.paths:
            logger.info(f"Importing existing files from: {path}")

            stats = import_directory(
                path,
                recursive=self.recursive,
                delete_after=self.delete_after,
                validate=self.validate,
                progress_callback=self.import_progress_callback,
            )

            results[path] = stats

            logger.info(
                f"Imported from {path}: {stats['imported']} files, {stats['created']} new, {stats['skipped']} skipped"
            )

        return results

    def handle_file_event(self, filepath: str):
        """
        Handle a file event from the watcher.

        Args:
            filepath: Path to the file that triggered the event
        """
        logger.debug(f"Processing file event: {filepath}")

        indexed_file, created, error = import_file(
            filepath,
            delete_after=self.delete_after,
            validate=self.validate,
        )

        if self.file_event_callback:
            if error:
                if error == ImportErrorType.VALIDATION_FAILED:
                    self.file_event_callback(filepath, False, "Skipped: validation failed")
                else:
                    self.file_event_callback(filepath, False, f"Error: {str(error)}")
            else:
                status = "Created" if created else "Already indexed"
                self.file_event_callback(filepath, True, status)

        if error:
            logger.warning(f"Failed to import {filepath}: {error}")
        else:
            logger.info(f"{'Created' if created else 'Found existing'} IndexedFile for: {filepath}")

    def start_watching(self) -> PollingObserver:
        """
        Start watching the configured directories.

        Returns:
            The watchdog observer instance
        """
        if self.observer and self.observer.is_alive():
            logger.warning("Observer is already running")
            return self.observer

        # Create event handler
        event_handler = WatchEventHandler(self.handle_file_event)

        # Create and configure observer
        self.observer = PollingObserver()

        for path in self.paths:
            logger.info(f"Starting watch on: {path}")
            self.observer.schedule(event_handler, path, recursive=self.recursive)

        # Start the observer
        self.observer.start()
        logger.info("Directory watching started")

        return self.observer

    def stop_watching(self):
        """Stop watching directories."""
        if self.observer and self.observer.is_alive():
            logger.info("Stopping directory watcher...")
            self.observer.stop()
            self.observer.join()
            logger.info("Directory watcher stopped")
        else:
            logger.warning("Observer is not running")

    def watch_and_wait(self):
        """
        Start watching and wait until interrupted.

        This is a convenience method that starts watching and blocks
        until a KeyboardInterrupt is received.
        """
        observer = self.start_watching()

        try:
            while observer.is_alive():
                observer.join(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.stop_watching()
