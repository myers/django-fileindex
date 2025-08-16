from django.urls import path, include

urlpatterns = [
    path('fileindex/', include('fileindex.urls')),
]