from django.conf import settings
from django.db import models


# Field names are snake_case (Django convention) — serializers.py translates
# to/from the camelCase shape the extension's JS/TS has always used, so this
# model is the only place that needed to change, not every call site.
class Application(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='applications')
    job_key = models.CharField(max_length=512, blank=True)
    job_title = models.CharField(max_length=255, blank=True)
    company = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    job_url = models.URLField(max_length=2000, blank=True)
    employment_type = models.CharField(max_length=100, blank=True)
    job_description = models.TextField(blank=True)
    # No choices= constraint — the client (shared/constants.js's STATUSES)
    # already validates this; keeping it a plain CharField here matches the
    # project's existing "schemaless, don't over-constrain" philosophy for
    # this data (see CLAUDE.md's Data Model section).
    status = models.CharField(max_length=50, default='Pending')
    application_date = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)
    cover_letter = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.job_title} at {self.company} ({self.user_id})'


# One row per user — same "one candidate profile, not versioned" scope as
# the chrome.storage.local "profile" key it replaces.
class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    resume_file_name = models.CharField(max_length=255, blank=True)
    resume_text = models.TextField(blank=True)
    uploaded_at = models.CharField(max_length=64, blank=True)
    full_name = models.CharField(max_length=255, blank=True)
    email = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=100, blank=True)
    summary = models.TextField(blank=True)
    experience = models.JSONField(default=list, blank=True)
    education = models.JSONField(default=list, blank=True)
    projects = models.JSONField(default=list, blank=True)
    skills = models.JSONField(default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)
    certifications = models.JSONField(default=list, blank=True)
    interests = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f'Profile({self.user_id})'


class UserSettings(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='settings')
    auto_detect = models.BooleanField(default=True)

    def __str__(self):
        return f'UserSettings({self.user_id})'
