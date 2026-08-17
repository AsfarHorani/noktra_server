# Job Tracker — Server

Django API backend for the Job Tracker browser extension. See [README.md](README.md) for setup/usage. See [HISTORY.md](HISTORY.md) for the full decision log this repo was split from (predates the split — also covers the extension, which now lives in the companion [noktra_extension](https://github.com/AsfarHorani/noktra_extension) repo).

## What this is

A local-only Django server providing:
- Real per-user auth (signup/login/logout, hand-rolled token auth)
- CRUD for tracked job applications and a candidate profile
- Two LLM-backed features, both calling a local Ollama instance — never a cloud provider:
  - `analysis`: qualitative job-search insights (interview/offer patterns vs. rejected/ghosted)
  - `assistant`: resume parsing, cover-letter generation, interview-answer generation

This server has no standalone UI. It exists to be called by the companion [noktra_extension](https://github.com/AsfarHorani/noktra_extension) repo (a Chrome extension + Angular dashboard).

## Architecture conventions

- **Plain Django views, not Django REST Framework.** `JsonResponse`, `@csrf_exempt`, a `_parse_body()` helper for JSON parsing, one `require_auth` decorator (`accounts/auth.py`) reading `Authorization: Token <key>`. This project stays deliberately dependency-light (`requirements.txt` is Django + requests + python-dotenv) — don't reach for DRF, celery, or similar without a real need.
- **SQLite, no separate DB service.** This server is designed to run locally alongside the extension, never deployed. Don't add a DB migration to a different engine without a concrete reason.
- **Client-facing JSON is camelCase; DB columns are snake_case.** `tracker/serializers.py`'s plain dict-shaping functions (`application_to_json`/`apply_application_fields`, etc.) translate at the API boundary. Keep new fields following this pattern rather than inventing a serializer framework.
- **`Application.status`/`application_date` and `Profile`'s list fields (`skills`, `experience`, etc.) are intentionally unconstrained** — no `choices=`, no `DateField`, plain `JSONField(default=list)`. This means a client-side-only schema change never needs a migration. Don't add strict constraints without checking whether that property still needs to hold.
- **LLM prompts are in JSON, not hardcoded in Python.** `analysis/prompts.json` and `assistant/prompts.json` hold every actual instruction/template string; `prompts.py` in each app only does data-shaping and `str.format()` substitution. Tune wording by editing the JSON file, not the Python. Keep `{placeholder}` names in the JSON in sync with what `prompts.py` passes to `.format()` — a mismatch raises `KeyError` at generation time.
- **Stats are computed in Python, never asked of the LLM.** `analysis/stats.py` computes counts/rates deterministically; the model only describes qualitative patterns between two pre-computed groups. Never delegate exact counting/computation to the model where Python can just compute it — the same principle governs `assistant/prompts.py`'s `format_cover_letter()` (name/date/signature assembled in Python, not generated) and its `_extract_known_skills()` (a computed skills whitelist injected into the prompt, to stop the model inventing expertise the candidate doesn't have).
- **Auth-required test pattern**: every endpoint is `@require_auth`'d; every test file creates a `User`/`AuthToken` in `setUp()`, attaches `HTTP_AUTHORIZATION` on requests, and includes a `test_missing_auth_returns_401`-style test. Copy this pattern for new endpoints.
- **Fabrication safety is an ongoing, never-fully-solved concern** for `assistant`'s generation endpoints (cover letters, interview answers) — see `ANTI_FABRICATION_RULE` and the skill-whitelist mechanism in `assistant/prompts.py`, and HISTORY.md's extensive log of specific fabrication failures found and mitigated. Any change touching prompt wording for these two endpoints should be tested against a live Ollama instance, not just the mocked unit tests, since generation *quality* (as opposed to request/response shape) can't be verified by mocked tests.

## Structure

```
jobtracker_server/   settings.py (env-based config, see .env.example), urls.py
accounts/            AuthToken model, require_auth decorator, signup/login/logout views
tracker/             Application/Profile/UserSettings models + views + serializers
analysis/            Insights endpoint: stats.py (deterministic) + prompts.py/.json + ollama_client.py
assistant/           parse-resume/cover-letter/answer endpoints: prompts.py/.json + views.py
```

`analysis/ollama_client.py` is the one Ollama-calling client, imported directly by `assistant` too (`generate(prompt, json_mode=True, temperature=None)` — `json_mode=False` for natural-language output like cover letters).

## Testing

`python manage.py test` — 63 tests, mocked Ollama (no live model/GPU needed), covers CRUD, ownership isolation, and every documented validation/error path. Run this after any change to `views.py`/`models.py`/`serializers.py` in any app.

For generation *quality* (not just request handling), see README.md's "Manual end-to-end testing against a live model" section — that needs a real Ollama instance and human judgment, which the automated suite can't provide.
