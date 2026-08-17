# Run with: .venv\bin\python manage.py test analysis
#
# ollama_client.generate is mocked everywhere below (@patch) rather than
# calling a real Ollama instance — that keeps this suite fast and
# deterministic, and able to run without Ollama/a GPU installed at all. For
# checking actual model output quality against a live Ollama, use the
# fixtures in server/test_payloads/ instead (see CLAUDE.md's Phase 2
# "Working notes" section).

import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import AuthToken

from .ollama_client import OllamaResponseParseError, OllamaUnavailableError
from .stats import compute_stats


# Pure-Python tests for stats.py — no Django test client, no HTTP, no
# mocking needed, since compute_stats() has no side effects or dependencies.
class ComputeStatsTests(TestCase):
    # No applications at all: totals should be zero and the rates should be
    # None (not 0, not a ZeroDivisionError) since there's no denominator.
    def test_empty_list(self):
        stats = compute_stats([])
        self.assertEqual(stats["total"], 0)
        self.assertIsNone(stats["interviewRate"])
        self.assertIsNone(stats["offerRate"])

    # Applications exist, but all are still "Pending" — i.e. nothing has been
    # decided yet. Same as the empty case: rates must stay None rather than
    # silently reporting 0%, which would look like "you're getting rejected
    # a lot" instead of "nothing has happened yet".
    def test_all_pending_has_no_decided_denominator(self):
        apps = [{"status": "Pending"}, {"status": "Pending"}]
        stats = compute_stats(apps)
        self.assertEqual(stats["total"], 2)
        self.assertIsNone(stats["interviewRate"])
        self.assertIsNone(stats["offerRate"])

    # The core rate-math case: verifies Pending is excluded from the
    # denominator (see NO_OUTCOME_STATUSES in stats.py) while everything
    # else counts, and that interviewRate correctly folds in Offer as well
    # as Interview (an offer implies an interview happened).
    def test_mixed_statuses_computes_rates_over_decided_only(self):
        apps = [
            {"status": "Interview"},
            {"status": "Offer"},
            {"status": "Rejected"},
            {"status": "Rejected"},
            {"status": "Pending"},  # excluded from the denominator
        ]
        stats = compute_stats(apps)
        self.assertEqual(stats["total"], 5)
        # decided = 4 (Interview, Offer, Rejected, Rejected); Pending excluded
        self.assertEqual(stats["interviewRate"], 0.5)  # (Interview+Offer)/decided = 2/4
        self.assertEqual(stats["offerRate"], 0.25)  # Offer/decided = 1/4

    # A status outside shared/constants.js STATUSES (e.g. the extension's
    # schema evolves and this server isn't updated yet) shouldn't be dropped
    # silently — it should still show up in the total, bucketed as "Unknown"
    # so a mismatch is visible in the response instead of hidden.
    def test_unknown_status_is_counted_separately_not_dropped(self):
        apps = [{"status": "SomeFutureStatus"}]
        stats = compute_stats(apps)
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["byStatus"]["Unknown"], 1)


# HTTP-level tests for views.analyze(), via Django's test client
# (self.client) — exercises the same request-handling paths popup.js's
# fetch() call can hit: bad input, the empty-list shortcut, a normal success
# response, and Ollama being unreachable.
class AnalyzeViewTests(TestCase):
    def setUp(self):
        # reverse("analyze") resolves the name registered in analysis/urls.py
        # to the actual /api/analyze/ path, so this test doesn't hardcode it.
        self.url = reverse("analyze")
        user = User.objects.create_user(username="a@example.com", password="pw")
        self.token = AuthToken.objects.create(user=user)

    # Small helper so every test below doesn't have to repeat
    # method/content_type/auth-header — POST is the only verb the endpoint
    # accepts, and every request needs a valid token now (see accounts/).
    def post(self, payload_str, content_type="application/json"):
        return self.client.post(
            self.url, data=payload_str, content_type=content_type, HTTP_AUTHORIZATION=f"Token {self.token.key}"
        )

    # @require_POST on the view should reject GET with Django's standard 405,
    # not a 404 or a crash.
    def test_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    # No Authorization header at all — every endpoint on this server now
    # requires a logged-in user (see accounts/auth.py's require_auth).
    def test_missing_auth_returns_401(self):
        response = self.client.post(self.url, data=json.dumps({"applications": []}), content_type="application/json")
        self.assertEqual(response.status_code, 401)

    # Body isn't JSON at all — json.loads() in the view should raise
    # JSONDecodeError, which the view catches and turns into a clean 400
    # rather than an unhandled exception / 500.
    def test_malformed_json_returns_400(self):
        response = self.post("not json")
        self.assertEqual(response.status_code, 400)

    # Valid JSON, but no "applications" array in it — the view's
    # isinstance(applications, list) check should catch this before it ever
    # reaches compute_stats() or the prompt builder.
    def test_missing_applications_key_returns_400(self):
        response = self.post(json.dumps({"foo": "bar"}))
        self.assertEqual(response.status_code, 400)

    # applications: [] is a valid, well-formed request with nothing to
    # analyze. The view should short-circuit with a friendly default message
    # *without* ever calling Ollama — mock_generate.assert_not_called()
    # verifies that shortcut actually happens, not just that the response
    # looks right.
    @patch("analysis.views.ollama_client.generate")
    def test_empty_applications_skips_ollama_call(self, mock_generate):
        response = self.post(json.dumps({"applications": []}))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["stats"]["total"], 0)
        self.assertIn("No applications tracked yet", body["insights"]["summary"])
        mock_generate.assert_not_called()

    # The happy path: a couple of real applications, Ollama mocked to return
    # a fixed insights dict. Confirms the view (a) still computes its own
    # "stats" independently of whatever the mock returns, and (b) passes the
    # mocked "insights" straight through untouched into the response.
    @patch("analysis.views.ollama_client.generate")
    def test_success_combines_computed_stats_with_mocked_insights(self, mock_generate):
        mock_generate.return_value = {
            "summary": "You do better with mid-size industrial companies.",
            "interview_patterns": ["Mid-size companies", "Applied within 24h"],
            "rejection_patterns": ["Large FinTech employers"],
            "recommendations": ["Prioritize industrial/manufacturing listings"],
        }
        payload = {
            "applications": [
                {"jobTitle": "Backend Engineer", "company": "Acme", "status": "Interview", "notes": ""},
                {"jobTitle": "Frontend Dev", "company": "MegaBank", "status": "Rejected", "notes": ""},
            ]
        }
        response = self.post(json.dumps(payload))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["stats"]["total"], 2)
        self.assertEqual(body["insights"]["interview_patterns"], ["Mid-size companies", "Applied within 24h"])
        mock_generate.assert_called_once()

    # Simulates Ollama being down/unreachable by making the mocked
    # generate() raise OllamaUnavailableError, same as the real
    # ollama_client.generate() does on a connection error (see
    # ollama_client.py). The view should turn that into a 503 with an
    # "error" key the popup can display, not a bare 500.
    @patch("analysis.views.ollama_client.generate")
    def test_ollama_unavailable_returns_503(self, mock_generate):
        mock_generate.side_effect = OllamaUnavailableError("Couldn't reach Ollama at http://localhost:11434.")
        payload = {"applications": [{"jobTitle": "X", "company": "Y", "status": "Interview"}]}
        response = self.post(json.dumps(payload))
        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.json())

    # Regression test for ollama_client.py's generalization (it used to
    # build this exact fallback shape internally on a JSON-parse failure;
    # now it raises OllamaResponseParseError and each app's view builds its
    # own fallback — this confirms analysis/views.py's fallback still
    # produces the same shape as before that change).
    @patch("analysis.views.ollama_client.generate")
    def test_ollama_unparseable_response_falls_back_gracefully(self, mock_generate):
        mock_generate.side_effect = OllamaResponseParseError("not actually json")
        payload = {"applications": [{"jobTitle": "X", "company": "Y", "status": "Interview"}]}
        response = self.post(json.dumps(payload))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["insights"]["summary"], "not actually json")
        self.assertEqual(body["insights"]["interview_patterns"], [])
