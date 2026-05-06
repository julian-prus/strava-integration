from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/fetch-gpx/", views.api_fetch_gpx, name="api-fetch-gpx"),
    path("api/upload-gpx/", views.api_upload_gpx, name="api-upload-gpx"),
    path("api/normalize/", views.api_normalize, name="api-normalize"),
    path("api/explore-segments/", views.api_explore_segments, name="api-explore-segments"),
    path("api/snap-to-segments/", views.api_snap_to_segments, name="api-snap-to-segments"),
    path("api/build-route/", views.api_build_route, name="api-build-route"),
]
