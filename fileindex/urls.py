from django.urls import path

from .views import IndexedFileDetail, lookup, add, raw_file

app_name = "fileindex"
urlpatterns = [
    path("lookup", lookup, name="lookup"),
    path("add", add, name="add"),
    path("files/<int:pk>/", IndexedFileDetail.as_view(), name="detail"),
    path("files/<str:sha512>", raw_file, name="raw_file"),
]
