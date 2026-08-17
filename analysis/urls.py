# Mounted at /api/ by jobtracker_server/urls.py, so this resolves to
# /api/analyze/ — the URL popup.js's ANALYSIS_SERVER_URL points at.
from django.urls import path

from . import views

urlpatterns = [
    path("analyze/", views.analyze, name="analyze"),
]
