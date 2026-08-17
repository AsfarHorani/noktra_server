# Run with: .venv/bin/python.exe manage.py test accounts
#
# Unlike analysis/assistant's tests, nothing here is mocked — signup/login/
# logout are the one part of the server that's genuinely DB-backed (a real
# User + AuthToken row), so these tests exercise Django's actual password
# hashing/validation and the real accounts.models.AuthToken table via a
# temporary test database, not a fake.

import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import AuthToken


class SignupViewTests(TestCase):
    def setUp(self):
        self.url = reverse("signup")

    # Small helper so every test below doesn't have to repeat
    # method/content_type — every request here is a POST with a JSON body.
    def post(self, payload):
        return self.client.post(self.url, data=json.dumps(payload), content_type="application/json")

    # @require_POST on the view should reject GET with Django's standard
    # 405, not a 404 or a crash — same convention as every other view in
    # this project.
    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    # Body isn't JSON at all — the view's own json.loads() should raise and
    # be turned into a clean 400, not an unhandled 500.
    def test_malformed_json_returns_400(self):
        response = self.client.post(self.url, data="not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    # Either field missing entirely — the view's explicit `if not email or
    # not password` check should catch both cases before ever touching the
    # database.
    def test_missing_fields_returns_400(self):
        self.assertEqual(self.post({"email": "a@example.com"}).status_code, 400)
        self.assertEqual(self.post({"password": "correct-horse-battery-staple"}).status_code, 400)

    # A password that fails Django's AUTH_PASSWORD_VALIDATORS (too short/
    # common/numeric-only, see settings.py) should be rejected with a 400
    # *and* leave no half-created user behind — the validate_password() call
    # happens before User.objects.create_user(), so this also confirms that
    # ordering is actually correct, not just that the response code is right.
    def test_weak_password_returns_400(self):
        response = self.post({"email": "a@example.com", "password": "12345678"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="a@example.com").exists())

    # The happy path: confirms a real User row is created (username == the
    # given email, per the view's "no separate username field" decision —
    # see CLAUDE.md's "Real Backend" section) and that the returned token
    # actually matches a real AuthToken row tied to that user, not just that
    # *some* token-shaped string came back.
    def test_success_creates_user_and_token(self):
        response = self.post({"email": "a@example.com", "password": "correct-horse-battery-staple"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["email"], "a@example.com")
        self.assertTrue(data["token"])
        user = User.objects.get(username="a@example.com")
        self.assertTrue(AuthToken.objects.filter(user=user, key=data["token"]).exists())

    # Signing up twice with the same email should never produce two User
    # rows with the same username — the view's explicit
    # User.objects.filter(username=email).exists() check should catch this
    # before Django's own unique-username constraint would (which would
    # otherwise surface as a raw IntegrityError / 500).
    def test_duplicate_email_returns_400(self):
        self.post({"email": "a@example.com", "password": "correct-horse-battery-staple"})
        response = self.post({"email": "a@example.com", "password": "another-strong-password"})
        self.assertEqual(response.status_code, 400)


class LoginViewTests(TestCase):
    def setUp(self):
        self.url = reverse("login")
        self.email = "a@example.com"
        self.password = "correct-horse-battery-staple"
        self.user = User.objects.create_user(username=self.email, email=self.email, password=self.password)

    def post(self, payload):
        return self.client.post(self.url, data=json.dumps(payload), content_type="application/json")

    def test_success_returns_token(self):
        response = self.post({"email": self.email, "password": self.password})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["token"])

    # Right email, wrong password — django.contrib.auth.authenticate()
    # should return None, and the view should turn that into a 401 with a
    # generic "Invalid email or password" message rather than confirming
    # which part was wrong (not that this is a public-facing service, but
    # it's still the correct default not to leak that distinction).
    def test_wrong_password_returns_401(self):
        response = self.post({"email": self.email, "password": "not-the-password"})
        self.assertEqual(response.status_code, 401)

    # An email that was never signed up at all should fail the exact same
    # way as a wrong password — same 401, same generic message — not a
    # different error that would reveal whether an account exists.
    def test_unknown_email_returns_401(self):
        response = self.post({"email": "nobody@example.com", "password": self.password})
        self.assertEqual(response.status_code, 401)

    # The view does AuthToken.objects.get_or_create(user=user) rather than
    # always minting a new token — logging in twice in a row (e.g. two
    # tabs, or the popup and the dashboard both triggering a fresh login)
    # should hand back the *same* token both times, not silently invalidate
    # whichever one was issued first.
    def test_repeated_login_reuses_same_token(self):
        first = self.post({"email": self.email, "password": self.password}).json()["token"]
        second = self.post({"email": self.email, "password": self.password}).json()["token"]
        self.assertEqual(first, second)


class LogoutViewTests(TestCase):
    def setUp(self):
        self.email = "a@example.com"
        self.user = User.objects.create_user(username=self.email, email=self.email, password="correct-horse-battery-staple")
        self.token = AuthToken.objects.create(user=self.user)

    # logout is @require_auth'd like every other endpoint past this file —
    # calling it with no Authorization header at all should 401 the same
    # way any other protected endpoint would, not silently no-op.
    def test_requires_auth(self):
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 401)

    # The actual point of logout: the token row is gone afterward, so a
    # later request reusing that same key would now also 401 — this test
    # checks the DB state directly rather than just trusting the 200.
    def test_success_deletes_token(self):
        response = self.client.post(reverse("logout"), HTTP_AUTHORIZATION=f"Token {self.token.key}")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AuthToken.objects.filter(user=self.user).exists())
