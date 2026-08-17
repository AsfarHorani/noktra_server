"""Three endpoints: parse a resume into a structured profile, generate a
cover letter, generate an interview-question answer. All three follow the
same shape as analysis/views.py's analyze() — csrf_exempt JSON API, mocked
in tests, 503 on Ollama being unreachable — reusing analysis.ollama_client
directly rather than a second copy of the Ollama-calling code.
"""

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.auth import require_auth
from analysis import ollama_client

from .prompts import (
    build_answer_prompt,
    build_cover_letter_prompt,
    build_parse_resume_prompt,
    format_cover_letter,
    job_description_missing,
    profile_is_empty,
)

_JOB_DESCRIPTION_REQUIRED_ERROR = (
    "Add the job description before generating this — paste it into the application's Job Description field "
    "so the result can actually address what this specific job is asking for, not just generic interest."
)


def _parse_body(request):
    try:
        return json.loads(request.body), None
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "Request body must be valid JSON."}, status=400)


@csrf_exempt
@require_POST
@require_auth
def parse_resume(request):
    body, error = _parse_body(request)
    if error:
        return error

    resume_text = (body.get("resumeText") or "").strip()
    if not resume_text:
        return JsonResponse({"error": 'Expected non-empty "resumeText".'}, status=400)

    prompt = build_parse_resume_prompt(resume_text)
    try:
        # Low temperature, same reasoning as cover-letter/answer generation
        # (see their views below): a resume with several jobs and dozens of
        # skills is a lot to extract faithfully, and Ollama's default
        # temperature (~0.8) is tuned for varied/creative output, not
        # thorough, consistent extraction — confirmed via repeated live runs
        # that a low temperature here also extracts more reliably.
        profile_fields = ollama_client.generate(prompt, temperature=0.2)
    except ollama_client.OllamaUnavailableError as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    except ollama_client.OllamaResponseParseError:
        return JsonResponse(
            {"error": "The model didn't return a parseable profile. Try again, or fill in the profile manually."},
            status=502,
        )

    return JsonResponse(profile_fields)


@csrf_exempt
@require_POST
@require_auth
def cover_letter(request):
    body, error = _parse_body(request)
    if error:
        return error

    profile = body.get("profile")
    application = body.get("application")
    if not isinstance(profile, dict) or not isinstance(application, dict):
        return JsonResponse({"error": 'Expected "profile" and "application" objects.'}, status=400)

    # User feedback (see CLAUDE.md's Assistant section): a cover letter
    # generated from an empty profile is worse than no letter at all, not an
    # acceptable degraded case — it has nothing real to draw on, so the model
    # either writes something generic to the point of being useless or, as
    # confirmed live, leaks meta-commentary about its own lack of material.
    # Blocked here, before generation, rather than left to the client to
    # decide whether to call this endpoint.
    if profile_is_empty(profile):
        return JsonResponse(
            {
                "error": "Set up your profile before generating a cover letter — upload a resume or fill in "
                "your details on the Profile page so there's something real to write from."
            },
            status=400,
        )

    # User feedback: a cover letter that never engages with what the actual
    # job is asking for isn't worth generating at all — this used to be a
    # graceful degraded case (build_cover_letter_prompt's now-removed
    # no_jd_note told the model to write generically instead), but that's no
    # longer accepted. Blocked here, before generation, same pattern as the
    # profile check above — not left to the client to decide whether to call
    # this endpoint. See CLAUDE.md's fallback sections for which sites
    # (LinkedIn/d.vinci/generic) don't auto-capture a description, meaning
    # this is the normal, expected path there until the user pastes one in.
    if job_description_missing(application):
        return JsonResponse({"error": _JOB_DESCRIPTION_REQUIRED_ERROR}, status=400)

    user_notes = (body.get("userNotes") or "").strip()
    prompt = build_cover_letter_prompt(profile, application, user_notes)
    try:
        # Low temperature: makes the model stick closer to the given
        # profile/job text rather than embellishing — see the docstring on
        # ollama_client.generate() for why this matters here specifically.
        letter_body = ollama_client.generate(prompt, json_mode=False, temperature=0.3)
    except ollama_client.OllamaUnavailableError as exc:
        return JsonResponse({"error": str(exc)}, status=503)

    # The model only wrote the body paragraphs — see format_cover_letter()'s
    # docstring for why the header/salutation/signature are assembled here
    # from real profile/application data instead of asked of the model.
    letter = format_cover_letter(profile, application, letter_body)
    return JsonResponse({"coverLetter": letter})


@csrf_exempt
@require_POST
@require_auth
def answer(request):
    body, error = _parse_body(request)
    if error:
        return error

    profile = body.get("profile")
    application = body.get("application")
    question = (body.get("question") or "").strip()
    if not isinstance(profile, dict) or not isinstance(application, dict):
        return JsonResponse({"error": 'Expected "profile" and "application" objects.'}, status=400)
    if not question:
        return JsonResponse({"error": 'Expected non-empty "question".'}, status=400)

    # Same reasoning/block as cover_letter() above — an interview answer is
    # "about the job" just as much as a cover letter is, and one that never
    # engages with the actual posting (e.g. "why this role") isn't worth
    # generating either. Unlike profile_is_empty (cover letters only,
    # answers still allow an empty profile — see build_answer_prompt's
    # empty_profile_note), this check applies uniformly to both endpoints.
    if job_description_missing(application):
        return JsonResponse({"error": _JOB_DESCRIPTION_REQUIRED_ERROR}, status=400)

    prompt = build_answer_prompt(profile, application, question)
    try:
        result = ollama_client.generate(prompt, json_mode=False, temperature=0.3)
    except ollama_client.OllamaUnavailableError as exc:
        return JsonResponse({"error": str(exc)}, status=503)

    return JsonResponse({"answer": result})
