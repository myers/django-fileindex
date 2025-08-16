from django.test import TestCase
from django.core.management import call_command
from unittest.mock import patch, MagicMock
from io import StringIO
import sys


class ManagementCommandsTestCase(TestCase):
    def test_worker_command_imports(self):
        """Test that worker command can be imported"""
        from fileindex.management.commands import worker
        self.assertTrue(hasattr(worker, 'Command'))
        
    def test_fileindex_add_command_imports(self):
        """Test that fileindex_add command can be imported"""
        from fileindex.management.commands import fileindex_add
        self.assertTrue(hasattr(fileindex_add, 'Command'))
        
    def test_fileindex_watch_command_imports(self):
        """Test that fileindex_watch command can be imported"""
        from fileindex.management.commands import fileindex_watch
        self.assertTrue(hasattr(fileindex_watch, 'Command'))
        
    def test_fileindex_create_avif_for_gif_imports(self):
        """Test that create_avif_for_gif command can be imported"""
        from fileindex.management.commands import fileindex_create_avif_for_gif
        self.assertTrue(hasattr(fileindex_create_avif_for_gif, 'Command'))