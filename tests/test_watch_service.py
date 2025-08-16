import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from django.test import TestCase

from fileindex.watch_service import (
    FileImportEventHandler,
    create_file_watcher,
    watch_and_import
)
from fileindex.models import IndexedFile


class WatchServiceTestCase(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_file_import_event_handler_created(self):
        """Test FileImportEventHandler processes created files"""
        handler = FileImportEventHandler(remove_after_import=False)
        
        # Create a test file
        test_file = os.path.join(self.temp_dir, 'test.txt')
        Path(test_file).write_text('test content')
        
        # Create mock event
        event = MagicMock()
        event.is_directory = False
        event.src_path = test_file
        
        # Process the event
        handler.on_created(event)
        
        # Check file was imported
        self.assertEqual(IndexedFile.objects.count(), 1)
        self.assertTrue(os.path.exists(test_file))  # File still exists
        
    def test_file_import_event_handler_remove_after(self):
        """Test FileImportEventHandler removes files when configured"""
        handler = FileImportEventHandler(remove_after_import=True)
        
        # Create a test file
        test_file = os.path.join(self.temp_dir, 'test.txt')
        Path(test_file).write_text('test content')
        
        # Create mock event
        event = MagicMock()
        event.is_directory = False
        event.src_path = test_file
        
        # Process the event
        handler.on_created(event)
        
        # Check file was imported and removed
        self.assertEqual(IndexedFile.objects.count(), 1)
        self.assertFalse(os.path.exists(test_file))  # File removed
        
    def test_file_import_event_handler_skip_directory(self):
        """Test FileImportEventHandler skips directory events"""
        handler = FileImportEventHandler()
        
        # Create mock directory event
        event = MagicMock()
        event.is_directory = True
        event.src_path = self.temp_dir
        
        # Process the event
        handler.on_created(event)
        
        # No files should be imported
        self.assertEqual(IndexedFile.objects.count(), 0)
        
    def test_file_import_event_handler_moved(self):
        """Test FileImportEventHandler processes moved files"""
        handler = FileImportEventHandler()
        
        # Create a test file at destination
        dest_file = os.path.join(self.temp_dir, 'moved.txt')
        Path(dest_file).write_text('moved content')
        
        # Create mock event
        event = MagicMock()
        event.is_directory = False
        event.dest_path = dest_file
        
        # Process the event
        handler.on_moved(event)
        
        # Check file was imported
        self.assertEqual(IndexedFile.objects.count(), 1)
        
    def test_file_import_event_handler_duplicate_prevention(self):
        """Test FileImportEventHandler prevents duplicate processing"""
        handler = FileImportEventHandler()
        
        # Create a test file
        test_file = os.path.join(self.temp_dir, 'test.txt')
        Path(test_file).write_text('test content')
        
        # Create mock event
        event = MagicMock()
        event.is_directory = False
        event.src_path = test_file
        
        # Process the same event multiple times
        handler.on_created(event)
        handler.on_created(event)
        handler.on_modified(event)
        
        # Should only import once
        self.assertEqual(IndexedFile.objects.count(), 1)
        
    def test_create_file_watcher(self):
        """Test creating a file watcher"""
        paths = [self.temp_dir]
        observer = create_file_watcher(paths, remove_after_import=False)
        
        self.assertIsNotNone(observer)
        self.assertFalse(observer.is_alive())  # Not started yet
        
        # Check that handlers were scheduled
        self.assertTrue(len(observer._handlers) > 0)
        
    @patch('fileindex.file_import_service.import_paths')
    def test_watch_and_import_with_existing(self, mock_import_paths):
        """Test watch_and_import imports existing files"""
        mock_import_paths.return_value = {}  # No errors
        
        # Create existing file
        existing = os.path.join(self.temp_dir, 'existing.txt')
        Path(existing).write_text('existing')
        
        # Use threading to stop the watcher after a short time
        import threading
        def stop_after_delay():
            time.sleep(0.1)
            # This will cause KeyboardInterrupt in the main thread
            import os
            import signal
            os.kill(os.getpid(), signal.SIGINT)
        
        timer = threading.Timer(0.1, stop_after_delay)
        timer.start()
        
        try:
            watch_and_import(
                paths=[self.temp_dir],
                import_existing=True,
                remove_after_import=False
            )
        except KeyboardInterrupt:
            pass
        
        # Check that existing files were imported
        mock_import_paths.assert_called_once()
        
    def test_watch_and_import_callback(self):
        """Test watch_and_import calls callback when stopped"""
        callback_called = []
        
        def callback():
            callback_called.append(True)
        
        # Use threading to stop the watcher
        import threading
        def stop_after_delay():
            time.sleep(0.1)
            import os
            import signal
            os.kill(os.getpid(), signal.SIGINT)
        
        timer = threading.Timer(0.1, stop_after_delay)
        timer.start()
        
        try:
            watch_and_import(
                paths=[self.temp_dir],
                import_existing=False,
                callback=callback
            )
        except KeyboardInterrupt:
            pass
        
        # Callback should have been called
        self.assertTrue(len(callback_called) > 0)