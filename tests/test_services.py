from django.test import TestCase
from unittest.mock import patch, MagicMock
from PIL import Image
from pathlib import Path

from fileindex.models import IndexedFile, IndexedImage
from fileindex.services.avif_generation import enqueue_creating_avif_from_gif


class ServicesTestCase(TestCase):
    def setUp(self):
        # Create a test GIF file
        self.gif_path = Path("test.gif")
        img = Image.new('RGB', (100, 100), color='blue')
        img.save(self.gif_path, format='GIF')
        
        # Create IndexedFile and IndexedImage
        self.indexed_file, _ = IndexedFile.objects.get_or_create_from_file(self.gif_path)
        self.indexed_image = self.indexed_file.indexedimage
        
    def tearDown(self):
        if self.gif_path.exists():
            self.gif_path.unlink()
            
    def test_enqueue_creating_avif_from_gif_small_image(self):
        """Test that small images are skipped"""
        # Create a small image
        self.indexed_image.width = 50
        self.indexed_image.height = 50
        self.indexed_image.save()
        
        with patch('fileindex.services.logger') as mock_logger:
            enqueue_creating_avif_from_gif(self.indexed_image)
            mock_logger.info.assert_called_once()
            self.assertIn("smaller than 64 px", mock_logger.info.call_args[0][0])
            
    def test_enqueue_creating_avif_from_gif_long_duration_small_size(self):
        """Test that long duration but small size GIFs are skipped"""
        self.indexed_image.width = 100
        self.indexed_image.height = 100
        self.indexed_image.save()
        
        # Mock get_duration to return > 30 seconds
        with patch.object(self.indexed_file, 'get_duration', return_value=35):
            self.indexed_file.size = 500 * 1024  # 500KB
            self.indexed_file.save()
            
            with patch('fileindex.services.logger') as mock_logger:
                enqueue_creating_avif_from_gif(self.indexed_image)
                mock_logger.info.assert_called_once()
                self.assertIn("long duration but small size", mock_logger.info.call_args[0][0])
                
    def test_enqueue_creating_avif_from_gif_success(self):
        """Test successful enqueuing"""
        self.indexed_image.width = 100
        self.indexed_image.height = 100
        self.indexed_image.save()
        
        with patch('fileindex.services.avif_creation_queue') as mock_queue:
            enqueue_creating_avif_from_gif(self.indexed_image)
            mock_queue.enqueue.assert_called_once_with(
                "create_avif_from_gif", 
                {"indexed_file_id": self.indexed_file.id}
            )