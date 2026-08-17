"""CRUD for Application/Profile/UserSettings — the replacement for what
chrome.storage.local used to do directly. Every view here is require_auth'd
and scoped to request.user; same _parse_body / @csrf_exempt / JsonResponse
style as analysis/views.py and assistant/views.py.
"""

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from accounts.auth import require_auth

from .models import Application, Profile, UserSettings
from .serializers import (
    apply_application_fields,
    apply_profile_fields,
    apply_settings_fields,
    application_to_json,
    profile_to_json,
    settings_to_json,
)


def _parse_body(request):
    try:
        return json.loads(request.body), None
    except json.JSONDecodeError:
        return None, JsonResponse({'error': 'Request body must be valid JSON.'}, status=400)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@require_auth
def applications(request):
    if request.method == 'GET':
        apps = Application.objects.filter(user=request.user)
        return JsonResponse([application_to_json(a) for a in apps], safe=False)

    body, error = _parse_body(request)
    if error:
        return error
    app = apply_application_fields(Application(user=request.user), body)
    app.save()
    return JsonResponse(application_to_json(app), status=201)


@csrf_exempt
@require_http_methods(['GET', 'PATCH', 'DELETE'])
@require_auth
def application_detail(request, app_id):
    try:
        app = Application.objects.get(id=app_id, user=request.user)
    except Application.DoesNotExist:
        return JsonResponse({'error': 'Not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(application_to_json(app))

    if request.method == 'DELETE':
        app.delete()
        return JsonResponse({'ok': True})

    body, error = _parse_body(request)
    if error:
        return error
    apply_application_fields(app, body)
    app.save()
    return JsonResponse(application_to_json(app))


@require_http_methods(['GET'])
@require_auth
def application_by_key(request):
    job_key = request.GET.get('jobKey', '')
    if not job_key:
        return JsonResponse({'error': 'Expected a "jobKey" query parameter.'}, status=400)
    app = Application.objects.filter(user=request.user, job_key=job_key).first()
    if app is None:
        return JsonResponse(None, safe=False)
    return JsonResponse(application_to_json(app))


@csrf_exempt
@require_http_methods(['DELETE'])
@require_auth
def clear_applications(request):
    Application.objects.filter(user=request.user).delete()
    return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['GET', 'PUT'])
@require_auth
def profile(request):
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)

    if request.method == 'GET':
        return JsonResponse(profile_to_json(profile_obj))

    body, error = _parse_body(request)
    if error:
        return error
    apply_profile_fields(profile_obj, body)
    profile_obj.save()
    return JsonResponse(profile_to_json(profile_obj))


@csrf_exempt
@require_http_methods(['GET', 'PUT'])
@require_auth
def settings_view(request):
    settings_obj, _ = UserSettings.objects.get_or_create(user=request.user)

    if request.method == 'GET':
        return JsonResponse(settings_to_json(settings_obj))

    body, error = _parse_body(request)
    if error:
        return error
    apply_settings_fields(settings_obj, body)
    settings_obj.save()
    return JsonResponse(settings_to_json(settings_obj))
