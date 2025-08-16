import os
import tempfile
from pathlib import Path
from django.test import TestCase

from fileindex.file_import_service import (
    should_import_file,
    import_single_file,
    import_directory,
    import_paths
)
from fileindex.models import IndexedFile


class FileImportServiceTestCase(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        # Clean up temp files
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_should_import_file_hidden(self):
        """Test that hidden files are not imported"""
        hidden_file = os.path.join(self.temp_dir, '.hidden')
        Path(hidden_file).touch()
        
        self.assertFalse(should_import_file(hidden_file))
        
    def test_should_import_file_temp(self):
        """Test that temp files are not imported"""
        temp_files = [
            os.path.join(self.temp_dir, 'file.tmp'),
            os.path.join(self.temp_dir, 'file.temp'),
            os.path.join(self.temp_dir, 'file~'),
        ]
        
        for temp_file in temp_files:
            Path(temp_file).touch()
            self.assertFalse(should_import_file(temp_file))
            
    def test_should_import_file_empty(self):
        """Test that empty files are not imported"""
        empty_file = os.path.join(self.temp_dir, 'empty.txt')
        Path(empty_file).touch()
        
        self.assertFalse(should_import_file(empty_file))
        
    def test_should_import_file_valid(self):
        """Test that valid files are imported"""
        valid_file = os.path.join(self.temp_dir, 'valid.txt')
        Path(valid_file).write_text('content')
        
        self.assertTrue(should_import_file(valid_file))
        
    def test_import_single_file_success(self):
        """Test successful single file import"""
        test_file = os.path.join(self.temp_dir, 'test.txt')
        Path(test_file).write_text('test content')
        
        indexed_file, created, error = import_single_file(test_file)
        
        self.assertIsNotNone(indexed_file)
        self.assertTrue(created)
        self.assertIsNone(error)
        self.assertTrue(os.path.exists(test_file))  # Original still exists
        
    def test_import_single_file_with_removal(self):
        """Test single file import with removal"""
        test_file = os.path.join(self.temp_dir, 'test.txt')
        Path(test_file).write_text('test content')
        
        indexed_file, created, error = import_single_file(
            test_file, 
            remove_after_import=True
        )
        
        self.assertIsNotNone(indexed_file)
        self.assertTrue(created)
        self.assertIsNone(error)
        self.assertFalse(os.path.exists(test_file))  # Original removed
        
    def test_import_single_file_skip_hidden(self):
        """Test that hidden files are skipped"""
        hidden_file = os.path.join(self.temp_dir, '.hidden')
        Path(hidden_file).write_text('hidden content')
        
        indexed_file, created, error = import_single_file(hidden_file)
        
        self.assertIsNone(indexed_file)
        self.assertFalse(created)
        self.assertEqual(error, "File does not meet import criteria")
        
    def test_import_directory(self):
        """Test directory import"""
        # Create test files
        files = []
        for i in range(3):
            test_file = os.path.join(self.temp_dir, f'file{i}.txt')
            Path(test_file).write_text(f'content {i}')
            files.append(test_file)
            
        # Add a hidden file that should be skipped
        hidden = os.path.join(self.temp_dir, '.hidden')
        Path(hidden).write_text('hidden')
        
        errors = import_directory(self.temp_dir)
        
        self.assertEqual(len(errors), 1)  # Only the hidden file
        self.assertIn('.hidden', list(errors.keys())[0])
        
        # Check that valid files were imported
        self.assertEqual(IndexedFile.objects.count(), 3)
        
    def test_import_directory_recursive(self):
        """Test recursive directory import"""
        # Create subdirectory
        subdir = os.path.join(self.temp_dir, 'subdir')
        os.makedirs(subdir)
        
        # Create files in both directories
        Path(os.path.join(self.temp_dir, 'root.txt')).write_text('root')
        Path(os.path.join(subdir, 'sub.txt')).write_text('sub')
        
        errors = import_directory(self.temp_dir, recursive=True)
        
        self.assertEqual(len(errors), 0)
        self.assertEqual(IndexedFile.objects.count(), 2)
        
    def test_import_directory_non_recursive(self):
        """Test non-recursive directory import"""
        # Create subdirectory
        subdir = os.path.join(self.temp_dir, 'subdir')
        os.makedirs(subdir)
        
        # Create files in both directories
        Path(os.path.join(self.temp_dir, 'root.txt')).write_text('root')
        Path(os.path.join(subdir, 'sub.txt')).write_text('sub')
        
        errors = import_directory(self.temp_dir, recursive=False)
        
        self.assertEqual(len(errors), 0)
        self.assertEqual(IndexedFile.objects.count(), 1)  # Only root file
        
    def test_import_paths_mixed(self):
        """Test importing mixed files and directories"""
        # Create a file
        single_file = os.path.join(self.temp_dir, 'single.txt')
        Path(single_file).write_text('single')
        
        # Create a directory with files
        subdir = os.path.join(self.temp_dir, 'subdir')
        os.makedirs(subdir)
        Path(os.path.join(subdir, 'sub1.txt')).write_text('sub1')
        Path(os.path.join(subdir, 'sub2.txt')).write_text('sub2')
        
        paths = [single_file, subdir]
        errors = import_paths(paths)
        
        self.assertEqual(len(errors), 0)
        self.assertEqual(IndexedFile.objects.count(), 3)
        
    def test_import_paths_nonexistent(self):
        """Test importing nonexistent paths"""
        paths = ['/nonexistent/path', '/another/bad/path']
        errors = import_paths(paths)
        
        self.assertEqual(len(errors), 2)
        for path in paths:
            self.assertIn(path, errors)
            self.assertIn("does not exist", errors[path])