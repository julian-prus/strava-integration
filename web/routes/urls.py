from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/fetch-gpx/", views.api_fetch_gpx, name="api-fetch-gpx"),
    path("api/upload-gpx/", views.api_upload_gpx, name="api-upload-gpx"),
    path("api/normalize/", views.api_normalize, name="api-normalize"),
]
