from django.test import TestCase
from django.core.files.base import ContentFile
from PIL import Image
from pathlib import Path
import json
import tempfile

from fileindex.models import (
    IndexedFile, IndexedImage, FilePath, 
    indexedfile_added, indexedimage_added,
    create_indexedimage_from_indexedfile,
    create_avif_from_gif
)


class ModelSignalsTestCase(TestCase):
    def test_indexedfile_added_signal(self):
        """Test that indexedfile_added signal is sent"""
        signal_received = []
        
        def handler(sender, instance, **kwargs):
            signal_received.append(instance)
            
        indexedfile_added.connect(handler)
        
        try:
            # Create a test file
            test_path = Path("test_signal.txt")
            test_path.write_text("test content")
            
            indexed_file, _ = IndexedFile.objects.get_or_create_from_file(test_path)
            test_path.unlink()
            
            self.assertEqual(len(signal_received), 1)
            self.assertEqual(signal_received[0], indexed_file)
        finally:
            indexedfile_added.disconnect(handler)
            
    def test_create_indexedimage_from_indexedfile_signal(self):
        """Test automatic IndexedImage creation for image files"""
        # Create an image file
        img_path = Path("test_image.png")
        img = Image.new('RGB', (50, 50), color='yellow')
        img.save(img_path)
        
        indexed_file, _ = IndexedFile.objects.get_or_create_from_file(img_path)
        img_path.unlink()
        
        # Check that IndexedImage was created automatically
        self.assertTrue(hasattr(indexed_file, 'indexedimage'))
        self.assertEqual(indexed_file.indexedimage.width, 50)
        self.assertEqual(indexed_file.indexedimage.height, 50)
        
        
class IndexedFileModelTestCase(TestCase):
    def test_extension_for_various_formats(self):
        """Test extension_for method with various file types"""
        indexed_file = IndexedFile()
        
        # Test with filename extensions
        self.assertEqual(indexed_file.extension_for("image.jpg"), ".jpg")
        self.assertEqual(indexed_file.extension_for("IMAGE.JPEG"), ".jpg")
        self.assertEqual(indexed_file.extension_for("file.txt"), ".txt")
        self.assertEqual(indexed_file.extension_for("video.mov"), ".mov")
        self.assertEqual(indexed_file.extension_for("image.png"), ".png")
        self.assertEqual(indexed_file.extension_for("anim.gif"), ".gif")
        self.assertEqual(indexed_file.extension_for("photo.heic"), ".heic")
        self.assertEqual(indexed_file.extension_for("video.gifv"), ".gifv")
        self.assertEqual(indexed_file.extension_for("image.webp"), ".webp")
        self.assertEqual(indexed_file.extension_for("image.avif"), ".webp")  # Note: returns .webp
        
        # Test with MIME types
        indexed_file.mime_type = "image/jpeg"
        self.assertEqual(indexed_file.extension_for("noext"), ".jpg")
        
        indexed_file.mime_type = "image/gif"
        self.assertEqual(indexed_file.extension_for("noext"), ".gif")
        
        indexed_file.mime_type = "image/png"
        self.assertEqual(indexed_file.extension_for("noext"), ".png")
        
        indexed_file.mime_type = "image/webp"
        self.assertEqual(indexed_file.extension_for("noext"), ".webp")
        
        indexed_file.mime_type = "image/avif"
        self.assertEqual(indexed_file.extension_for("noext"), ".avif")
        
    def test_extension_for_unknown_type(self):
        """Test extension_for raises exception for unknown types"""
        indexed_file = IndexedFile()
        indexed_file.mime_type = "application/unknown"
        
        with self.assertRaises(Exception) as ctx:
            indexed_file.extension_for("unknown.xyz")
        self.assertIn("Don't know how to standardize", str(ctx.exception))
        
    def test_get_duration_non_media(self):
        """Test get_duration returns None for non-media files"""
        indexed_file = IndexedFile(mime_type="text/plain")
        self.assertIsNone(indexed_file.get_duration())
        
    def test_str_representation(self):
        """Test string representation of IndexedFile"""
        indexed_file = IndexedFile(sha512="ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        self.assertEqual(str(indexed_file), "ABCDEFGHIJ...")
        
    def test_derived_from_relationship(self):
        """Test derived_from relationship"""
        # Create original file
        original_path = Path("original.txt")
        original_path.write_text("original content")
        original_file, _ = IndexedFile.objects.get_or_create_from_file(original_path)
        original_path.unlink()
        
        # Create derived file
        derived_path = Path("derived.txt")
        derived_path.write_text("derived content")
        derived_file, _ = IndexedFile.objects.get_or_create_from_file(
            derived_path, derived_from=original_file
        )
        derived_path.unlink()
        
        self.assertEqual(derived_file.derived_from, original_file)
        self.assertIn(derived_file, original_file.derived_files.all())
        

class IndexedImageModelTestCase(TestCase):
    def test_get_or_create_from_non_image(self):
        """Test that non-image files raise ValueError"""
        # Create a text file
        text_path = Path("test.txt")
        text_path.write_text("not an image")
        indexed_file, _ = IndexedFile.objects.get_or_create_from_file(text_path)
        text_path.unlink()
        
        with self.assertRaises(ValueError) as ctx:
            IndexedImage.objects.get_or_create_from_indexedfile(indexed_file)
        self.assertIn("Not an image", str(ctx.exception))
        
    def test_file_property(self):
        """Test that file property returns indexedfile's file"""
        img_path = Path("test.png")
        img = Image.new('RGB', (10, 10))
        img.save(img_path)
        
        indexed_file, _ = IndexedFile.objects.get_or_create_from_file(img_path)
        img_path.unlink()
        
        indexed_image = indexed_file.indexedimage
        self.assertEqual(indexed_image.file, indexed_file.file)
        

class FilePathModelTestCase(TestCase):
    def test_filepath_str_representation(self):
        """Test string representation of FilePath"""
        filepath = FilePath(pk=123, path="/test/path/file.txt")
        self.assertEqual(str(filepath), "(123) '/test/path/file.txt'")
        
    def test_multiple_filepaths_same_file(self):
        """Test multiple FilePaths can point to same IndexedFile"""
        # Create first file
        path1 = Path("file1.txt")
        path1.write_text("same content")
        indexed_file1, _ = IndexedFile.objects.get_or_create_from_file(path1)
        
        # Create second file with same content
        path2 = Path("file2.txt") 
        path2.write_text("same content")
        indexed_file2, _ = IndexedFile.objects.get_or_create_from_file(path2)
        
        # Clean up
        path1.unlink()
        path2.unlink()
        
        # Should be the same IndexedFile
        self.assertEqual(indexed_file1, indexed_file2)
        # But different FilePaths
        self.assertEqual(indexed_file1.filepath_set.count(), 2)
        paths = [fp.path for fp in indexed_file1.filepath_set.all()]
        self.assertIn(str(path1.absolute()), paths)
        self.assertIn(str(path2.absolute()), paths)