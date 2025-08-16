from django.test import TestCase
from unittest.mock import patch, MagicMock, call
import subprocess
from pathlib import Path
from PIL import Image

from fileindex.models import IndexedFile
from fileindex.tasks import SubprocessError


class TasksTestCase(TestCase):
    def test_subprocess_error_class(self):
        """Test SubprocessError can be raised"""
        with self.assertRaises(SubprocessError):
            raise SubprocessError("Test error")
            
    @patch('fileindex.tasks.IndexedFile.objects.get')
    def test_create_avif_task_not_found(self, mock_get):
        """Test create_avif_from_gif with non-existent file"""
        from fileindex.tasks import create_avif_from_gif
        from django.core.exceptions import ObjectDoesNotExist
        
        mock_get.side_effect = ObjectDoesNotExist()
        
        # Mock job object
        mock_job = MagicMock()
        mock_job.args = {"indexed_file_id": 999999}
        
        # Should return None when file not found
        result = create_avif_from_gif(None, mock_job)
        self.assertIsNone(result)
        
    @patch('fileindex.tasks.IndexedFile.objects.get')
    def test_create_avif_task_already_exists(self, mock_get):
        """Test create_avif_from_gif when AVIF already exists"""
        from fileindex.tasks import create_avif_from_gif
        
        mock_file = MagicMock()
        mock_derived = MagicMock()
        mock_derived.filter.return_value.exists.return_value = True
        mock_file.derived_files = mock_derived
        mock_get.return_value = mock_file
        
        # Mock job object
        mock_job = MagicMock()
        mock_job.args = {"indexed_file_id": 1}
        
        # Should return None when AVIF already exists
        result = create_avif_from_gif(None, mock_job)
        self.assertIsNone(result)