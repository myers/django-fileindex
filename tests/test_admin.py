"""Tests for Django admin customizations."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from fileindex.admin import IndexedFileAdmin
from fileindex.factories import IndexedFileFactory
from fileindex.models import IndexedFile


@pytest.mark.django_db
class TestIndexedFileAdmin:
    """Test cases for IndexedFileAdmin customizations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.site = AdminSite()
        self.admin = IndexedFileAdmin(IndexedFile, self.site)
        self.factory = RequestFactory()
        self.request = self.factory.get("/admin/fileindex/indexedfile/")

    def test_metadata_pretty_with_valid_json(self):
        """Test that metadata_pretty correctly formats JSON data."""
        # Create an IndexedFile with metadata
        metadata = {
            "width": 1920,
            "height": 1080,
            "thumbhash": "test_hash",
            "duration": 5000,
        }
        indexed_file = IndexedFileFactory.create(metadata=metadata)

        # Call the metadata_pretty method
        result = self.admin.metadata_pretty(indexed_file)

        # Verify it returns formatted HTML
        assert "<pre" in result
        assert "1920" in result
        assert "1080" in result
        assert "test_hash" in result
        # Check that JSON is pretty-printed (has indentation)
        assert "\n  " in result  # Indented content

    def test_metadata_pretty_with_empty_metadata(self):
        """Test metadata_pretty with empty metadata."""
        indexed_file = IndexedFileFactory.create(metadata={})
        result = self.admin.metadata_pretty(indexed_file)
        assert result == "-"

    def test_metadata_pretty_with_none_handling(self):
        """Test metadata_pretty handles None-like metadata gracefully."""
        # The metadata field has default=dict, so we test with an object that has empty metadata
        indexed_file = IndexedFileFactory.create()
        indexed_file.metadata = None  # Manually set to None for testing the method
        result = self.admin.metadata_pretty(indexed_file)
        assert result == "-"

    def test_metadata_pretty_with_complex_metadata(self):
        """Test metadata_pretty with nested and complex metadata."""
        metadata = {
            "video": {
                "codec": "h264",
                "bitrate": 5000000,
                "fps": 30,
            },
            "audio": {
                "codec": "aac",
                "channels": 2,
                "sample_rate": 44100,
            },
            "thumbnails": ["thumb1.jpg", "thumb2.jpg"],
            "tags": None,
        }
        indexed_file = IndexedFileFactory.create(metadata=metadata)

        result = self.admin.metadata_pretty(indexed_file)

        # Verify structure is preserved
        assert "<pre" in result
        assert '"video"' in result
        assert '"codec": "h264"' in result
        assert '"audio"' in result
        # Verify it's properly sorted (sort_keys=True)
        assert result.index('"audio"') < result.index('"video"')  # alphabetical order

    def test_readonly_fields_includes_metadata_pretty(self):
        """Test that readonly_fields includes metadata_pretty instead of metadata."""
        readonly_fields = self.admin.get_readonly_fields(self.request, None)

        # metadata_pretty should be in the list
        assert "metadata_pretty" in readonly_fields
        # original metadata field should not be in the list
        assert "metadata" not in readonly_fields

    def test_fields_configuration(self):
        """Test that the fields configuration includes metadata_pretty."""
        assert "metadata_pretty" in self.admin.fields
        assert "metadata" not in self.admin.fields

    def test_admin_permissions(self):
        """Test that admin permissions are correctly configured."""
        # Verify add permission is disabled
        assert not self.admin.has_add_permission(self.request)

        # Verify delete permission is disabled
        indexed_file = IndexedFileFactory.create()
        assert not self.admin.has_delete_permission(self.request, indexed_file)
