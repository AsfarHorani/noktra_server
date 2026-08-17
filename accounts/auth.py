"""The one piece of auth machinery every other app's views import —
require_auth reads an `Authorization: Token <key>` header, looks it up
against AuthToken, and sets request.user before calling through. A 401
JsonResponse (not an exception) on anything wrong, matching the rest of
this project's "fail with a JSON error the client can show directly"
convention (see analysis/views.py, assistant/views.py).
"""

from functools import wraps

from django.http import JsonResponse

from .models import AuthToken


def require_auth(view_fn):
    @wraps(view_fn)
    def wrapped(request, *args, **kwargs):
        header = request.headers.get('Authorization', '')
        if not header.startswith('Token '):
            return JsonResponse({'error': 'Missing or malformed Authorization header.'}, status=401)

        key = header.removeprefix('Token ').strip()
        try:
            token = AuthToken.objects.select_related('user').get(key=key)
        except AuthToken.DoesNotExist:
            return JsonResponse({'error': 'Invalid or expired token.'}, status=401)

        request.user = token.user
        return view_fn(request, *args, **kwargs)

    return wrapped
