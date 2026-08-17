"""Prompt builders for the assistant app — resume parsing, cover letters,
and interview-answer generation. Kept separate from analysis/prompts.py
since these serve a different concern (candidate profile & content
generation) even though both call the same analysis.ollama_client.generate().

All actual prompt WORDING lives in prompts.json, not here — this file only
does the data-shaping (formatting a profile/application into prompt text)
and the str.format() substitution that fills each template's {placeholder}
slots. Splitting it this way means tuning a rule's wording or adding an
example never touches Python logic, and vice versa. See prompts.json's
"_comment" field for the placeholder-naming contract between the two files.
"""

import datetime
import json
import pathlib

_PROMPTS_PATH = pathlib.Path(__file__).resolve().parent / "prompts.json"
with open(_PROMPTS_PATH, encoding="utf-8") as _f:
    _PROMPTS = json.load(_f)

RESUME_SCHEMA_HINT = _PROMPTS["resume_schema_hint"]
ANTI_FABRICATION_RULE = _PROMPTS["anti_fabrication_rule"]
_SKILL_WHITELIST_TEMPLATE = _PROMPTS["skill_whitelist_template"]

_PARSE_RESUME_TEMPLATE = _PROMPTS["parse_resume_template"]
_COVER_LETTER_NOTES_BLOCK_TEMPLATE = _PROMPTS["cover_letter"]["notes_block_template"]
_COVER_LETTER_BODY_TEMPLATE = _PROMPTS["cover_letter"]["body_template"]
_ANSWER_EMPTY_PROFILE_NOTE = _PROMPTS["answer"]["empty_profile_note"]
_ANSWER_TEMPLATE = _PROMPTS["answer"]["template"]

# Belt-and-suspenders safety net for the "no meta-commentary" instruction in
# the cover-letter template — confirmed live that llama3.1:8b sometimes
# ignores it anyway and either prefixes the body with a line like "Here is
# the cover letter body:", or narrates its own approach as a full leaked
# sentence (see _strip_meta_preamble below). Both lists live in prompts.json
# alongside the instruction text they're a safety net for, not because
# they're prompt wording sent to the model themselves.
_PREAMBLE_PREFIXES = tuple(_PROMPTS["meta_preamble"]["preamble_prefixes"])
_META_COMMENTARY_SIGNALS = tuple(_PROMPTS["meta_preamble"]["meta_commentary_signals"])


def build_parse_resume_prompt(resume_text):
    return _PARSE_RESUME_TEMPLATE.format(resume_text=resume_text, resume_schema_hint=RESUME_SCHEMA_HINT)


def _format_profile(profile):
    lines = []
    if profile.get("fullName"):
        lines.append(f"Full Name: {profile['fullName']}")
    if profile.get("email"):
        lines.append(f"Email: {profile['email']}")
    if profile.get("phone"):
        lines.append(f"Phone: {profile['phone']}")
    if profile.get("summary"):
        lines.append(f"Summary: {profile['summary']}")
    experience = profile.get("experience") or []
    if experience:
        lines.append("Experience:")
        for job in experience:
            span = f"{job.get('startDate', '')} - {job.get('endDate', '')}".strip(" -")
            lines.append(f"  - {job.get('title', '')} at {job.get('company', '')} ({span}): {job.get('description', '')}")
    education = profile.get("education") or []
    if education:
        lines.append("Education:")
        for ed in education:
            lines.append(f"  - {ed.get('degree', '')} {ed.get('field', '')} — {ed.get('school', '')}")
    projects = profile.get("projects") or []
    if projects:
        lines.append("Projects:")
        for proj in projects:
            lines.append(f"  - {proj.get('name', '')}: {proj.get('description', '')} ({proj.get('technologies', '')})")
    skills = profile.get("skills") or []
    if skills:
        lines.append(f"Skills: {', '.join(skills)}")
    languages = profile.get("languages") or []
    if languages:
        lines.append(f"Languages: {', '.join(languages)}")
    certifications = profile.get("certifications") or []
    if certifications:
        lines.append(f"Certifications: {', '.join(certifications)}")
    interests = profile.get("interests") or []
    if interests:
        lines.append(f"Interests: {', '.join(interests)}")
    formatted = "\n".join(lines) if lines else "(no profile information provided)"

    # The structured fields above are an AI-extracted SUMMARY of the resume,
    # not the resume itself — confirmed live that it can compress away real,
    # specific details (a particular kind of work at a particular company)
    # that never make it into any structured field, even though nothing
    # dropped them on purpose. Since the original resume text is already
    # saved in full (resume-upload.ts stores it on the profile alongside the
    # parsed fields specifically so it isn't lost), include it here too as
    # the fuller, more trustworthy source — the structured section above is
    # a convenience index into it, not a replacement for it. Treat anything
    # written here as just as real and usable as the structured fields.
    resume_text = (profile.get("resumeText") or "").strip()
    if resume_text:
        formatted += f"\n\nFull Resume Text (the structured fields above are a summary of this and may have condensed or missed specific details — this is the complete, authoritative source; use it too, not just the summary):\n{resume_text}"

    return formatted


def _format_application(application):
    parts = [
        f"Job Title: {application.get('jobTitle', '')}",
        f"Company: {application.get('company', '')}",
    ]
    if application.get("location"):
        parts.append(f"Location: {application['location']}")
    if application.get("jobDescription"):
        parts.append(f"Job Description: {application['jobDescription']}")
    return "\n".join(parts)


# Confirmed live, a real and worse failure than the genericness
# ANTI_FABRICATION_RULE was originally written against: applying for a
# "SAP Entwickler" (SAP Developer) role, with a profile showing Java/Python/
# JavaScript/Spring Boot/React and NO SAP or ABAP anywhere, llama3.1:8b wrote
# "As a seasoned ABAP/4 and ABAP OO developer, I have a proven track
# record..." and "I have developed a strong foundation in ABAP/4 and ABAP OO
# programming languages" — a complete, confident, specific fabrication of an
# entire technical identity, inferred purely from the job title matching a
# technology stack. Telling the model "don't invent skills" in the abstract
# (the existing ANTI_FABRICATION_RULE) was not enough to stop this — the
# model needs something it can mechanically check itself against, not just a
# principle to reason from. So this extracts the candidate's actual
# structured skills/languages/certifications/project-technologies in Python
# (never asking the LLM to identify or judge this) into an explicit
# allow-list, which get_skill_whitelist_block() below turns into a hard
# boundary in the prompt: only what's literally in this list may be claimed.
def _extract_known_skills(profile):
    skills = {}  # lowercase -> first-seen original casing, for de-duping without losing display text
    for key in ("skills", "languages", "certifications"):
        for item in profile.get(key) or []:
            text = str(item).strip()
            if text:
                skills.setdefault(text.lower(), text)
    for project in profile.get("projects") or []:
        for tech in str(project.get("technologies") or "").split(","):
            text = tech.strip()
            if text:
                skills.setdefault(text.lower(), text)
    return sorted(skills.values(), key=str.lower)


def _skill_whitelist_block(profile):
    known_skills = _extract_known_skills(profile)
    skill_whitelist = ", ".join(known_skills) if known_skills else "(none listed)"
    return _SKILL_WHITELIST_TEMPLATE.format(skill_whitelist=skill_whitelist)


# Public (no leading underscore) — assistant/views.py's cover_letter() uses
# this directly to reject generation entirely when there's nothing to draw
# on (see CLAUDE.md's "Real Backend"/Assistant sections for why: user
# feedback was that an empty-profile letter is worse than no letter, not an
# acceptable degraded case as this project originally assumed). Still used
# internally here too, for build_answer_prompt's own empty-profile handling
# — answers stay generation-allowed with an empty profile, only cover
# letters were asked to block it.
def profile_is_empty(profile):
    return not any(
        profile.get(key)
        for key in (
            "summary",
            "experience",
            "education",
            "projects",
            "skills",
            "languages",
            "certifications",
            "interests",
            "resumeText",
        )
    )


# Public, same reasoning/usage pattern as profile_is_empty() above —
# assistant/views.py's cover_letter() and answer() both reject generation
# entirely when there's no job description to work from, rather than
# generating something generic. User feedback: a job-related generation
# (cover letter OR interview-answer prep) that never engaged with what the
# actual job asks for isn't useful enough to bother producing — the user
# should paste the description in first, always, not just for sites whose
# fallback happens not to capture one (LinkedIn/d.vinci/generic — see
# CLAUDE.md's fallback sections for which sites those are).
def job_description_missing(application):
    return not (application.get("jobDescription") or "").strip()


# No no_jd_note here anymore — the view (assistant/views.py's
# cover_letter()) now rejects the request with a 400 before this is ever
# called if job_description_missing(application) is true, so this function
# can assume a real job description is always present. Same "remove the
# case entirely rather than ask the model to write around it" reasoning as
# profile_is_empty above, and the same trigger-removal logic that fixed the
# meta-commentary leak: a missing-JD note here would just be one more thing
# for the model to narrate back as prose instead of silently complying with.
def build_cover_letter_prompt(profile, application, user_notes):
    notes_block = _COVER_LETTER_NOTES_BLOCK_TEMPLATE.format(user_notes=user_notes) if user_notes else ""
    return _COVER_LETTER_BODY_TEMPLATE.format(
        anti_fabrication_rule=ANTI_FABRICATION_RULE,
        skill_whitelist_block=_skill_whitelist_block(profile),
        profile=_format_profile(profile),
        application=_format_application(application),
        notes_block=notes_block,
    )


def _strip_meta_preamble(text):
    text = text.strip()

    # Original check: a short label-like first line ("Here is the cover
    # letter:") that's clearly not part of the letter body.
    first_line, _, rest = text.partition("\n")
    stripped_first = first_line.strip()
    looks_like_preamble = stripped_first.endswith(":") or stripped_first.lower().startswith(_PREAMBLE_PREFIXES)
    if looks_like_preamble and rest.strip():
        text = rest.strip()

    # Broader check: a leaked sentence narrating the model's own approach,
    # recognized by content rather than by shape, since this failure mode
    # doesn't reliably end with ":" or start with a fixed prefix. Only
    # checked against the first paragraph — this failure mode always appears
    # as the opening line(s), never buried mid-letter.
    paragraphs = text.split("\n\n", 1)
    first_para = paragraphs[0]
    rest_text = paragraphs[1] if len(paragraphs) > 1 else ""

    sentences = first_para.split(". ")
    if any(signal in sentences[0].lower() for signal in _META_COMMENTARY_SIGNALS):
        remaining_sentences = sentences[1:]
        if remaining_sentences:
            # Drop just the leaked sentence, keep the rest of the paragraph.
            new_first_para = ". ".join(remaining_sentences).strip()
            text = (new_first_para + ("\n\n" + rest_text if rest_text else "")).strip()
        elif rest_text.strip():
            # The whole first paragraph WAS the leaked sentence — drop it.
            text = rest_text.strip()

    return text


# The name/contact header, date, salutation, and signature are assembled here
# in plain Python from the profile/application data that's actually known to
# be real, rather than left to the model. Confirmed live while building this:
# even with an explicit instruction to omit the header entirely when no name
# is on file ("skip this block ... rather than inventing a placeholder"),
# llama3.1:8b still fabricated a complete fake identity — a plausible name
# plus a made-up email and phone number, not a placeholder at all. That's a
# strictly worse failure than the metrics/employer fabrication the rest of
# ANTI_FABRICATION_RULE targets (a fake name/email in an actually-sent letter
# is actively harmful, not just inaccurate), and no amount of prompt wording
# reliably fixed it in testing. Deterministic assembly of the parts that are
# already known — never asking the model to invent identity — is the actual
# fix, the same "don't ask the LLM for what Python can compute exactly"
# principle server/analysis/stats.py already applies to counts/rates.
def format_cover_letter(profile, application, body):
    lines = []
    body = _strip_meta_preamble(body)
    full_name = (profile.get("fullName") or "").strip()
    email = (profile.get("email") or "").strip()
    phone = (profile.get("phone") or "").strip()
    if full_name:
        lines.append(full_name)
    contact_line = ", ".join(filter(None, [email, phone]))
    if contact_line:
        lines.append(contact_line)
    if lines:
        lines.append("")

    lines.append(datetime.date.today().strftime("%B %d, %Y"))
    lines.append("")

    company = (application.get("company") or "").strip()
    lines.append(f"Dear {company} Hiring Team," if company else "Dear Hiring Manager,")
    lines.append("")

    lines.append(body.strip())
    lines.append("")

    lines.append("Sincerely,")
    if full_name:
        lines.append(full_name)

    return "\n".join(lines)


def build_answer_prompt(profile, application, question):
    empty_profile_note = _ANSWER_EMPTY_PROFILE_NOTE if profile_is_empty(profile) else ""
    return _ANSWER_TEMPLATE.format(
        anti_fabrication_rule=ANTI_FABRICATION_RULE,
        skill_whitelist_block=_skill_whitelist_block(profile),
        profile=_format_profile(profile),
        application=_format_application(application),
        empty_profile_note=empty_profile_note,
        question=question,
    )
