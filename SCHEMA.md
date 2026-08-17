# Database Schema

Entity-relationship diagram for the real backend introduced in CLAUDE.md's
"Real Backend: Accounts, Applications & Profile Storage" section. SQLite
(`server/db.sqlite3`), one row per user for `Profile`/`UserSettings`, one row
per tracked job for `Application`. `User` is Django's own built-in
`auth.User` model (`django.contrib.auth`) — not redefined here, just
extended via foreign keys the same way `accounts`/`tracker` extend it.

```mermaid
erDiagram
    USER ||--o{ AUTHTOKEN : "has (login sessions)"
    USER ||--o{ APPLICATION : "tracks"
    USER ||--|| PROFILE : "has"
    USER ||--|| USERSETTINGS : "has"

    USER {
        int id PK
        string username "== email, no separate username field is exposed"
        string email
        string password "Django's own PBKDF2 hash"
    }

    AUTHTOKEN {
        int id PK
        int user_id FK
        string key UK "64-char random hex, sent as Authorization Token key"
        datetime created_at
    }

    APPLICATION {
        int id PK
        int user_id FK
        string job_key "hostname:identifier dedup key, see content/detect.js"
        string job_title
        string company
        string location
        string job_url
        string employment_type
        text job_description
        string status "Pending/Applied/Interview/Offer/Rejected/Withdrawn/Ghosted/Ignored, no DB constraint"
        string application_date "plain string, not a DateField"
        text notes
        text cover_letter
        datetime created_at
        datetime updated_at
    }

    PROFILE {
        int id PK
        int user_id FK UK "OneToOneField"
        string resume_file_name
        text resume_text
        string uploaded_at
        string full_name
        string email
        string phone
        text summary
        json experience "list of title/company/dates/description"
        json education "list of school/degree/field/dates"
        json projects "list of name/description/technologies"
        json skills
        json languages
        json certifications
        json interests
    }

    USERSETTINGS {
        int id PK
        int user_id FK UK "OneToOneField"
        bool auto_detect "default true"
    }
```

## Notes

- **`AUTHTOKEN` is `||--o{`, not `||--||`**: the FK allows more than one
  token per user (nothing in the schema stops it), but `accounts/views.py`'s
  `login()` uses `get_or_create` so in practice one user only ever holds one
  live token at a time — logging in again just hands back the same one
  rather than minting a second. `logout()` deletes it outright rather than
  just marking it inactive, so there's no expired-token cleanup to run.
- **Every FK is `on_delete=CASCADE`**: deleting a `User` deletes their
  `AuthToken`, every `Application`, their `Profile`, and their
  `UserSettings` with it. There's no account-deletion flow yet (see
  CLAUDE.md's "Real Backend" Working notes — no password reset/email
  verification either, accepted for a personal local tool), but if one gets
  added later this is the cascade it would trigger.
- **`status`/`application_date` and the `Profile` list fields are
  deliberately unconstrained** (no `choices=`, no `DateField`, plain
  `JSONField(default=list)`) — this mirrors the old `chrome.storage.local`
  array's schemaless-ness on purpose, so a client-side-only schema change
  (a new status, a new profile field) still doesn't need a migration. See
  CLAUDE.md's "Data Model (MVP)" section.
- **Field names here are the DB/Python side (snake_case)** — the JSON the
  extension actually sends/receives over the API is camelCase
  (`jobTitle`, `applicationDate`, `coverLetter`, ...); `tracker/serializers.py`
  translates between the two at the API boundary. See CLAUDE.md for why.
- Regenerate/update this diagram by hand if `accounts/models.py` or
  `tracker/models.py` change — there's no `django-extensions`-style
  auto-generation wired up, this is a maintained-by-hand doc.
