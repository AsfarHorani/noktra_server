"""The one HTTP endpoint this whole server exposes: POST /api/analyze/.

Called by popup/popup.js's analyzeButton handler with the full applications
array read straight out of the extension's chrome.storage.local. This view
is deliberately the only place that ties the three analysis modules
together — stats.py (deterministic math), prompts.py (LLM prompt building),
and ollama_client.py (the actual model call) — so each of those stays
independently testable (see tests.py, which mocks ollama_client.generate).
"""

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.auth import require_auth

from . import ollama_client
from .prompts import build_prompt
from .stats import compute_stats


# csrf_exempt: this is a JSON API hit by fetch() from the extension popup,
# not a Django-rendered <form> with a session cookie to protect — there's no
# CSRF token to check in the first place. require_POST: the only verb this
# endpoint supports; anything else gets Django's standard 405. require_auth:
# every endpoint on this server is now behind a login (see accounts/).
@csrf_exempt
@require_POST
@require_auth
def analyze(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Request body must be valid JSON."}, status=400)

    applications = body.get("applications")
    if not isinstance(applications, list):
        return JsonResponse({"error": "Expected an \"applications\" array."}, status=400)

    # Stats are always computed and returned, even below, before any LLM
    # call — they're pure Python and never depend on Ollama being reachable.
    stats = compute_stats(applications)

    # Nothing to compare yet — skip the Ollama round-trip entirely rather
    # than sending it an empty prompt.
    if not applications:
        return JsonResponse({
            "stats": stats,
            "insights": {
                "summary": "No applications tracked yet — nothing to analyze.",
                "interview_patterns": [],
                "rejection_patterns": [],
                "recommendations": [],
            },
        })

    prompt = build_prompt(applications, stats)
    try:
        insights = ollama_client.generate(prompt)
    except ollama_client.OllamaUnavailableError as exc:
        # Ollama not running / unreachable — fail with a message the popup
        # can show directly, rather than a bare 500 + stack trace.
        return JsonResponse({"error": str(exc)}, status=503)
    except ollama_client.OllamaResponseParseError as exc:
        # The model didn't return valid JSON despite format="json" —
        # surface its raw text rather than failing the whole request.
        insights = {
            "summary": exc.raw_text.strip() or "The model returned an empty response.",
            "interview_patterns": [],
            "rejection_patterns": [],
            "recommendations": [],
        }

    return JsonResponse({"stats": stats, "insights": insights})
