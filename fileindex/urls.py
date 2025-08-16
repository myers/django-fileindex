from django.urls import path

from .views import (
    FilesWithoutMetadataView,
    IndexedFileDetail,
    VideoMetadataIssuesView,
    add,
    lookup,
)

app_name = "fileindex"
urlpatterns = [
    path("lookup", lookup, name="lookup"),
    path("add", add, name="add"),
    path("files/<int:pk>/", IndexedFileDetail.as_view(), name="detail"),
    path("admin/no-metadata/", FilesWithoutMetadataView.as_view(), name="no_metadata"),
    path("admin/video-issues/", VideoMetadataIssuesView.as_view(), name="video_issues"),
]
