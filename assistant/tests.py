# Run with: .venv\bin\python manage.py test assistant
#
# Same approach as analysis/tests.py: ollama_client.generate is mocked
# everywhere below, so this suite is fast, deterministic, and needs no live
# Ollama/GPU. For checking actual generated-text quality (does the cover
# letter actually sound human?), that needs a live Ollama and a manual read
# — not something a unit test can meaningfully assert on. Also like
# analysis/tests.py, every view here is now @require_auth'd (see
# accounts/auth.py), so each test class creates its own user+token in
# setUp() and attaches it via its post() helper.

import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import AuthToken
from analysis.ollama_client import OllamaResponseParseError, OllamaUnavailableError

# Shared fixtures reused across all three test classes below — just enough
# profile/application shape for the views' isinstance(..., dict) checks and
# the (mocked) prompt builders to have something real to work with.
SAMPLE_PROFILE = {
    "summary": "Backend engineer with 5 years building Python services.",
    "experience": [{"title": "Backend Engineer", "company": "Acme", "startDate": "2021", "endDate": "Present", "description": "Built APIs."}],
    "skills": ["Python", "Django"],
}
SAMPLE_APPLICATION = {"jobTitle": "Senior Backend Engineer", "company": "Beta Corp", "jobDescription": "Looking for a Django expert."}


class ParseResumeViewTests(TestCase):
    def setUp(self):
        self.url = reverse("parse_resume")
        user = User.objects.create_user(username="a@example.com", password="pw")
        self.token = AuthToken.objects.create(user=user)

    # Small helper so every test below doesn't have to repeat
    # method/content_type/auth-header.
    def post(self, payload_str):
        return self.client.post(
            self.url, data=payload_str, content_type="application/json", HTTP_AUTHORIZATION=f"Token {self.token.key}"
        )

    # @require_POST rejects GET with Django's standard 405, not a 404 or a
    # crash — same convention every view in this project follows.
    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    # No Authorization header at all — require_auth should 401 before the
    # view body (or Ollama) is ever reached. Deliberately bypasses the
    # post() helper here since that's the one thing it always attaches.
    def test_missing_auth_returns_401(self):
        response = self.client.post(self.url, data=json.dumps({"resumeText": "x"}), content_type="application/json")
        self.assertEqual(response.status_code, 401)

    # Body isn't JSON at all — the view's _parse_body() should catch the
    # json.loads() failure and return a clean 400, not a 500.
    def test_malformed_json_returns_400(self):
        self.assertEqual(self.post("not json").status_code, 400)

    def test_missing_resume_text_returns_400(self):
        self.assertEqual(self.post(json.dumps({})).status_code, 400)

    # Whitespace-only counts as "no resume text" too, not a truthy string —
    # the view's .strip() before the emptiness check should catch this.
    def test_blank_resume_text_returns_400(self):
        self.assertEqual(self.post(json.dumps({"resumeText": "   "})).status_code, 400)

    @patch("assistant.views.ollama_client.generate")
    def test_success_returns_structured_profile(self, mock_generate):
        mock_generate.return_value = {"summary": "A summary.", "experience": [], "skills": ["Python"]}
        response = self.post(json.dumps({"resumeText": "Some resume text..."}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"], "A summary.")
        # json_mode defaults to True — confirms this endpoint asks for
        # structured output, unlike cover-letter/answer below.
        mock_generate.assert_called_once()
        self.assertNotIn("json_mode", mock_generate.call_args.kwargs)

    # Simulates Ollama being down — the view should turn
    # OllamaUnavailableError into a 503 with a message the dashboard can
    # show directly, not a bare 500.
    @patch("assistant.views.ollama_client.generate")
    def test_ollama_unavailable_returns_503(self, mock_generate):
        mock_generate.side_effect = OllamaUnavailableError("Couldn't reach Ollama.")
        response = self.post(json.dumps({"resumeText": "Some resume text..."}))
        self.assertEqual(response.status_code, 503)

    # Unlike analysis/views.py (which has a sensible fallback shape to fall
    # back to — empty pattern lists), there's no reasonable partial-profile
    # fallback here, so an unparseable response is a real error, not a
    # soft-degraded 200.
    @patch("assistant.views.ollama_client.generate")
    def test_unparseable_response_returns_502(self, mock_generate):
        mock_generate.side_effect = OllamaResponseParseError("not json")
        response = self.post(json.dumps({"resumeText": "Some resume text..."}))
        self.assertEqual(response.status_code, 502)


class CoverLetterViewTests(TestCase):
    def setUp(self):
        self.url = reverse("cover_letter")
        user = User.objects.create_user(username="a@example.com", password="pw")
        self.token = AuthToken.objects.create(user=user)

    def post(self, payload_str):
        return self.client.post(
            self.url, data=payload_str, content_type="application/json", HTTP_AUTHORIZATION=f"Token {self.token.key}"
        )

    # require_auth is applied per-view, not globally — this confirms it's
    # actually on cover_letter specifically, not just parse_resume.
    def test_missing_auth_returns_401(self):
        payload = json.dumps({"profile": SAMPLE_PROFILE, "application": SAMPLE_APPLICATION})
        response = self.client.post(self.url, data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 401)

    # Either "profile" or "application" missing entirely — the view's
    # isinstance(..., dict) check should catch both before ever calling
    # build_cover_letter_prompt().
    def test_missing_profile_or_application_returns_400(self):
        self.assertEqual(self.post(json.dumps({"profile": SAMPLE_PROFILE})).status_code, 400)
        self.assertEqual(self.post(json.dumps({"application": SAMPLE_APPLICATION})).status_code, 400)

    @patch("assistant.views.ollama_client.generate")
    def test_success_returns_plain_text_letter(self, mock_generate):
        mock_generate.return_value = "Dear Beta Corp, I'd love to build Django APIs for you..."
        response = self.post(json.dumps({"profile": SAMPLE_PROFILE, "application": SAMPLE_APPLICATION}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("coverLetter", response.json())
        # The whole reason cover letters go through json_mode=False: forcing
        # JSON on natural-language output produces awkward quoted prose
        # instead of a clean block of text — confirm that's actually set.
        self.assertEqual(mock_generate.call_args.kwargs.get("json_mode"), False)

    # Regression test for a real, confirmed-live fabrication: applying to a
    # job titled "SAP Entwickler" with a Java/Python/JS profile (no SAP or
    # ABAP anywhere), the model wrote "As a seasoned ABAP/4 and ABAP OO
    # developer..." — inferring an entire false technical identity purely
    # from the job title. The fix computes the candidate's real skills in
    # Python and injects them as an explicit whitelist the prompt sends to
    # the model — this test only confirms the whitelist is actually built
    # from the real profile and reaches the prompt Ollama receives (i.e.
    # doesn't silently regress to being dropped or empty); it can't confirm
    # the model itself stops fabricating, since that needs a live model.
    @patch("assistant.views.ollama_client.generate")
    def test_prompt_includes_computed_skill_whitelist_excluding_job_title_tech(self, mock_generate):
        mock_generate.return_value = "Letter body."
        profile = {
            "summary": "Software Engineer with around 4 years of experience.",
            "skills": ["Java", "Python", "JavaScript", "Spring Boot", "React.js"],
        }
        application = {
            "jobTitle": "SAP Entwickler (m/w/d)",
            "company": "SEAL Systems AG",
            "jobDescription": "Suchen ABAP/4 und ABAP OO Entwickler mit oData, SOAP, REST Kenntnissen.",
        }
        response = self.post(json.dumps({"profile": profile, "application": application}))
        self.assertEqual(response.status_code, 200)
        prompt_sent = mock_generate.call_args.args[0]
        self.assertIn("KNOWN, VERIFIED SKILLS", prompt_sent)
        self.assertIn("Java, JavaScript, Python, React.js, Spring Boot", prompt_sent)
        self.assertNotIn("ABAP", prompt_sent.split("KNOWN, VERIFIED SKILLS")[1].split("\n")[0])

    # userNotes is optional — omitting it entirely shouldn't 400, the view
    # should just treat it as an empty string.
    @patch("assistant.views.ollama_client.generate")
    def test_optional_user_notes_not_required(self, mock_generate):
        mock_generate.return_value = "A letter with no special notes."
        payload = {"profile": SAMPLE_PROFILE, "application": SAMPLE_APPLICATION}
        response = self.post(json.dumps(payload))
        self.assertEqual(response.status_code, 200)

    @patch("assistant.views.ollama_client.generate")
    def test_ollama_unavailable_returns_503(self, mock_generate):
        mock_generate.side_effect = OllamaUnavailableError("Couldn't reach Ollama.")
        response = self.post(json.dumps({"profile": SAMPLE_PROFILE, "application": SAMPLE_APPLICATION}))
        self.assertEqual(response.status_code, 503)

    # The actual fix for the reported leaked-meta-commentary bug: a cover
    # letter is worse than no letter when there's no real profile to draw
    # from, so the view rejects it outright — before ever calling Ollama —
    # rather than letting the model paper over the gap (which is what
    # produced the leak in the first place). Empty dict and an all-blank
    # profile should both count as "empty", same as profile_is_empty() itself.
    @patch("assistant.views.ollama_client.generate")
    def test_empty_profile_returns_400_without_calling_ollama(self, mock_generate):
        for empty_profile in ({}, {"summary": "", "experience": [], "skills": []}):
            response = self.post(json.dumps({"profile": empty_profile, "application": SAMPLE_APPLICATION}))
            self.assertEqual(response.status_code, 400)
            self.assertIn("profile", response.json()["error"].lower())
        mock_generate.assert_not_called()

    # User feedback: never generate a cover letter without a real job
    # description — LinkedIn/d.vinci/generic-fallback jobs don't auto-capture
    # one (see CLAUDE.md), so this is the normal path there until the user
    # pastes one into the application's Job Description field. Missing key
    # entirely, empty string, and whitespace-only should all count as
    # "missing" — matches job_description_missing()'s own .strip() check.
    @patch("assistant.views.ollama_client.generate")
    def test_missing_job_description_returns_400_without_calling_ollama(self, mock_generate):
        for application in (
            {"jobTitle": "X", "company": "Y"},
            {"jobTitle": "X", "company": "Y", "jobDescription": ""},
            {"jobTitle": "X", "company": "Y", "jobDescription": "   "},
        ):
            response = self.post(json.dumps({"profile": SAMPLE_PROFILE, "application": application}))
            self.assertEqual(response.status_code, 400)
            self.assertIn("job description", response.json()["error"].lower())
        mock_generate.assert_not_called()


class AnswerViewTests(TestCase):
    def setUp(self):
        self.url = reverse("answer")
        user = User.objects.create_user(username="a@example.com", password="pw")
        self.token = AuthToken.objects.create(user=user)

    def post(self, payload_str):
        return self.client.post(
            self.url, data=payload_str, content_type="application/json", HTTP_AUTHORIZATION=f"Token {self.token.key}"
        )

    # Same reasoning as CoverLetterViewTests' version — require_auth needs
    # to be confirmed on each decorated view independently.
    def test_missing_auth_returns_401(self):
        payload = json.dumps({"profile": SAMPLE_PROFILE, "application": SAMPLE_APPLICATION, "question": "Why this role?"})
        response = self.client.post(self.url, data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 401)

    # profile/application are present here (unlike CoverLetterViewTests'
    # equivalent test) — this class is specifically about "question" being
    # required, so the other two fields are deliberately valid throughout.
    def test_missing_question_returns_400(self):
        payload = {"profile": SAMPLE_PROFILE, "application": SAMPLE_APPLICATION}
        self.assertEqual(self.post(json.dumps(payload)).status_code, 400)

    # Same block as CoverLetterViewTests' version — "anything about the
    # job", not just cover letters, requires a real job description first.
    @patch("assistant.views.ollama_client.generate")
    def test_missing_job_description_returns_400_without_calling_ollama(self, mock_generate):
        application = {"jobTitle": "X", "company": "Y"}
        payload = {"profile": SAMPLE_PROFILE, "application": application, "question": "Why this role?"}
        response = self.post(json.dumps(payload))
        self.assertEqual(response.status_code, 400)
        self.assertIn("job description", response.json()["error"].lower())
        mock_generate.assert_not_called()

    # question is just a free-text string to the view — it doesn't
    # distinguish a preset question from a custom-typed one, so this
    # confirms both work identically rather than assuming it from the code.
    @patch("assistant.views.ollama_client.generate")
    def test_success_works_for_preset_and_custom_questions(self, mock_generate):
        mock_generate.return_value = "I'm a backend engineer who loves building reliable APIs..."
        for question in ["Tell me about yourself", "What's your favorite debugging war story?"]:
            payload = {"profile": SAMPLE_PROFILE, "application": SAMPLE_APPLICATION, "question": question}
            response = self.post(json.dumps(payload))
            self.assertEqual(response.status_code, 200)
            self.assertIn("answer", response.json())

    @patch("assistant.views.ollama_client.generate")
    def test_ollama_unavailable_returns_503(self, mock_generate):
        mock_generate.side_effect = OllamaUnavailableError("Couldn't reach Ollama.")
        payload = {"profile": SAMPLE_PROFILE, "application": SAMPLE_APPLICATION, "question": "Why this role?"}
        response = self.post(json.dumps(payload))
        self.assertEqual(response.status_code, 503)
