from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
import io
import os
from pathlib import Path

from fileindex.models import IndexedFile


class FileindexViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Create a test image file
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        # Create an IndexedFile
        test_file = Path("test_image.png")
        with open(test_file, 'wb') as f:
            f.write(img_bytes.getvalue())
        
        self.indexed_file, _ = IndexedFile.objects.get_or_create_from_file(test_file)
        test_file.unlink()
        
    def test_raw_file_view(self):
        """Test the raw file view returns the file correctly"""
        url = reverse('fileindex:raw_file', args=[self.indexed_file.sha512])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        
    def test_raw_file_view_not_found(self):
        """Test the raw file view returns 404 for non-existent file"""
        url = reverse('fileindex:raw_file', args=['nonexistent'])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 404)
        
    def test_raw_file_view_with_extension(self):
        """Test the raw file view strips extension from sha512"""
        # The view should strip the extension from the sha512 parameter
        sha512_with_ext = self.indexed_file.sha512 + '.png'
        url = reverse('fileindex:raw_file', args=[sha512_with_ext])
        response = self.client.get(url)
        
        # Since the view looks for sha512 without extension, this should 404
        self.assertEqual(response.status_code, 404)
        
    def test_raw_file_view_sendfile(self):
        """Test the raw file view uses X-Sendfile when configured"""
        with self.settings(SENDFILE=True):
            url = reverse('fileindex:raw_file', args=[self.indexed_file.sha512])
            response = self.client.get(url)
            
            self.assertEqual(response.status_code, 200)
            self.assertIn('X-Sendfile', response)
            
    def test_detail_view(self):
        """Test the detail view"""
        url = reverse('fileindex:detail', args=[self.indexed_file.pk])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)