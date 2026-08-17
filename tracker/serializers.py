"""Plain dict-shaping functions translating between the DB models' Django-
conventional snake_case fields and the camelCase JSON shape the extension's
JS/TS has used since the MVP (chrome.storage.local held these same shapes
directly). No serializer framework — this is the same "hand-build the dict"
approach assistant/prompts.py's _format_profile/_format_application already
use elsewhere in this project.
"""


def application_to_json(app):
    return {
        'id': app.id,
        'jobKey': app.job_key,
        'jobTitle': app.job_title,
        'company': app.company,
        'location': app.location,
        'jobUrl': app.job_url,
        'employmentType': app.employment_type,
        'jobDescription': app.job_description,
        'status': app.status,
        'applicationDate': app.application_date,
        'notes': app.notes,
        'coverLetter': app.cover_letter,
        'createdAt': app.created_at.isoformat(),
        'updatedAt': app.updated_at.isoformat(),
    }


# Only copies over fields actually present in `data` (partial updates from
# PATCH shouldn't blank out everything else) — the caller applies these onto
# an existing or new model instance.
_APPLICATION_FIELD_MAP = {
    'jobKey': 'job_key',
    'jobTitle': 'job_title',
    'company': 'company',
    'location': 'location',
    'jobUrl': 'job_url',
    'employmentType': 'employment_type',
    'jobDescription': 'job_description',
    'status': 'status',
    'applicationDate': 'application_date',
    'notes': 'notes',
    'coverLetter': 'cover_letter',
}


def apply_application_fields(app, data):
    for json_key, field_name in _APPLICATION_FIELD_MAP.items():
        if json_key in data:
            setattr(app, field_name, data[json_key] or '')
    return app


def profile_to_json(profile):
    return {
        'resumeFileName': profile.resume_file_name,
        'resumeText': profile.resume_text,
        'uploadedAt': profile.uploaded_at,
        'fullName': profile.full_name,
        'email': profile.email,
        'phone': profile.phone,
        'summary': profile.summary,
        'experience': profile.experience,
        'education': profile.education,
        'projects': profile.projects,
        'skills': profile.skills,
        'languages': profile.languages,
        'certifications': profile.certifications,
        'interests': profile.interests,
    }


_PROFILE_LIST_FIELDS = {'experience', 'education', 'projects', 'skills', 'languages', 'certifications', 'interests'}
_PROFILE_FIELD_MAP = {
    'resumeFileName': 'resume_file_name',
    'resumeText': 'resume_text',
    'uploadedAt': 'uploaded_at',
    'fullName': 'full_name',
    'email': 'email',
    'phone': 'phone',
    'summary': 'summary',
    'experience': 'experience',
    'education': 'education',
    'projects': 'projects',
    'skills': 'skills',
    'languages': 'languages',
    'certifications': 'certifications',
    'interests': 'interests',
}


def apply_profile_fields(profile, data):
    for json_key, field_name in _PROFILE_FIELD_MAP.items():
        if json_key in data:
            value = data[json_key]
            setattr(profile, field_name, value if field_name in _PROFILE_LIST_FIELDS else (value or ''))
    return profile


def settings_to_json(user_settings):
    return {'autoDetect': user_settings.auto_detect}


def apply_settings_fields(user_settings, data):
    if 'autoDetect' in data:
        user_settings.auto_detect = bool(data['autoDetect'])
    return user_settings
