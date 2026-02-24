from django.urls import include, path

urlpatterns = [
    path("fileindex/", include("fileindex.urls")),
]
