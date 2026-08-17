"""Builds the prompt sent to Ollama for qualitative pattern-finding.

The model is deliberately never asked for counts or rates — see stats.py.
It only compares the positive-signal group (Interview/Offer) against the
negative-signal group (Rejected/Ghosted) and describes what's common in each.

Prompt WORDING lives in prompts.json, not here — see assistant/prompts.py's
module docstring for why this split exists; the same reasoning applies here.
"""

import json
import pathlib

POSITIVE_STATUSES = {"Interview", "Offer"}
NEGATIVE_STATUSES = {"Rejected", "Ghosted"}

NOTES_MAX_CHARS = 400

_PROMPTS_PATH = pathlib.Path(__file__).resolve().parent / "prompts.json"
with open(_PROMPTS_PATH, encoding="utf-8") as _f:
    _PROMPTS = json.load(_f)

RESPONSE_SCHEMA_HINT = _PROMPTS["response_schema_hint"]
_SAMPLE_SIZE_NOTE = _PROMPTS["sample_size_note"]
_BUILD_PROMPT_TEMPLATE = _PROMPTS["build_prompt_template"]


def _condense(app):
    notes = (app.get("notes") or "")[:NOTES_MAX_CHARS]
    return {
        "jobTitle": app.get("jobTitle") or "",
        "company": app.get("company") or "",
        "location": app.get("location") or "",
        "employmentType": app.get("employmentType") or "",
        "status": app.get("status") or "",
        "notes": notes,
    }


def build_prompt(applications, stats):
    positive = [_condense(a) for a in applications if a.get("status") in POSITIVE_STATUSES]
    negative = [_condense(a) for a in applications if a.get("status") in NEGATIVE_STATUSES]

    sample_size_note = _SAMPLE_SIZE_NOTE if len(positive) + len(negative) < 3 else ""

    return _BUILD_PROMPT_TEMPLATE.format(
        sample_size_note=sample_size_note,
        positive_count=len(positive),
        positive_json=json.dumps(positive, indent=2),
        negative_count=len(negative),
        negative_json=json.dumps(negative, indent=2),
        response_schema_hint=RESPONSE_SCHEMA_HINT,
    )
