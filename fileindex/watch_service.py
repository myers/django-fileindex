"""
Service module for file watching operations.
"""
import logging
from typing import List, Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

from .file_import_service import import_single_file

logger = logging.getLogger(__name__)


class FileImportEventHandler(FileSystemEventHandler):
    """
    Event handler that imports files when they are created or modified.
    """
    
    def __init__(self, remove_after_import: bool = False):
        self.remove_after_import = remove_after_import
        self.processed_files = set()
        
    def _process_file(self, filepath: str):
        """Process a file event."""
        # Avoid processing the same file multiple times in quick succession
        if filepath in self.processed_files:
            return
            
        self.processed_files.add(filepath)
        
        logger.info(f"Processing file event: {filepath}")
        indexed_file, created, error = import_single_file(
            filepath,
            only_hard_link=False,
            remove_after_import=self.remove_after_import
        )
        
        if error:
            logger.error(f"Failed to import {filepath}: {error}")
        else:
            logger.info(f"Successfully processed {filepath}")
            
        # Clear processed files cache periodically to prevent memory issues
        if len(self.processed_files) > 1000:
            self.processed_files.clear()
    
    def on_created(self, event):
        if not event.is_directory:
            self._process_file(event.src_path)
    
    def on_modified(self, event):
        if not event.is_directory:
            self._process_file(event.src_path)
    
    def on_moved(self, event):
        if not event.is_directory:
            self._process_file(event.dest_path)


def create_file_watcher(
    paths: List[str],
    remove_after_import: bool = False,
    use_polling: bool = True
) -> PollingObserver:
    """
    Create and configure a file system watcher.
    
    Args:
        paths: List of paths to watch
        remove_after_import: If True, delete files after successful import
        use_polling: If True, use polling observer (more reliable but slower)
        
    Returns:
        Configured observer instance (not started)
    """
    event_handler = FileImportEventHandler(remove_after_import=remove_after_import)
    
    if use_polling:
        observer = PollingObserver()
    else:
        # Use native observer for better performance
        from watchdog.observers import Observer
        observer = Observer()
    
    for path in paths:
        logger.info(f"Setting up watcher for: {path}")
        observer.schedule(event_handler, path, recursive=True)
    
    return observer


def watch_and_import(
    paths: List[str],
    remove_after_import: bool = False,
    import_existing: bool = True,
    callback: Callable = None
) -> None:
    """
    Watch directories for new files and import them.
    
    Args:
        paths: List of paths to watch
        remove_after_import: If True, delete files after successful import
        import_existing: If True, import existing files before starting watch
        callback: Optional callback function to call when observer stops
    """
    # Import existing files first if requested
    if import_existing:
        from .file_import_service import import_paths
        logger.info("Importing existing files...")
        errors = import_paths(paths, remove_after_import=remove_after_import)
        if errors:
            logger.warning(f"Encountered {len(errors)} errors during initial import")
    
    # Create and start observer
    observer = create_file_watcher(paths, remove_after_import=remove_after_import)
    observer.start()
    logger.info("File watcher started")
    
    try:
        # Keep running until interrupted
        while observer.is_alive():
            observer.join(1)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        observer.stop()
        observer.join()
        logger.info("File watcher stopped")
        
        if callback:
            callback()