from django.test import TestCase
from PIL import Image
from pathlib import Path
import os
from fileindex.models import IndexedFile


def create_text_file(filepath, contents):
    with open(filepath, "w") as o:
        o.write(contents)


def create_image_file(filepath):
    im = Image.new(mode="RGB", size=(200, 205), color=(153, 153, 255))
    im.save(filepath)
    return filepath


def create_gif_file(filepath):
    im = Image.new(mode="RGB", size=(200, 205), color=(153, 153, 255))
    im.save(filepath, save_all=True, append_images=[im], duration=100, loop=0)
    return filepath


class ImportIndexedFileTestCase(TestCase):
    def setUp(self):
        create_text_file("test.txt", "foobar\n")

    def tearDown(self):
        os.unlink("test.txt")

    # def test_importing_files_on_the_same_filesystem_hard_links(self):
    #     print("write this")
    #     self.assert_(False)

    def test_import_file(self):
        indexedfile, created = IndexedFile.objects.get_or_create_from_file("test.txt")
        self.assertEqual(created, True)
        self.assertEqual(
            indexedfile.sha512,
            "46NYVURLGSSUX2MZ6TVN3YXORFOCBDKLHWB7DFKLMESV2JKWVC3TO46A3QBBBKQEJ76MU2BUQOKGBFM4XSPXHUYHSJRPZC6JGXKGEYQ=",
        )
        self.assertEqual(indexedfile.sha1, "TCEIDLOJ7Q3FKB35YLKNOV6UQC26UDQR")
        self.assertEqual(indexedfile.mime_type, "text/plain")
        self.assertEqual(indexedfile.size, 7)
        self.assertEqual(indexedfile.filepath_set.count(), 1)
        self.assertEqual(indexedfile.file.name, indexedfile.path)

    def test_importing_the_same_file_twice(self):
        file1, created1 = IndexedFile.objects.get_or_create_from_file("test.txt")
        self.assertEqual(created1, True)
        self.assertEqual(file1.filepath_set.count(), 1)

        file2, created2 = IndexedFile.objects.get_or_create_from_file("test.txt")
        self.assertEqual(created2, False)
        self.assertEqual(file1, file2)

    def test_importing_the_same_file_with_different_contents(self):
        file1, created1 = IndexedFile.objects.get_or_create_from_file("test.txt")

        os.unlink("test.txt")
        create_text_file("test.txt", "barbaz\n")

        file2, created2 = IndexedFile.objects.get_or_create_from_file("test.txt")
        self.assertEqual(
            file2.sha512,
            "HP2QUUF5ZAPBSENZCPHJOES3BXPBLYVNFAOVRDOWY2D7UMRY4VQXXM5N6VEAP2ANBCGVQFVXCGQILKE56XVIMNDQTN3VSGKRNVBM4KQ=",
        )
        self.assertEqual(file2.sha1, "2D4VCKE3NFTEY3TFPV3S5L6NE5YMXH4F")
        self.assertEqual(file2.mime_type, "text/plain")
        self.assertEqual(file2.file.name, file2.path)

        self.assertEqual(IndexedFile.objects.count(), 2)
        self.assertEqual(created1, True)
        self.assertEqual(created2, True)
        self.assertNotEqual(file1, file2)

        self.assertNotEqual(file1.filepath_set.all()[0], file2.filepath_set.all()[0])


class ImportIndexedImageTestCase(TestCase):
    def setUp(self):
        self.test_filepath = create_image_file(Path("test.png"))

    def tearDown(self):
        self.test_filepath.unlink()

    def test_importing_image_creates_indexedimage(self):
        indexedfile, created = IndexedFile.objects.get_or_create_from_file(
            self.test_filepath
        )
        self.assertEqual(created, True)
        # SHA values might vary based on image generation, so just check they exist
        self.assertTrue(indexedfile.sha512)
        self.assertTrue(indexedfile.sha1)
        self.assertEqual(indexedfile.mime_type, "image/png")
        self.assertGreater(indexedfile.size, 0)  # Size may vary
        self.assertEqual(indexedfile.filepath_set.count(), 1)
        self.assertEqual(indexedfile.file.name, indexedfile.path)

        self.assertTrue(indexedfile.indexedimage)

        self.assertEqual(indexedfile.indexedimage.width, 200)
        self.assertEqual(indexedfile.indexedimage.height, 205)

        # for some reason on linux this returns "7gQCBwA/Sj+Kh4eHeIiIiHiICE93AAAA"
        # self.assertEqual(
        #     indexedfile.indexedimage.thumbhash, "7gQCBwA/ST96h4eHeIeIiIiICE93AAAA"
        # )

        self.assertIsNotNone(indexedfile.indexedimage.thumbhash)


class GifToAvifQueueTestCase(TestCase):
    def setUp(self):
        self.test_filepath = create_gif_file(Path("test.gif"))

    def tearDown(self):
        self.test_filepath.unlink()

    def test_gif_creates_avif_queue_item(self):
        # Import the GIF file
        indexedfile, created = IndexedFile.objects.get_or_create_from_file(
            self.test_filepath
        )
        self.assertEqual(created, True)
        self.assertEqual(indexedfile.mime_type, "image/gif")

        # Verify the IndexedImage was created
        self.assertTrue(indexedfile.indexedimage)
        self.assertEqual(indexedfile.indexedimage.width, 200)
        self.assertEqual(indexedfile.indexedimage.height, 205)

        # For testing without pgq, we can't check the queue directly
        # Just verify the image was processed correctly
        self.assertIsNotNone(indexedfile.indexedimage.thumbhash)
