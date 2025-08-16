import os, tempfile, filecmp

from django.test import TestCase


def create_text_file(filepath, contents):
    with open(filepath, "w") as o:
        o.write(contents)


from fileindex.fileutils import analyze_file, smartlink, smartcopy, smartadd


class AnalyzeFileTestCase(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.test_file_name = os.path.join(self.tmpdir.name, "test.txt")
        create_text_file(self.test_file_name, "foobar\n")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_analyze_file(self):
        results = analyze_file(self.test_file_name)
        self.assertEqual(results["sha1"], "TCEIDLOJ7Q3FKB35YLKNOV6UQC26UDQR")
        self.assertEqual(
            results["sha512"],
            "46NYVURLGSSUX2MZ6TVN3YXORFOCBDKLHWB7DFKLMESV2JKWVC3TO46A3QBBBKQEJ76MU2BUQOKGBFM4XSPXHUYHSJRPZC6JGXKGEYQ=",
        )
        self.assertEqual(results["mime_type"], "text/plain")
        self.assertEqual(results["size"], 7)


class SmartLinkTestCase(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.test_file_name = os.path.join(self.tmpdir.name, "test.txt")
        self.test_dst_name = os.path.join(self.tmpdir.name, "test2.txt")
        create_text_file(self.test_file_name, "foobar\n")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_smartlink(self):
        self.assertEqual(1, os.lstat(self.test_file_name).st_nlink)
        smartlink(self.test_file_name, self.test_dst_name)
        self.assertEqual(2, os.lstat(self.test_dst_name).st_nlink)
        self.assertEqual(2, os.lstat(self.test_file_name).st_nlink)

    def test_smartlink_with_copy(self):
        self.assertEqual(1, os.lstat(self.test_file_name).st_nlink)
        create_text_file(self.test_dst_name, "foobar\n")

        smartlink(self.test_file_name, self.test_dst_name)
        self.assertEqual(2, os.lstat(self.test_dst_name).st_nlink)
        self.assertEqual(2, os.lstat(self.test_file_name).st_nlink)


class SmartAddTestCase(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.test_file_name = os.path.join(self.tmpdir.name, "test.txt")
        self.test_dst_name = os.path.join(self.tmpdir.name, "test2.txt")
        create_text_file(self.test_file_name, "foobar\n")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_smartadd(self):
        self.assertEqual(1, os.lstat(self.test_file_name).st_nlink)
        smartadd(self.test_file_name, self.test_dst_name)
        self.assertEqual(2, os.lstat(self.test_dst_name).st_nlink)
        self.assertEqual(2, os.lstat(self.test_file_name).st_nlink)

    def test_smartadd_with_copy(self):
        self.assertEqual(1, os.lstat(self.test_file_name).st_nlink)
        create_text_file(self.test_dst_name, "foobar\n")

        smartadd(self.test_file_name, self.test_dst_name)
        self.assertEqual(2, os.lstat(self.test_dst_name).st_nlink)
        self.assertEqual(2, os.lstat(self.test_file_name).st_nlink)
