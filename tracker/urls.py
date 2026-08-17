# Mounted at /api/ by jobtracker_server/urls.py.
from django.urls import path

from . import views

urlpatterns = [
    path("applications/", views.applications, name="applications"),
    path("applications/by-key/", views.application_by_key, name="application_by_key"),
    path("applications/clear/", views.clear_applications, name="clear_applications"),
    path("applications/<int:app_id>/", views.application_detail, name="application_detail"),
    path("profile/", views.profile, name="profile"),
    path("settings/", views.settings_view, name="settings"),
]
