"""Tests for Django admin customizations."""

import pytest
from django.contrib.auth.models import User
from django.test import Client

from fileindex.factories import IndexedFileFactory


@pytest.fixture
def admin_client(db):
    user = User.objects.create_superuser("admin", "admin@test.com", "password")
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_admin_changelist_renders(admin_client):
    """Loading the IndexedFile admin list page should not 500."""
    IndexedFileFactory.create(corrupt=True)
    IndexedFileFactory.create(corrupt=False)
    IndexedFileFactory.create(corrupt=None)

    response = admin_client.get("/admin/fileindex/indexedfile/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_detail_renders(admin_client):
    """Loading the IndexedFile admin detail page should not 500."""
    indexed_file = IndexedFileFactory.create(
        metadata={"pdf": {"pages": 10}},
    )

    response = admin_client.get(f"/admin/fileindex/indexedfile/{indexed_file.pk}/change/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_detail_view_renders(admin_client):
    """Loading the IndexedFile detail view should not 500."""
    indexed_file = IndexedFileFactory.create()

    response = admin_client.get(f"/fileindex/files/{indexed_file.pk}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_no_metadata_view_renders(admin_client):
    """Loading the files-without-metadata staff view should not 500."""
    IndexedFileFactory.create(metadata={})

    response = admin_client.get("/fileindex/admin/no-metadata/")
    assert response.status_code == 200
