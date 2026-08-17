"""Signup / login / logout — the only three unauthenticated endpoints on
this server (everything else requires the token these hand out). Same
_parse_body / @csrf_exempt / JsonResponse style as assistant/views.py.
"""

import json

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import ValidationError, validate_password
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .auth import require_auth
from .models import AuthToken


def _parse_body(request):
    try:
        return json.loads(request.body), None
    except json.JSONDecodeError:
        return None, JsonResponse({'error': 'Request body must be valid JSON.'}, status=400)


@csrf_exempt
@require_POST
def signup(request):
    body, error = _parse_body(request)
    if error:
        return error

    email = (body.get('email') or '').strip().lower()
    password = body.get('password') or ''
    if not email or not password:
        return JsonResponse({'error': 'Expected non-empty "email" and "password".'}, status=400)

    if User.objects.filter(username=email).exists():
        return JsonResponse({'error': 'An account with that email already exists.'}, status=400)

    # Uses the AUTH_PASSWORD_VALIDATORS already configured in settings.py
    # (minimum length, common-password check, etc.) — those were sitting
    # unused until this endpoint existed.
    try:
        validate_password(password)
    except ValidationError as exc:
        return JsonResponse({'error': ' '.join(exc.messages)}, status=400)

    # username = email throughout — this app never shows a separate
    # username, so there's no reason to ask for two identifiers.
    user = User.objects.create_user(username=email, email=email, password=password)
    token = AuthToken.objects.create(user=user)
    return JsonResponse({'token': token.key, 'email': email})


@csrf_exempt
@require_POST
def login(request):
    body, error = _parse_body(request)
    if error:
        return error

    email = (body.get('email') or '').strip().lower()
    password = body.get('password') or ''

    user = authenticate(request, username=email, password=password)
    if user is None:
        return JsonResponse({'error': 'Invalid email or password.'}, status=401)

    token, _ = AuthToken.objects.get_or_create(user=user)
    return JsonResponse({'token': token.key, 'email': email})


@csrf_exempt
@require_POST
@require_auth
def logout(request):
    AuthToken.objects.filter(user=request.user).delete()
    return JsonResponse({'ok': True})
