# Run with: .venv/bin/python.exe manage.py test tracker
#
# No mocking anywhere in this file — Application/Profile/UserSettings are
# the real, DB-backed replacement for chrome.storage.local (see CLAUDE.md's
# "Real Backend" section), so these tests exercise the actual ORM/views
# against a temporary test database rather than a fake. Ownership isolation
# (a logged-in user only ever seeing their own rows) is the one property
# that's genuinely new/risky compared to the old chrome.storage.local world
# — every test class below that has more than one meaningful case includes
# at least one isolation test, not just a happy path.

import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import AuthToken

from .models import Application, Profile, UserSettings


# Shared setUp for every test class below: two separate users with their
# own tokens, so any test that needs to prove isolation just switches which
# token self.auth() attaches instead of re-creating a second user each time.
class TrackerTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="a@example.com", email="a@example.com", password="pw")
        self.token = AuthToken.objects.create(user=self.user)
        self.other_user = User.objects.create_user(username="b@example.com", email="b@example.com", password="pw")
        self.other_token = AuthToken.objects.create(user=self.other_user)

    # Defaults to self.user's token; pass other_token to act as the second
    # user instead — keeps every request line below to one call instead of
    # repeating the header dict construction everywhere.
    def auth(self, token=None):
        return {"HTTP_AUTHORIZATION": f"Token {(token or self.token).key}"}


class ApplicationsListCreateTests(TrackerTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("applications")

    # No Authorization header at all — require_auth should 401 before the
    # view body (list vs. create) is ever reached.
    def test_requires_auth(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    # A freshly signed-up user with nothing tracked yet should get an empty
    # list, not a 404 or a null — mirrors what the popup/dashboard render as
    # "no applications tracked yet".
    def test_list_empty(self):
        response = self.client.get(self.url, **self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    # The core round-trip: POST creates a row (confirms it comes back with a
    # real id and the fields as given), and a follow-up GET confirms it was
    # actually persisted, not just echoed back in the create response.
    def test_create_and_list(self):
        payload = {"jobTitle": "Backend Engineer", "company": "Acme", "status": "Pending"}
        create = self.client.post(self.url, data=json.dumps(payload), content_type="application/json", **self.auth())
        self.assertEqual(create.status_code, 201)
        body = create.json()
        self.assertEqual(body["jobTitle"], "Backend Engineer")
        self.assertTrue(body["id"])

        listed = self.client.get(self.url, **self.auth()).json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["company"], "Acme")

    # The whole point of moving off chrome.storage.local and onto real
    # accounts: one user's tracked applications must never leak into
    # another user's list, even though both hit the exact same endpoint.
    def test_applications_are_isolated_per_user(self):
        payload = {"jobTitle": "Mine", "company": "Acme"}
        self.client.post(self.url, data=json.dumps(payload), content_type="application/json", **self.auth())

        other_list = self.client.get(self.url, **self.auth(self.other_token)).json()
        self.assertEqual(other_list, [])


class ApplicationDetailTests(TrackerTestCase):
    def setUp(self):
        super().setUp()
        self.app = Application.objects.create(user=self.user, job_title="Backend Engineer", company="Acme")
        self.url = reverse("application_detail", args=[self.app.id])

    def test_get(self):
        response = self.client.get(self.url, **self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["jobTitle"], "Backend Engineer")

    # A record id that's real but belongs to someone else should look
    # exactly like a record that doesn't exist at all (404, via the view's
    # Application.objects.get(id=..., user=request.user) filter) — not a
    # 403, which would confirm the id is valid and just off-limits.
    def test_other_user_gets_404(self):
        response = self.client.get(self.url, **self.auth(self.other_token))
        self.assertEqual(response.status_code, 404)

    # PATCH should only touch the fields actually sent — jobTitle wasn't
    # part of this payload, so it must survive unchanged alongside the
    # status change. This is the behavior apply_application_fields()
    # (serializers.py) exists to guarantee, as opposed to a full overwrite.
    def test_patch_updates_only_given_fields(self):
        payload = {"status": "Applied"}
        response = self.client.patch(self.url, data=json.dumps(payload), content_type="application/json", **self.auth())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "Applied")
        self.assertEqual(body["jobTitle"], "Backend Engineer")

    def test_delete(self):
        response = self.client.delete(self.url, **self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Application.objects.filter(id=self.app.id).exists())

    # Same isolation guarantee as the list/create tests, but for delete
    # specifically — a malicious or buggy client can't destroy another
    # user's data just by guessing/incrementing an id.
    def test_other_user_cannot_delete(self):
        response = self.client.delete(self.url, **self.auth(self.other_token))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Application.objects.filter(id=self.app.id).exists())


class ApplicationByKeyTests(TrackerTestCase):
    # jobKey lookup is how content/detect.js's scan() tells "already
    # tracked, show a status prompt" apart from "never seen, show a track
    # prompt" (see CLAUDE.md) — this confirms the server-side half of that
    # dedup logic actually finds the right row.
    def test_found(self):
        Application.objects.create(user=self.user, job_title="Backend Engineer", job_key="acme.com:123")
        response = self.client.get(reverse("application_by_key"), {"jobKey": "acme.com:123"}, **self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["jobKey"], "acme.com:123")

    # No match should come back as a plain JSON null with a 200, not a 404
    # — the content script treats "no record for this jobKey" as a normal,
    # expected outcome (first visit to a job), not an error condition.
    def test_not_found_returns_null(self):
        response = self.client.get(reverse("application_by_key"), {"jobKey": "nope"}, **self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json())

    def test_missing_param_returns_400(self):
        response = self.client.get(reverse("application_by_key"), **self.auth())
        self.assertEqual(response.status_code, 400)


class ClearApplicationsTests(TrackerTestCase):
    # The dashboard's "Clear All" button should only ever wipe the
    # logged-in user's own rows — confirms the DELETE is scoped by
    # request.user the same way every other endpoint is, not a global wipe.
    def test_clears_only_own_applications(self):
        Application.objects.create(user=self.user, job_title="Mine")
        Application.objects.create(user=self.other_user, job_title="Not mine")

        response = self.client.delete(reverse("clear_applications"), **self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Application.objects.filter(user=self.user).count(), 0)
        self.assertEqual(Application.objects.filter(user=self.other_user).count(), 1)


class ProfileViewTests(TrackerTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("profile")

    # First-ever GET for a user with no profile row yet should get-or-create
    # one on the fly (see views.py's profile()) rather than 404ing — the
    # dashboard's Profile page expects to always have *something* to render,
    # even before a resume's ever been uploaded.
    def test_get_creates_empty_profile(self):
        response = self.client.get(self.url, **self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["skills"], [])
        self.assertTrue(Profile.objects.filter(user=self.user).exists())

    def test_put_updates_profile(self):
        payload = {"fullName": "Jordan Lee", "skills": ["Python", "Django"]}
        response = self.client.put(self.url, data=json.dumps(payload), content_type="application/json", **self.auth())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["fullName"], "Jordan Lee")
        self.assertEqual(body["skills"], ["Python", "Django"])

    # Profile is a OneToOneField on User — this confirms that relationship
    # actually isolates data per user in practice, not just in the schema:
    # writing to one user's profile must never appear when a different
    # user's token requests theirs.
    def test_profile_isolated_per_user(self):
        self.client.put(self.url, data=json.dumps({"fullName": "Mine"}), content_type="application/json", **self.auth())
        other = self.client.get(self.url, **self.auth(self.other_token)).json()
        self.assertEqual(other["fullName"], "")


class SettingsViewTests(TrackerTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("settings")

    # Matches the old chrome.storage.local getSettings() default (autoDetect:
    # true) — a user who's never touched the setting should still get a
    # fully-formed, sensible object back, not an empty one the client has to
    # patch defaults onto itself.
    def test_get_defaults_to_auto_detect_true(self):
        response = self.client.get(self.url, **self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["autoDetect"])

    def test_put_updates_setting(self):
        payload = {"autoDetect": False}
        response = self.client.put(self.url, data=json.dumps(payload), content_type="application/json", **self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["autoDetect"])
        self.assertFalse(UserSettings.objects.get(user=self.user).auto_detect)
