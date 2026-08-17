# Mounted at /api/assistant/ by jobtracker_server/urls.py.
from django.urls import path

from . import views

urlpatterns = [
    path("parse-resume/", views.parse_resume, name="parse_resume"),
    path("cover-letter/", views.cover_letter, name="cover_letter"),
    path("answer/", views.answer, name="answer"),
]
